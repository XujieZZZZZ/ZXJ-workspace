# -*- coding: utf-8 -*-
"""指标计算(evaluation-guide.md 的公式逐一落地,纯数值,无 I/O)。

含:R/P/Jaccard、Recency Ratio、时间分布 W1(CDF 差的精确积分)、
类内密度/类间质心相似度/Observation 贴合度、平均对数引用量、顶会占比。
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from embedder import cosine  # 复用归一化点积实现


# --------------------------------------------------------------------------- #
# 1.2 相关工作硬性检索指标
# --------------------------------------------------------------------------- #
def retrieval_metrics(matched: int, n_h: int, n_l: int) -> dict:
    """R=|S_M|/|S_H|, P=|S_M|/|S_L|, J=|S_M|/|S_H ∪ S_L|(集合含重复去重后)。"""
    union = max(n_h + n_l - matched, 1)
    return {
        "recall": matched / n_h if n_h else 0.0,          # R
        "precision": matched / n_l if n_l else 0.0,       # P
        "jaccard": matched / union,                       # J
        "matched": matched, "n_h": n_h, "n_l": n_l,
    }


# --------------------------------------------------------------------------- #
# 1.3.1 时间分布
# --------------------------------------------------------------------------- #
def recency_ratio(years: Sequence[Optional[int]], current: int = None,
                  window: int = 3) -> Tuple[float, int]:
    """近 N 年论文占比 RR(S)=|{p: current-Year_p <= N}|/|S|。

    年份缺失的论文无法判定,直接不计入分子但留在分母?——按指南公式分母=|S|,
    缺失年份论文视为不满足(计为非近期)处理,返回 (RR, 有年份论文数) 供解读。
    """
    if current is None:
        from config import CURRENT_YEAR
        current = CURRENT_YEAR
    ys = [int(y) for y in years if y is not None]
    n = max(len(years), 1)
    recent = sum(1 for y in ys if current - y <= window)
    return recent / n, len(ys)


def w1_cdf_distance(years_a: Sequence[Optional[int]],
                    years_b: Sequence[Optional[int]]) -> Tuple[float, int, int]:
    """一维 Wasserstein(W1):两经验 CDF 之差的积分 ∫|F_A(x)-F_B(x)|dx。

    对离散年份精确分段积分(样本量不等亦可),等价于等样本时同序统计量
    均值绝对差。缺失年份从分布中剔除并返回各自有效数(报告中注明覆盖率)。
    """
    a = sorted(int(y) for y in years_a if y is not None)
    b = sorted(int(y) for y in years_b if y is not None)
    if not a or not b:
        return float("nan"), len(a), len(b)
    na, nb = len(a), len(b)
    # CDF 变化只发生在各观测年份处;分段端点取 [min-1, max+1]
    lo, hi = min(a[0], b[0]) - 1, max(a[-1], b[-1]) + 1
    # 构造 F(x) 在整点右侧的取值即可:以所有观测年份为断点逐段积分
    breaks = sorted(set(a) | set(b))
    fa = fb = 0.0
    total = 0.0
    prev_x = lo
    ia = ib = 0
    for x in breaks + [hi]:
        total += abs(fa - fb) * (x - prev_x)   # 区间 [prev_x, x) 内 CDF 恒定
        while ia < na and a[ia] == x:
            fa += 1.0 / na; ia += 1
        while ib < nb and b[ib] == x:
            fb += 1.0 / nb; ib += 1
        prev_x = x
    return total, na, nb


# --------------------------------------------------------------------------- #
# 1.3.2 语义结构与聚类差异(输入为行归一化向量矩阵或向量列表)
# --------------------------------------------------------------------------- #
def _to_mat(vecs) -> np.ndarray:
    m = np.asarray(vecs, dtype=np.float32)
    if m.ndim == 1:
        m = m.reshape(1, -1)
    return m


def intra_class_density(vecs) -> float:
    """类内语义聚焦度:所有论文向量两两余弦的均值( |S|<=1 时记 NaN)。"""
    m = _to_mat(vecs)
    n = m.shape[0]
    if n < 2:
        return float("nan")
    sims = m @ m.T
    iu = np.triu_indices(n, k=1)
    return float(sims[iu].mean())


def inter_centroid_similarity(vecs_a, vecs_b) -> float:
    """类间质心余弦 Sim_inter=cos(mean A, mean B)。"""
    a, b = _to_mat(vecs_a), _to_mat(vecs_b)
    if a.shape[0] == 0 or b.shape[0] == 0:
        return float("nan")
    return float(cosine(a.mean(axis=0), b.mean(axis=0)))


def relevance_to_observation(vecs, v_obs) -> float:
    """Observation 贴合度 Rel(S,Obs)=mean_p cos(v_p, v_obs)。"""
    m = _to_mat(vecs)
    if m.shape[0] == 0:
        return float("nan")
    return float((m @ np.asarray(v_obs, dtype=np.float32)).mean())


# --------------------------------------------------------------------------- #
# 1.3.3 客观学术质量
# --------------------------------------------------------------------------- #
def mean_log_citations(citation_counts: Sequence[Optional[int]]) -> Tuple[float, int]:
    """平均对数引用量 MLC=mean ln(1+c);无引用记录的论文剔除并返回有效数。"""
    cs = [float(c) for c in citation_counts if c is not None and not math.isnan(c)]
    if not cs:
        return float("nan"), 0
    return float(np.mean([math.log1p(c) for c in cs])), len(cs)


def top_venue_ratio(top_flags: Sequence[bool]) -> Tuple[float, int]:
    """顶会顶刊占比 TVR(名册匹配结果在调用侧给出,这里只汇总)。"""
    if not top_flags:
        return float("nan"), 0
    return float(np.mean([1.0 if f else 0.0 for f in top_flags])), len(top_flags)


if __name__ == "__main__":  # 自检
    assert abs(recency_ratio([2023, 2024, 2025, 2000], current=2026, window=3)[0] - 0.75) < 1e-9
    # W1: 等样本且同序时等于同序统计量均值绝对差
    a = [2000, 2005, 2010, 2015, 2020]
    b = [2001, 2006, 2011, 2016, 2021]
    w1, _, _ = w1_cdf_distance(a, b)
    assert abs(w1 - 1.0) < 1e-6, w1
    assert abs(w1_cdf_distance(a, a)[0]) < 1e-12
    assert abs(mean_log_citations([0, 1, 2])[0] - math.log1p(0)) < 1.1
    assert math.isnan(mean_log_citations([None])[0])
    v = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    assert abs(intra_class_density(v) - 1 / 3) < 1e-5
    assert abs(inter_centroid_similarity(v[:1], v[1:2]) - 1.0) < 1e-5
    assert abs(relevance_to_observation(v[:1], [1.0, 0.0]) - 1.0) < 1e-5
    print("metrics_calc self-check OK")
