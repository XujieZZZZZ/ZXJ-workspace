# -*- coding: utf-8 -*-
"""RQ2-1 评测入口:python run_rq2_1.py [--limit N] [--redo] [--backend qwen|glm] [--workers M]

流水线:
  S2 实体解析(缓存/续跑) -> 论文/文本向量(缓存) -> 逐样本三级匹配与全部指标
  -> DeBERTa-NLI 忠实度 -> LLM 裁判(原子拆解/支持判定/G-Eval,断点续跑)
  -> 输出报告 outputs/reports/rq2_1_{withsearch|withoutsearch}.md + .json(与控制台摘要)
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, List, Optional

import config
import dataio
import rq2_1 as r21
from embedder import Specter2Embedder
from judge import JudgeLLM, JsonlStore, run_judge_tasks
from nli import NliScorer
from report import banner, fmt, md_section, md_table, pct, write_json, write_text
from s2_client import S2Client, S2_CACHE_FILE
from utils import log

JUDGE_SUBDIR = config.JUDGE_DIR / "rq2_1"


def _store(kind: str) -> JsonlStore:
    return JsonlStore(JUDGE_SUBDIR / f"{kind}.jsonl")


# --------------------------------------------------------------------------- #
def resolve_stage(pdf_ids: List[str], redo_s2: bool, workers_s2: int) -> Dict[str, dict]:
    if redo_s2 and S2_CACHE_FILE.exists():
        S2_CACHE_FILE.unlink()
        log("S2 缓存已清空(--redo-s2),将重新解析")
    s2 = S2Client(api_key=config.S2_API_KEY, cache_file=S2_CACHE_FILE,
                  workers=workers_s2)
    return r21.resolve_pool(s2, pdf_ids=pdf_ids)


def _doc_metrics(pdf_id: str, variant: str, res: Dict[str, dict],
                 emb: Specter2Embedder) -> dict:
    """计算一个样本的 RQ2-1 数值指标(不含 claim 三件套)。"""
    doc_h = dataio.load_doc(dataio.SET_GT, pdf_id)
    doc_l = dataio.load_doc(variant, pdf_id)
    vecs = r21.build_vectors(doc_h, doc_l, res, emb, doc_h["observation"])
    mat = r21.match_levels(doc_h, doc_l, res, vecs)
    rec = r21.paper_metrics(doc_h, doc_l, res, vecs, mat, variant, pdf_id)
    rec["match_detail"] = {"cnt": mat["cnt"], "n_h": mat["n_h"], "n_l": mat["n_l"],
                           "matched_l_idx": mat["matched_l"],
                           "l_titles_matched": [mat["l_titles"][j] for j in mat["matched_l"]]}
    return rec


def claim_judge_stage(pdf_ids: List[str], variant: str, judge: JudgeLLM,
                      redo: bool, workers: int) -> None:
    """原子拆解(仅 GT,两变体共享)与支持判定、G-Eval 逻辑分。"""
    # 1) 原子拆解(GT claims) — decompose 任务与 variant 无关,统一 key 避免重复
    dec_store = _store("decompose")
    dec_items = []
    for pdf_id in pdf_ids:
        doc_h = dataio.load_doc(dataio.SET_GT, pdf_id)
        dec_items.append({"_key": f"{pdf_id}|decompose",
                          "claims": dataio.all_claims(doc_h)})
    run_judge_tasks(dec_items, "atomic_decompose", judge, dec_store,
                    redo=redo, workers=workers, desc=f"atomic-decompose")
    # 2) 支持判定 + G-Eval(variant 相关)
    sup_items, logic_items = [], []
    for pdf_id in pdf_ids:
        doc_h = dataio.load_doc(dataio.SET_GT, pdf_id)
        doc_l = dataio.load_doc(variant, pdf_id)
        dec = dec_store.get(f"{pdf_id}|decompose")
        atoms = (dec or {}).get("result", {}).get("atomic_assertions", []) \
            if dec and dec.get("ok") else []
        sup_items.append({"_key": f"{pdf_id}|{variant}|support",
                          "model_claims": " ".join(dataio.all_claims(doc_l)),
                          "atoms": atoms})
        logic_items.append({"_key": f"{pdf_id}|{variant}|logic",
                            "obs": doc_h["observation"],
                            "claims_text": " ".join(dataio.all_claims(doc_l))})
    run_judge_tasks(sup_items, "support_check", judge, _store("support"),
                    redo=redo, workers=workers, desc=f"support:{variant}")
    run_judge_tasks(logic_items, "logic_score", judge, _store("logic"),
                    redo=redo, workers=workers, desc=f"logic:{variant}")


def nli_stage(pdf_ids: List[str], variant: str, res: Dict[str, dict]) -> Dict[str, dict]:
    nli = NliScorer()
    out = {}
    for pdf_id in pdf_ids:
        doc_l = dataio.load_doc(variant, pdf_id)
        out[pdf_id] = r21.faithfulness_blocks(doc_l, res, nli)
    return out


# --------------------------------------------------------------------------- #
def run(pdf_ids: List[str], redo_s2: bool = False, redo_judge: bool = False,
        workers_llm: int = None, workers_s2: int = 2,
        backend: Optional[str] = None, emb_name: str = config.EMB_DEFAULT) -> None:
    config.ensure_dirs()
    t0 = time.time()
    log(f"RQ2-1 开始,样本数: {len(pdf_ids)}")

    # 0) --redo:统一清空 LLM 裁判缓存一次(此后各变体以续跑方式复用同一 store,
    #    避免循环内多次 unlink 导致前一变体结果被后一调用清掉)
    if redo_judge:
        import shutil
        if JUDGE_SUBDIR.exists():
            shutil.rmtree(JUDGE_SUBDIR)
            log("LLM 裁判缓存已清空(--redo)")
        redo_judge = False

    # 1) S2 解析(全局缓存;仅首次/--redo 时联网)
    cache_hits = S2_CACHE_FILE.exists()
    res = resolve_stage(pdf_ids, redo_s2, workers_s2)
    if redo_s2:
        log("S2 解析已重新执行(--redo)")
    elif not cache_hits:
        log("S2 解析完成(首次执行)")

    # 3) 逐变体逐样本数值指标(论文/观察向量在指标计算中按需编码并落盘缓存)
    judge = JudgeLLM(backend=backend)
    _spec = config.EMB_CHOICES[emb_name]
    emb = Specter2Embedder(model_dir=_spec[0],
                           name=None if emb_name == config.EMB_DEFAULT else emb_name,
                           adapter_dir=_spec[2], pooling=_spec[3])
    log(f"语义编码器: {emb_name} = {config.EMB_CHOICES[emb_name][1]} (缓存目录: {emb.emb_dir})")
    all_rows: Dict[str, list] = {}
    for variant in dataio.RW_VARIANTS:
        log(f"[{variant}] 计算文档级指标…")
        rows = []
        for pdf_id in pdf_ids:
            rec = _doc_metrics(pdf_id, variant, res, emb)
            rows.append(rec)
            log(f"  {pdf_id}: R={rec['retrieval']['recall']:.2%} "
                f"P={rec['retrieval']['precision']:.2%} matched={rec['retrieval']['matched']}")
        all_rows[variant] = rows
        # 4) claim 评测(LLM 裁判缓存复用 + NLI 本地重算;与编码器无关的部分保持一致)
        claim_judge_stage(pdf_ids, variant, judge, redo_judge, workers_llm or config.LLM_WORKERS)
        nli_out = nli_stage(pdf_ids, variant, res)
        # 5) 组装每样本记录(指标 + claim 指标)
        for rec in rows:
            pid = rec["pdf_id"]
            _fill_claim_metrics(rec, pid, variant, nli_out.get(pid))
    log("各变体文档指标计算完成")

    # 6) 输出报告(默认编码器沿用原文件名;其他编码器加 _emb_{name} 后缀,不覆盖旧结果)
    for variant in dataio.RW_VARIANTS:
        rows = all_rows[variant]
        agg = r21.aggregate(rows)
        _write_report(variant, rows, agg, emb_name)
    log(f"RQ2-1 完成,耗时 {time.time() - t0:.0f}s,"
        f"LLM usage: {judge.usage()}")
    for variant in dataio.RW_VARIANTS:
        rows = all_rows[variant]
        agg = r21.aggregate(rows)
        _console_summary(variant, rows, agg, emb_name)


def _fill_claim_metrics(rec: dict, pdf_id: str, variant: str,
                        nli_out: Optional[dict]) -> None:
    """读取裁判/本地结果,填回样本记录(含 Coverage / Logic / Faithfulness)。"""
    claims = {"faithfulness": (nli_out or {}).get("faithfulness"),
              "n_nli_pairs": (nli_out or {}).get("n_pairs", 0)}
    dec = _store("decompose").get(f"{pdf_id}|decompose")
    atoms = []
    if dec and dec.get("ok"):
        atoms = dec["result"].get("atomic_assertions", [])
    claims["n_atoms"] = len(atoms)
    sup = _store("support").get(f"{pdf_id}|{variant}|support")
    if sup and sup.get("ok"):
        verdicts = sup["result"].get("verdicts", [])
        covered = sum(1 for v in verdicts if v.get("supported") == 1)
        claims["coverage"] = covered / len(verdicts) if verdicts else None
        claims["n_supported"] = covered
    else:
        claims["coverage"] = None
    logic = _store("logic").get(f"{pdf_id}|{variant}|logic")
    claims["logic"] = (logic or {}).get("result", {}).get("score") if logic and logic.get("ok") else None
    rec["claim"] = claims


# --------------------------------------------------------------------------- #
def _write_report(variant: str, rows: List[dict], agg: dict,
                  emb_name: str = config.EMB_DEFAULT) -> None:
    tag = "" if emb_name == config.EMB_DEFAULT else f"_emb_{emb_name}"
    out = [f"# RQ2-1 评估报告:LLM 生成 Related Work(变体: {variant})\n",
           f"- 样本数: {len(rows)}(论文 Observation → LLM 相关工作 S_L vs 人类 S_H)\n"
           f"- 语义编码器: {config.EMB_CHOICES[emb_name][1]}(--emb {emb_name});"
           "向量缓存与输出按编码器隔离,不覆盖其他编码器的结果\n"
           "- 指标定义与公式:见 evaluation-guide.md 第一节;计算口径详见 README-评测说明.md\n"]
    # 1.1 实体解析/检索失败率(H 与 L 两侧都统计;检索不到视为编造/失败,仅供参考)
    h = ["样本", "|S_H|", "S2未找到(H)", "H 失败率", "|S_L|", "S2未找到(L)", "L 失败率"]
    body = md_table(h, [[r["pdf_id"],
                         r["failure"]["H"]["total"], r["failure"]["H"]["s2_fail"],
                         pct(r["failure"]["H"]["s2_fail_rate"]),
                         r["failure"]["L"]["total"], r["failure"]["L"]["s2_fail"],
                         pct(r["failure"]["L"]["s2_fail_rate"])] for r in rows])
    def _mean_std(vals):
        """非缺失样本的均值/标准差;返回 (mean, std, n)。"""
        vs = [v for v in vals if v is not None]
        n = len(vs)
        if not n:
            return (None, None, 0)
        m = sum(vs) / n
        sd = (sum((v - m) ** 2 for v in vs) / n) ** 0.5
        return (m, sd, n)
    if "H" in agg.get("failure", {}):   # 跨样本合计行 + 每样本均值
        fh, fl = agg["failure"]["H"], agg["failure"]["L"]
        hm, hs, _ = _mean_std([r["failure"]["H"]["s2_fail_rate"] for r in rows])
        lm, ls, _ = _mean_std([r["failure"]["L"]["s2_fail_rate"] for r in rows])
        body += "\n\n**合计(全部样本)**: H 侧 {h_fail}/{h_tot}({h_rate});L 侧 {l_fail}/{l_tot}({l_rate})".format(
            h_fail=fh["n_fail"], h_tot=fh["n_total"], h_rate=pct(fh["s2_fail_rate"]),
            l_fail=fl["n_fail"], l_tot=fl["n_total"], l_rate=pct(fl["s2_fail_rate"]))
        body += ("\n\n**每样本失败率平均(mean±std)**: "
                 "H 侧 {hm}±{hs};L 侧 {lm}±{ls}").format(
            hm=pct(hm), hs=pct(hs), lm=pct(lm), ls=pct(ls))
    out.append(md_section("1.1 S2 实体解析与检索失败率(H/L 两侧;检索不到视为编造/失败,仅供参考)",
                          body))
    # 1.2 检索指标
    h = ["样本", "Recall(R)", "Precision(P)", "Jaccard", "|S_M|"]
    body = md_table(h, [[r["pdf_id"], pct(r["retrieval"]["recall"]),
                         pct(r["retrieval"]["precision"]),
                         fmt(r["retrieval"]["jaccard"]), r["retrieval"]["matched"]]
                        for r in rows])
    if "recall" in agg["retrieval"]:   # 聚合行
        body += "\n\n**聚合(mean±std)**\n\n" + md_table(
            h, [["mean", pct(agg["retrieval"]["recall"]["mean"]),
                 pct(agg["retrieval"]["precision"]["mean"]),
                 fmt(agg["retrieval"]["jaccard"]["mean"]),
                 fmt(agg["retrieval"]["matched"]["mean"])],
                ["std", fmt(agg["retrieval"]["recall"]["std"]),
                 fmt(agg["retrieval"]["precision"]["std"]),
                 fmt(agg["retrieval"]["jaccard"]["std"]),
                 fmt(agg["retrieval"]["matched"]["std"])]])
    out.append(md_section("1.2 相关工作硬性检索指标", body))
    # 1.3 分布/语义/质量
    h = ["样本", "RR(H)", "RR(L)", "W1(年份)", "类内(H)", "类内(L)", "类间", "Rel(H)", "Rel(L)",
         "MLC(H)", "MLC(L)", "TVR(H)", "TVR(L)"]
    def rrow(r):
        return [r["pdf_id"], pct(r["temporal"]["rr_h"]), pct(r["temporal"]["rr_l"]),
                fmt(r["temporal"]["w1"]), fmt(r["semantic"]["intra_h"]), fmt(r["semantic"]["intra_l"]),
                fmt(r["semantic"]["inter"]), fmt(r["semantic"]["rel_h"]), fmt(r["semantic"]["rel_l"]),
                fmt(r["quality_h"]["mlc"]), fmt(r["quality_l"]["mlc"]),
                pct(r["quality_h"]["tvr"]), pct(r["quality_l"]["tvr"])]
    # 1.3 表 + 聚合行(mean±std,基于全部 8 样本;std 以小数显示,同 1.2 惯例)
    a = agg
    body13 = md_table(h, [rrow(r) for r in rows])
    if "rr_h" in a.get("temporal", {}):
        agg13 = [["mean"] +
                 [pct(a["temporal"]["rr_h"]["mean"]), pct(a["temporal"]["rr_l"]["mean"]),
                  fmt(a["temporal"]["w1"]["mean"]),
                  fmt(a["semantic"]["intra_h"]["mean"]), fmt(a["semantic"]["intra_l"]["mean"]),
                  fmt(a["semantic"]["inter"]["mean"]), fmt(a["semantic"]["rel_h"]["mean"]),
                  fmt(a["semantic"]["rel_l"]["mean"]),
                  fmt(a["quality_h"]["mlc"]["mean"]), fmt(a["quality_l"]["mlc"]["mean"]),
                  pct(a["quality_h"]["tvr"]["mean"]), pct(a["quality_l"]["tvr"]["mean"])],
                 ["std"] +
                 [fmt(a["temporal"]["rr_h"]["std"]), fmt(a["temporal"]["rr_l"]["std"]),
                  fmt(a["temporal"]["w1"]["std"]),
                  fmt(a["semantic"]["intra_h"]["std"]), fmt(a["semantic"]["intra_l"]["std"]),
                  fmt(a["semantic"]["inter"]["std"]), fmt(a["semantic"]["rel_h"]["std"]),
                  fmt(a["semantic"]["rel_l"]["std"]),
                  fmt(a["quality_h"]["mlc"]["std"]), fmt(a["quality_l"]["mlc"]["std"]),
                  fmt(a["quality_h"]["tvr"]["std"]), fmt(a["quality_l"]["tvr"]["std"])]]
        body13 += ("\n\n**聚合(mean±std)**\n\n"
                   + md_table(h, [rrow(r) for r in rows] + agg13)
                   + "\n\n*注:mean/std 为全部 8 样本的均值与总体标准差;std 以小数形式显示。*")
    out.append(md_section("1.3 时间分布 / 语义结构 / 客观质量", body13))
    # 1.4 claim
    h = ["样本", "Faithfulness(NLI)", "NLI对", "原子数", "Coverage", "逻辑分(1-5)"]
    t = md_table(h, [[r["pdf_id"], fmt(r["claim"]["faithfulness"]), r["claim"]["n_nli_pairs"],
                      r["claim"]["n_atoms"], pct(r["claim"]["coverage"]),
                      fmt(r["claim"]["logic"], 1)] for r in rows])
    # 1.4 聚合行(mean±std;Faithfulness 剔除缺失样本并注明 N)
    fms = _mean_std([r["claim"]["faithfulness"] for r in rows])
    nps = _mean_std([r["claim"]["n_nli_pairs"] for r in rows])
    nts = _mean_std([float(r["claim"]["n_atoms"]) for r in rows])
    cms = _mean_std([r["claim"]["coverage"] for r in rows])
    lms = _mean_std([r["claim"]["logic"] for r in rows])
    t += "\n\n**聚合(mean±std;缺失样本剔除后计算)**\n\n" + md_table(
        h, [["mean", fmt(fms[0]) if fms[0] is not None else "-", fmt(nps[0], 2),
             fmt(nts[0], 2), pct(cms[0]), fmt(lms[0], 2)],
            ["std", fmt(fms[1]) if fms[1] is not None else "-", fmt(nps[1], 2),
             fmt(nts[1], 2), fmt(cms[1], 2), fmt(lms[1], 2)]])
    if fms[2] != len(rows):
        t += f"\n\n*注:Faithfulness 均值基于 N={fms[2]}(剔除无有效 NLI 判定的样本);其余列基于 N=8。*"
    out.append(md_section("1.4 Core Claim 质量评估", t))
    write_text(config.REPORTS_DIR / f"rq2_1_{variant}{tag}.md", "\n".join(out))
    write_json(config.REPORTS_DIR / f"rq2_1_{variant}{tag}.json",
               {"variant": variant, "emb": emb_name, "per_sample": rows, "aggregate": agg})


def _console_summary(variant: str, rows: List[dict], agg: dict,
                     emb_name: str = config.EMB_DEFAULT) -> None:
    print(banner(f"RQ2-1 摘要 [变体: {variant}]  (完整报告: outputs/reports/rq2_1_{variant}.md)"))
    print(f"样本数 = {len(rows)}")
    def row(r):
        return ("  Recall {R:.1%}  Precision {P:.1%}  Jaccard {J:.3f}  |S_M|={M} |"
                " RR_L {rr:.1%}  W1 {w1:.2f} | MLC_L {ml:.2f}  TVR_L {tv:.1%} |"
                " Faith {f:.3f}  Coverage {c:.1%}  Logic {g:.1f}").format(
            R=r["retrieval"]["recall"], P=r["retrieval"]["precision"], J=r["retrieval"]["jaccard"],
            M=r["retrieval"]["matched"], rr=r["temporal"]["rr_l"], w1=r["temporal"]["w1"],
            ml=r["quality_l"]["mlc"], tv=r["quality_l"]["tvr"],
            f=r["claim"]["faithfulness"] or float("nan"),
            c=r["claim"]["coverage"] or float("nan"), g=r["claim"]["logic"] or float("nan"))
    for r in rows:
        print(" " + r["pdf_id"])
        print(row(r))
    print("-- 聚合 --")
    print(f"  Recall {pct(agg['retrieval']['recall']['mean'])}  Precision {pct(agg['retrieval']['precision']['mean'])}"
          f"  Jaccard {fmt(agg['retrieval']['jaccard']['mean'])}")
    print(f"  RR_L {pct(agg['temporal']['rr_l']['mean'])}  W1 {fmt(agg['temporal']['w1']['mean'])}"
          f"  | MLC_L {fmt(agg['quality_l']['mlc']['mean'])}  TVR_L {pct(agg['quality_l']['tvr']['mean'])}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="RQ2-1 相关工作生成能力评估")
    ap.add_argument("--limit", type=int, default=0, help="仅前 N 个样本(调试,默认全部)")
    ap.add_argument("--redo", action="store_true", help="重跑全部 LLM 裁判(默认断点续跑)")
    ap.add_argument("--redo-s2", action="store_true", help="重新执行 S2 解析(默认用缓存)")
    ap.add_argument("--backend", default=None, choices=["qwen", "deepseek", "glm"], help="LLM 后端")
    ap.add_argument("--emb", default=config.EMB_DEFAULT, choices=list(config.EMB_CHOICES),
                    help="语义编码器(specter2_base 保持既有结果;specter2/scibert 输出到新文件)")
    ap.add_argument("--workers", type=int, default=None, help="LLM 并发数")
    ap.add_argument("--workers-s2", type=int, default=2)
    args = ap.parse_args()
    pdfs = dataio.list_pdf_ids()
    if args.limit:
        pdfs = pdfs[:args.limit]
    run(pdfs, redo_s2=args.redo_s2, redo_judge=args.redo, workers_llm=args.workers,
        workers_s2=args.workers_s2, backend=args.backend, emb_name=args.emb)


if __name__ == "__main__":
    sys.exit(main())
