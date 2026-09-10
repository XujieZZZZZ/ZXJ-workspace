# -*- coding: utf-8 -*-
"""RQ2-1:相关工作生成能力测评(严格对应 evaluation-guide.md 第一节)。

流程:
  1.1 结构化提取(Title/Authors/Year) -> S2 API 解析(唯一标识/DOI/citation/venue/摘要)
      并统计 S2 检索失败率(检索不到 -> 视为编造或失败,供质量参考);
      三级匹配判定(DOI/S2ID 精确 | JaroWinkler>=0.90 且 |ΔYear|<=1 | SPECTER2 cos>=0.92),
      生成判定矩阵 M_{i,j},S_M=S_H∩S_L;
  1.2 硬性检索指标 R / P / Jaccard;
  1.3 时间分布 RR 与 W1;类内密度 / 类间质心 / Observation 贴合度;MLC / TVR;
  1.4 Core Claim:DeBERTa-NLI 事实忠实度、原子 Claim 覆盖率(LLM 拆解+判定)、G-Eval 逻辑分。
LLM 的 withsearch / withoutsearch 两条链路分别测评(输出各自一份结果)。
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

import numpy as np

import config
import dataio
import metrics_calc as mc
from embedder import Specter2Embedder, cosine, paper_doc_text
from jaro_winkler import jaro_winkler
from nli import NliScorer
from s2_client import S2Client, build_queries
from top_venues import is_top_venue, top_venue_entry
from utils import JsonlStore, log, norm_title, truncate_chars


# =========================================================================== #
# 一、S2 实体解析(带磁盘缓存)
# =========================================================================== #
def resolve_pool(s2: S2Client, pdf_ids: Optional[List[str]] = None) -> Dict[str, dict]:
    """对(可选限定的)论文池做 S2 解析(结果落盘缓存),返回 norm_title -> 记录。

    pdf_ids 用于 --limit 冒烟/调试时只解析相关样本引用的论文;正式全量运行时传 None。
    """
    pool = dataio.collect_work_pool()
    if pdf_ids:
        keep = set(pdf_ids)
        pool = [p for p in pool if keep & set(p["pdf_ids"])]
        log(f"限定样本 {len(keep)} 篇,待解析唯一论文: {len(pool)}")
    queries = [{"_key": norm_title(p["title"]),
                "title": p["title"], "authors": p["authors"], "year": p["year"]}
               for p in pool]
    log(f"待解析唯一论文数: {len(queries)}")
    results = s2.resolve_many(queries, desc="S2 resolve")
    # 限流/网络放弃的条目未入缓存 -> 值为 None,剔除后按成功统计
    n_pending = sum(1 for v in results.values() if v is None)
    results = {k: v for k, v in results.items() if v is not None}
    n_found = sum(1 for r in results.values() if r.get("status") == "found")
    n_miss = sum(1 for r in results.values() if r.get("status") == "missing")
    log(f"S2 解析完成: found={n_found} missing={n_miss} "
        f"放弃待续跑={n_pending} 失败率(未找到)={n_miss / max(len(results), 1):.2%}")
    if n_pending:
        log(f"提示: {n_pending} 条因限流/网络放弃,重新运行本命令会自动续跑补齐")
    return results


def res_meta(res: dict) -> dict:
    """取解析记录的规范元数据(未找到时返回空 dict)。"""
    p = (res or {}).get("s2_paper") or {}
    return p


def work_year(work: dict, res: dict) -> Optional[int]:
    """论文年份:优先数据自带(人类数据有 year),否则取 S2 解析的规范年份。"""
    y = work.get("year")
    if y is None:
        p = res_meta(res)
        y = p.get("year")
    return int(y) if y is not None else None


def search_failure_stats(doc_h: dict, doc_l: dict, res: Dict[str, dict]) -> dict:
    """统计两侧 S2 检索失败率(指南 1.1:检索不到视为编造/失败,供参考其质量)。"""
    out = {}
    for tag, doc in (("H", doc_h), ("L", doc_l)):
        works = dataio.unique_works(doc)
        n_fail = sum(1 for w in works
                     if (res.get(w["_norm"]) or {}).get("status") != "found")
        out[tag] = {"total": len(works), "s2_fail": n_fail,
                    "s2_fail_rate": n_fail / max(len(works), 1)}
    return out


# =========================================================================== #
# 二、三级匹配判定
# =========================================================================== #
def build_vectors(doc_h: dict, doc_l: dict, res: Dict[str, dict],
                  emb: Specter2Embedder, obs: str) -> dict:
    """构造文档两侧论文与 Observation 的文本向量(SPECTER2,磁盘缓存)。"""
    vec: Dict[str, np.ndarray] = {}

    def get_vec(key: str, text: str) -> np.ndarray:
        if key not in vec:
            vec[key] = emb.encode_cached(text)
        return vec[key]

    for doc, tag in ((doc_h, "H"), (doc_l, "L")):
        for w in dataio.unique_works(doc):
            rec = res.get(w["_norm"]) or {}
            p = res_meta(rec)
            text = paper_doc_text(p.get("title") or w["title"], p.get("abstract"))
            get_vec(f"{tag}:{w['_norm']}", text)
    v_obs = get_vec("obs", obs)
    return {"vec": vec, "v_obs": v_obs}


def match_levels(doc_h: dict, doc_l: dict, res: Dict[str, dict],
                 vecs: Dict[str, np.ndarray]) -> dict:
    """三级匹配:返回 {levels: M[i,j]=level, matched_l: [..], matched_h: [..], l1..l3 计数}。

    M 的行=人类论文(按 unique_works 顺序),列=LLM 论文。
    Level1: DOI 或 S2ID 精确相等(两侧均解析成功才可能);
    Level2: JaroWinkler(title)>=0.90 且 |year_L - year_H| <= 1(双方年份可知才判定);
    Level3: SPECTER2 余弦 >= 0.92(前两级未命中时计算)。
    """
    H = dataio.unique_works(doc_h)
    L = dataio.unique_works(doc_l)
    # 预取元数据,避免循环内重复查表
    h_rec = [res.get(w["_norm"]) or {} for w in H]
    l_rec = [res.get(w["_norm"]) or {} for w in L]
    h_p = [res_meta(r) for r in h_rec]
    l_p = [res_meta(r) for r in l_rec]
    h_year = [work_year(w, r) for w, r in zip(H, h_rec)]
    l_year = [work_year(w, r) for w, r in zip(L, l_rec)]
    n_h, n_l = len(H), len(L)
    M = [[0] * n_l for _ in range(n_h)]
    matched_l = [False] * n_l
    # L1 / L2 先判(纯元数据,零向量开销)
    for j in range(n_l):
        lp = l_p[j]
        l_doi = (lp.get("doi") or "").strip().lower()
        l_sid = lp.get("paperId")
        if not l_doi and not l_sid:
            continue
        for i in range(n_h):
            hp = h_p[i]
            if not hp:
                continue
            h_doi = (hp.get("doi") or "").strip().lower()
            h_sid = hp.get("paperId")
            if (l_doi and h_doi and l_doi == h_doi) or (l_sid and h_sid and l_sid == h_sid):
                M[i][j] = 1
                matched_l[j] = True
    # L2
    for i in range(n_h):
        if h_year[i] is None:
            continue
        for j in range(n_l):
            if M[i][j] or l_year[j] is None:
                continue
            if (jaro_winkler(H[i]["title"], L[j]["title"]) >= config.JW_THRESHOLD
                    and abs(h_year[i] - l_year[j]) <= config.YEAR_MAX_DELTA):
                M[i][j] = 2
                matched_l[j] = True
    # L3:仅对仍未命中的 (i,j) 计算余弦
    lvl3_cnt = 0
    vec = vecs["vec"]
    for j in range(n_l):
        if matched_l[j]:
            continue
        vl = vec.get(f"L:{L[j]['_norm']}")
        if vl is None:
            continue
        for i in range(n_h):
            if M[i][j]:
                continue
            vh = vec.get(f"H:{H[i]['_norm']}")
            if vh is None:
                continue
            if cosine(vh, vl) >= config.COS_THRESHOLD:
                M[i][j] = 3
                matched_l[j] = True
                lvl3_cnt += 1
    cnt = {1: 0, 2: 0, 3: 0}
    for i in range(n_h):
        for j in range(n_l):
            if M[i][j]:
                cnt[M[i][j]] += 1
    return {"M": M, "matched_l": [i for i, m in enumerate(matched_l) if m],
            "n_h": n_h, "n_l": n_l, "cnt": cnt, "lvl3_computed": lvl3_cnt,
            "h_titles": [w["title"] for w in H], "l_titles": [w["title"] for w in L]}


# =========================================================================== #
# 三、质量指标(语义/时间/引用/顶会)
# =========================================================================== #
def paper_metrics(doc_h: dict, doc_l: dict, res: Dict[str, dict],
                  vecs: Dict[str, np.ndarray], mat: dict, variant: str, pdf_id: str) -> dict:
    """汇总一个样本的所有数值指标(用于跨 doc 聚合与报告)。"""
    H, L = dataio.unique_works(doc_h), dataio.unique_works(doc_l)
    n_matched = len(mat["matched_l"])
    out: dict = {"pdf_id": pdf_id, "variant": variant,
                 "retrieval": mc.retrieval_metrics(n_matched, len(H), len(L)),
                 "failure": search_failure_stats(doc_h, doc_l, res)}
    # ---- 时间分布 ----
    h_years = [work_year(w, res.get(w["_norm"]) or {}) for w in H]
    l_years = [work_year(w, res.get(w["_norm"]) or {}) for w in L]
    rr_h, rr_h_n = mc.recency_ratio(h_years)
    rr_l, rr_l_n = mc.recency_ratio(l_years)
    w1, w1_nh, w1_nl = mc.w1_cdf_distance(h_years, l_years)
    out["temporal"] = {"rr_h": rr_h, "rr_l": rr_l, "n_years_h": rr_h_n,
                       "n_years_l": rr_l_n, "w1": w1, "w1_n_h": w1_nh, "w1_n_l": w1_nl}
    # ---- 语义结构 ----
    vh = np.stack([vecs["vec"][f"H:{w['_norm']}"] for w in H]) if H else np.zeros((0, 768), dtype=np.float32)
    vl = np.stack([vecs["vec"][f"L:{w['_norm']}"] for w in L]) if L else np.zeros((0, 768), dtype=np.float32)
    out["semantic"] = {
        "intra_h": mc.intra_class_density(vh), "intra_l": mc.intra_class_density(vl),
        "inter": mc.inter_centroid_similarity(vh, vl),
        "rel_h": mc.relevance_to_observation(vh, vecs["v_obs"]),
        "rel_l": mc.relevance_to_observation(vl, vecs["v_obs"]),
    }
    # ---- 客观质量 ----
    def quality_meta(works, tag):
        cits, tops, top_entries = [], [], []
        for w in works:
            p = res_meta(res.get(w["_norm"]) or {})
            cits.append(p.get("citationCount"))
            venue = p.get("venue")
            if venue:
                tops.append(is_top_venue(venue))
                if top_venue_entry(venue):
                    top_entries.append(top_venue_entry(venue))
            else:
                tops.append(False)
        mlc, n_mlc = mc.mean_log_citations(cits)
        tvr, n_tvr = mc.top_venue_ratio(tops)
        return {"mlc": mlc, "n_mlc": n_mlc, "tvr": tvr, "n_tvr": n_tvr,
                "n_venue_known": sum(1 for t in tops)}
    out["quality_h"] = quality_meta(H, "H")
    out["quality_l"] = quality_meta(L, "L")
    return out


# =========================================================================== #
# 四、Core Claim 评估(本地 NLI + LLM 裁判)
# =========================================================================== #
def faithfulness_blocks(doc_l: dict, res: Dict[str, dict],
                        nli: Optional[NliScorer]) -> dict:
    """DeBERTa-NLI 事实忠实度(指南 1.4.1)。

    premise=引文 S2 摘要, hypothesis=该 work 所在段落的 claim 文本;
    仅对"解析成功且含摘要"的 LLM 论文计算,平均并报告分母。"""
    works = dataio.unique_works(doc_l)
    pairs, meta = [], []
    for w in works:
        p = res_meta(res.get(w["_norm"]) or {})
        abstract = (p.get("abstract") or "").strip()
        if not abstract or not w["claims"]:
            continue
        premise = truncate_chars(abstract, 1800)
        hypothesis = truncate_chars(" ".join(w["claims"]), 900)
        pairs.append((premise, hypothesis))
        meta.append(w["title"])
    if not pairs or nli is None:
        return {"faithfulness": None, "n_pairs": len(pairs)}
    probs = nli.entail_prob(pairs)
    return {"faithfulness": float(probs.mean()), "n_pairs": len(pairs),
            "per_paper": [{"title": t, "prob": float(p)} for t, p in zip(meta, probs)]}


def atomic_coverage_items(doc_h: dict, doc_l: dict, variant: str, pdf_id: str) -> List[dict]:
    """构造原子 Claim 拆解 + 覆盖率判定的任务清单(不执行,由 runner 批量跑裁判)。"""
    # 拆解人类 claims(整篇一次)
    dec_item = {"_key": f"{pdf_id}|{variant}|decompose",
                "claims": dataio.all_claims(doc_h)}
    # 支持判定:model_claims = 该 LLM 文档的全部 claims
    model_claims = " ".join(dataio.all_claims(doc_l))
    sup_item = {"_key": f"{pdf_id}|{variant}|support",
                "model_claims": truncate_chars(model_claims, 14000),
                "atoms": [],   # 由拆解结果回填(runner 阶段)
                "doc": {"pdf_id": pdf_id, "variant": variant}}
    return [dec_item, sup_item]


# =========================================================================== #
# 五、汇总
# =========================================================================== #
def _mean_std(vals: List[float]) -> dict:
    """数值序列 -> {mean, std, n};序列含 None/空则跳过(NaN 原样保留并标注)。"""
    vals = [v for v in vals if v is not None]
    if not vals:
        return {}
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "n": len(vals)}


def aggregate(records: List[dict]) -> dict:
    """对多个样本记录做平均(含 std),逐字段显式聚合。"""
    agg: dict = {"n_samples": len(records)}
    fields = {
        "retrieval": ["recall", "precision", "jaccard", "matched", "n_h", "n_l"],
        "temporal": ["rr_h", "rr_l", "w1", "n_years_h", "n_years_l"],
        "semantic": ["intra_h", "intra_l", "inter", "rel_h", "rel_l"],
        "quality_h": ["mlc", "tvr"],
        "quality_l": ["mlc", "tvr"],
    }
    for f, keys in fields.items():
        agg[f] = {}
        for k in keys:
            stat = _mean_std([r[f][k] for r in records])
            if stat:
                agg[f][k] = stat
    # S2 失败率:跨样本汇总(分母=全部论文数)
    agg["failure"] = {}
    for tag in ("H", "L"):
        n_tot = int(np.sum([r["failure"][tag]["total"] for r in records]))
        n_fail = int(np.sum([r["failure"][tag]["s2_fail"] for r in records]))
        agg["failure"][tag] = {"n_total": n_tot, "n_fail": n_fail,
                               "s2_fail_rate": n_fail / max(n_tot, 1)}
    return agg
