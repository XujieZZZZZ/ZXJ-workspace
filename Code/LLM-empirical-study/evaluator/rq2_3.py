# -*- coding: utf-8 -*-
"""RQ2-3:LLM RW 与 Human RW 对 Solution 产出的影响对比与归因(指南第三节)。

成对双盲评估(位置对调消除 Position Bias):
  Order1 展示顺序 [Sol_LLM_RW, Sol_Human_RW];Order2 展示顺序 [Sol_Human_RW, Sol_LLM_RW]
  标签与内容绑定且两轮一致:LLM-RW 方案恒为标签 A,人类-RW 方案恒为标签 B
  (双盲靠"每轮是独立对话、标签任意"实现;两轮仅交换展示顺序)。
  每轮裁判输出偏好与两侧四维分;两轮偏好冲突 -> 该样本判 Tie。
  WinRate / Δ_k 采用两轮两侧分数均值(基于裁判分数,同口径);
  另以独立 Rubric(带 RW 上下文,与 RQ2-2 同口径)复算两侧绝对分作交叉验证。
归因:对三个假设(检索召回/贴合度传导/幻觉噪音)计算 RQ2-1 指标与 Δ 的
Spearman 等级相关(含双侧 p 值;N=8,报告注明解释力有限)。
withsearch / withoutsearch 两变体分别成卷。
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional

import numpy as np

import config
import dataio
from rq2_2 import sol_text_of
from utils import truncate_chars


def pairwise_items(pdf_id: str, variant: str, doc_llm: dict, doc_human_re: dict) -> List[dict]:
    """位置对调的两条成对判定任务(obs + 两个候选 solution,双盲)。

    两轮中 sol_llm 恒为标签 A、sol_hrw 恒为标签 B(标签与内容绑定),
    仅交换两方案在提示词中的展示先后顺序(build_pairwise 按 la 先输出)。
    """
    obs = doc_llm.get("observation") or ""
    sol_llm = sol_text_of(doc_llm)
    sol_hrw = sol_text_of(doc_human_re)
    return [
        {"_key": f"{pdf_id}|{variant}|pair|o1", "obs": obs,
         "sol_a": sol_llm, "sol_b": sol_hrw, "label_a": "A", "label_b": "B",
         "order": 1, "variant": variant, "pdf_id": pdf_id},
        # o2:展示顺序为 [sol_hrw(标签B), sol_llm(标签A)] -> 提示词按 la=B 先写 Candidate B
        {"_key": f"{pdf_id}|{variant}|pair|o2", "obs": obs,
         "sol_a": sol_hrw, "sol_b": sol_llm, "label_a": "B", "label_b": "A",
         "order": 2, "variant": variant, "pdf_id": pdf_id},
    ]


def resolve_outcome(o1: dict, o2: dict) -> str:
    """一致性判定:两轮偏好一致 -> 该偏好;冲突 -> Tie(指南 3.1.3)。

    注意:pairwise_items 中标签与内容绑定且两轮一致 —— preference "A" = Sol_LLM_RW、
    "B" = Sol_Human_RW(两轮仅交换展示顺序),故两轮按同一映射解释。
    勘误(2026-09-07):旧实现曾假定 "o2 中 LLM=B"(标签随顺序反转),与真实构造相反,
    导致 o2 偏好被反向解析:qwen 的位置倾向被误读成一致的 Win_LLM,deepseek 两轮一致的
    真实判定被误读成冲突 Tie。存储的逐轮判定(每轮 preference/四维分)本身有效,仅聚合解析有误。
    """
    p1 = o1["result"]["preference"]
    p2 = o2["result"]["preference"]

    def _side(p: str) -> str:
        return "Win_LLM" if p == "A" else ("Win_Human" if p == "B" else "Tie")

    w1, w2 = _side(p1), _side(p2)
    return w1 if w1 == w2 else "Tie"


def delta_from_pairwise(o1: dict, o2: dict) -> Dict[str, float]:
    """四维分差 Δ_k = mean over orders(Score_k(Sol_LLM_RW) - Score_k(Sol_Human_RW))。

    分数键路由(勿与偏好标签混淆):两轮提示词均指示 "Score Candidate {la} -> a_scores",
    o1 的 la=A(LLM)、o2 的 la=B(人类),裁判实测均遵循该映射(build_pairwise 以 la 先行),
    故按 JSON 键收纳后:o1.a_scores=LLM、o1.b_scores=人类、o2.a_scores=人类、o2.b_scores=LLM。
    """
    dims = ["targetedness", "feasibility", "novelty", "groundedness"]
    delta = {}
    for k in dims:
        # o1: a_scores=Sol_LLM_RW, b_scores=Sol_Human_RW;o2: a_scores=Sol_Human_RW, b_scores=Sol_LLM_RW
        llm1 = o1["result"]["a_scores"][k]
        hum1 = o1["result"]["b_scores"][k]
        llm2 = o2["result"]["b_scores"][k]
        hum2 = o2["result"]["a_scores"][k]
        delta[k] = ((llm1 - hum1) + (llm2 - hum2)) / 2.0
    delta["total"] = float(np.mean(list(delta.values())))
    return delta


def scores_from_pairwise(o1: dict, o2: dict) -> Dict[str, dict]:
    """返回两侧平均四维分(两轮均值)与加权总分,供报告细节展示。"""
    from rq2_2 import weighted_total
    dims = ["targetedness", "feasibility", "novelty", "groundedness"]
    llm_s, hum_s = {}, {}
    for k in dims:
        llm_s[k] = (o1["result"]["a_scores"][k] + o2["result"]["b_scores"][k]) / 2.0
        hum_s[k] = (o1["result"]["b_scores"][k] + o2["result"]["a_scores"][k]) / 2.0
    llm_s["total"], hum_s["total"] = weighted_total(llm_s), weighted_total(hum_s)
    return {"llm": llm_s, "human": hum_s}


# --------------------------------------------------------------------------- #
# 归因分析(Spearman)
# --------------------------------------------------------------------------- #
def spearman(xs: List[float], ys: List[float]) -> Optional[dict]:
    """Spearman 等级相关 ρ 与 p(去除 NaN;n<3 或输入恒定返回 None)。"""
    try:
        from scipy.stats import spearmanr
    except Exception:
        return None
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None
             and not (isinstance(x, float) and np.isnan(x))
             and not (isinstance(y, float) and np.isnan(y))]
    if len(pairs) < 3:
        return None
    xs_ = [p[0] for p in pairs]
    ys_ = [p[1] for p in pairs]
    # 任一输入恒定(如全部样本同分)时系数无定义,返回 None 而非告警
    if len(set(xs_)) < 2 or len(set(ys_)) < 2:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rho, p = spearmanr(xs_, ys_)
    if rho is None or (isinstance(rho, float) and np.isnan(rho)):
        return None
    return {"rho": float(rho), "p": float(p), "n": len(pairs)}


# 归因假设矩阵(指南 3.2):自变量来自 RQ2-1,因变量来自 RQ2-3
# y 使用完整维度名(与 delta_from_pairwise 的键一致):groundedness/targetedness/feasibility
HYPOTHESES = [
    {"name": "检索召回假说", "x": "recall", "y": "groundedness",
     "expect": "正相关(r_s>0):LLM 遗漏核心文献 -> Solution 失去继承性"},
    {"name": "贴合度传导假说", "x": "rel", "y": "targetedness",
     "expect": "正相关(r_s>0):相关工作偏离主题 -> 方案针对性差"},
    {"name": "幻觉/噪音干扰假说", "x": "halluc", "y": "feasibility",
     "expect": "负相关(r_s<0):幻觉文献误导 -> 方案不可行"},
]
