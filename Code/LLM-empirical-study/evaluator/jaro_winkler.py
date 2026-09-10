# -*- coding: utf-8 -*-
"""Jaro-Winkler 相似度纯 Python 实现(evaluation-guide.md Level-2 字符串匹配用)。

避免为单一指标引入第三方依赖(pyjarowinkler 等);实现为标准定义:
Jaro 相似度 -> 前 4 字符前缀增益加权的 Jaro-Winkler,输出区间 [0,1]。
"""
from __future__ import annotations


def _jaro(s1: str, s2: str) -> float:
    """Jaro 相似度:基于匹配窗口的字符匹配 + 换位惩罚。"""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_dist = max(len1, len2) // 2 - 1
    match_dist = max(match_dist, 0)

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    for i in range(len1):
        lo, hi = max(0, i - match_dist), min(i + match_dist + 1, len2)
        for j in range(lo, hi):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0

    # 统计换位(两串匹配字符序列中顺序不一致的对数/2)
    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    m = float(matches)
    return (m / len1 + m / len2 + (m - transpositions) / m) / 3.0


def jaro_winkler(s1: str, s2: str, prefix_scale: float = 0.1) -> float:
    """Jaro-Winkler 相似度(前缀增益,默认缩放 0.1)。

    注:输入串先做轻量规范化(去首尾空白),不做大小写/标点处理——
    标题的原始面貌由调用方决定(匹配判定中与 evaluation-guide.md 口径一致)。
    """
    s1, s2 = (s1 or "").strip(), (s2 or "").strip()
    j = _jaro(s1, s2)
    # 共同前缀长度(上限 4)
    prefix = 0
    for a, b in zip(s1, s2):
        if a == b:
            prefix += 1
            if prefix == 4:
                break
        else:
            break
    return j + prefix * prefix_scale * (1.0 - j)


if __name__ == "__main__":  # 最小自检(与公开标准值比对)
    assert abs(jaro_winkler("MARTHA", "MARHTA") - 0.961) < 0.002, jaro_winkler("MARTHA", "MARHTA")
    assert abs(jaro_winkler("DIXON", "DICKSONX") - 0.813) < 0.005, jaro_winkler("DIXON", "DICKSONX")
    assert abs(jaro_winkler("JELLYFISH", "SMELLYFISH") - 0.896) < 0.005
    assert jaro_winkler("", "abc") == 0.0
    assert jaro_winkler("same", "same") == 1.0
    print("jaro_winkler self-check OK")
