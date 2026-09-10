# -*- coding: utf-8 -*-
"""RQ2-2:基于人类 Related Work 的 Solution 生成能力测评(指南第二节)。

输入 Observation + S_H -> LLM 生成 Sol_L(数据即 merged_human_re 的 solution);
GroundTruth Sol_H(人类 solution,来自 human_data)。
指标:1) 4 维 Rubric 打分 + 加权总分(均权 0.25);2) 语义嵌入相似度(SPECTER2 学术编码);
      3) 关键技术要素覆盖率 AspectRecall(Human Sol 抽取 K 要素 -> 判定 Sol_L 覆盖)。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import config
import dataio
from embedder import Specter2Embedder, cosine
from utils import truncate_chars


def sol_text_of(doc: dict, limit: int = 16000) -> str:
    idea = (doc.get("solution") or {}).get("idea") or ""
    impl = (doc.get("solution") or {}).get("implementation") or ""
    return truncate_chars(f"[Idea]\n{idea}\n\n[Implementation]\n{impl}", limit)


# --------------------------------------------------------------------------- #
# 任务清单构造(judge 执行入口在 runner)
# --------------------------------------------------------------------------- #
def rubric_items(pdf_id: str, set_key: str, doc_h: dict, doc_sol: dict) -> List[dict]:
    """对单个 solution 做四维 Rubric 独立打分(带其输入 RW 上下文)。"""
    rw_text = render_rw_for_judge(doc_sol)
    obs = doc_sol.get("observation") or ""
    return [{"_key": f"{pdf_id}|{set_key}|rubric",
             "obs": obs, "rw_text": rw_text,
             "sol_text": sol_text_of(doc_sol)}]


def render_rw_for_judge(doc: dict) -> str:
    """渲染 related_works 供评审(含 claims 与 works 标题/第一作者/年份)。"""
    lines = []
    for block in doc.get("related_works") or []:
        for c in block.get("claims") or []:
            lines.append(f"[Claim] {c}")
        for w in block.get("works") or []:
            auth = (w.get("authors") or [""])[0]
            yr = w.get("year")
            lines.append(f"  - {w.get('title', '')} ({auth}, {yr if yr else 'n/a'})")
    return "\n".join(lines)


def aspect_items(pdf_id: str, doc_gt: dict, doc_sol: dict) -> List[dict]:
    """构造:Human Sol 要素抽取 + Sol_L 覆盖判定 两个任务项。"""
    sol_h = sol_text_of(doc_gt)          # 人类 solution(作为抽取蓝本)
    sol_l = sol_text_of(doc_sol)         # LLM solution(判定对象)
    return [{"_key": f"{pdf_id}|aspect_extract", "sol_text": sol_h},
            {"_key": f"{pdf_id}|aspect_coverage", "sol_text": sol_l, "aspects": [],
             "_fill": "aspects_from_extract"}]


# --------------------------------------------------------------------------- #
# 语义相似度(本机 SPECTER2,无 LLM 调用)
# --------------------------------------------------------------------------- #
def semantic_similarity(doc_gt: dict, doc_sol: dict, emb: Specter2Embedder) -> float:
    """Sim_semantic = cos(v(Sol_H), v(Sol_L))(学术文本编码器,指南 2.2.1)。"""
    vh = emb.encode_cached(sol_text_of(doc_gt))
    vl = emb.encode_cached(sol_text_of(doc_sol))
    return float(cosine(vh, vl))


# --------------------------------------------------------------------------- #
# 汇总计算(裁判结果就绪后)
# --------------------------------------------------------------------------- #
def weighted_total(scores: Dict[str, int]) -> float:
    """综合质量得分 = Σ w_k s_k(默认均权 0.25)。"""
    w = config.SOL_WEIGHTS
    return float(sum(w[k] * scores.get(k, 0) for k in w))


def aspect_recall(coverage: List[dict], n_aspects: int) -> float:
    """AspectRecall = 被 Sol_L 覆盖的要素数 / K。"""
    if n_aspects <= 0:
        return float("nan")
    return sum(1 for c in coverage if c.get("addressed") == 1) / n_aspects
