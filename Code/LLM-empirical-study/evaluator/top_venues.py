# -*- coding: utf-8 -*-
"""顶会顶刊判定(TVR 用,evaluation-guide.md 1.3-3):venue ∈ CCF-A/B 或 Core A*。

名册数据(data_refs/top_venues.json)来源:
1. 官方《中国计算机学会推荐国际学术会议和期刊目录(2022 更名版)》PDF(会议+期刊,A/B);
2. 公开整理的同一版 A 类会议清单(补充 PDF 解析漏网条目)。

匹配采用"归一化词集合包含 + 字符串包含"宽松规则,允许 S2 venue 串带
"Proceedings of the ..." 等前后缀。任何无法命中的 venue 都会被记入审计清单
(报告附录输出),供人工核查——宁可漏报(计为非顶会)也不误报;
Human / LLM 两侧共用同一名册与规则,指标对比公平。
注:个别以缩写形态出现(如 "IEEE Trans. Parallel Distrib. Syst.")的 venue 可能漏判,
此类字符串全部出现在审计附录中。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

import config
from utils import norm_title  # 复用规范化:小写 / 仅字母数字 / 折叠空白

_VENUE_CACHE: Optional[List[dict]] = None
_AUDIT: Dict[str, dict] = {}   # norm_venue -> {"venue": 原文, "contexts": [..]}


def _load() -> List[dict]:
    global _VENUE_CACHE
    if _VENUE_CACHE is None:
        with open(config.TOP_VENUES_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        for e in raw:
            e["_abbr_toks"] = set(norm_title(e["abbr"]).split())
            e["_name_toks"] = set(norm_title(e["name"]).split())
            e["_name_norm"] = norm_title(e["name"])
        _VENUE_CACHE = raw
    return _VENUE_CACHE


def _match(venue_norm: str, venue_toks: set, entry: dict) -> bool:
    """对单个名册条目的判定:
    1) 简称词集合 ⊆ venue 词集合(如 "IEEE INFOCOM" / "ACM SIGCOMM 2022")。
    2) 全称词集合互相包含(词数>=3,过滤 "Proceedings"/"of"/"the" 等前后缀噪声)。
    3) 归一化整串互相包含(长度>=8,兜底)。"""
    abbr_toks, name_toks = entry["_abbr_toks"], entry["_name_toks"]
    if abbr_toks and abbr_toks <= venue_toks:
        return True
    if len(name_toks) >= 3 and name_toks <= venue_toks:
        return True
    if len(venue_toks) >= 3 and venue_toks <= name_toks:
        return True
    name_norm = entry["_name_norm"]
    if len(name_norm) >= 8 and (name_norm in venue_norm or venue_norm in name_norm):
        return True
    return False


def top_venue_entry(venue: Optional[str]) -> Optional[dict]:
    """命中则返回名册条目(含 abbr/rank/type),未命中返回 None。"""
    if not venue:
        return None
    vn = norm_title(venue)
    if len(vn) < 4:
        return None
    vtoks = set(vn.split())
    for e in _load():
        if _match(vn, vtoks, e):
            return {"abbr": e["abbr"], "name": e["name"], "rank": e["rank"], "type": e["type"]}
    return None


def is_top_venue(venue: Optional[str]) -> bool:
    return top_venue_entry(venue) is not None


def audit_unmatched(venue: Optional[str], context: str = "") -> None:
    """记录未能命中的 venue 原文与上下文(报告附录输出,便于人工核查)。"""
    if not venue or is_top_venue(venue):
        return
    key = norm_title(venue)
    rec = _AUDIT.setdefault(key, {"venue": venue, "contexts": []})
    if context and context not in rec["contexts"]:
        rec["contexts"].append(context)


def audit_report() -> List[dict]:
    """返回审计条目列表(按 venue 原文排序)。"""
    return sorted(_AUDIT.values(), key=lambda r: r["venue"].lower())


if __name__ == "__main__":  # 自检
    cases = [
        ("Proceedings of the ACM SIGCOMM 2022 Conference", True),
        ("IEEE INFOCOM", True),
        ("2023 IEEE Symposium on Security and Privacy", True),
        ("IEEE/ACM Transactions on Networking", True),
        ("Networked Systems Design and Implementation", True),   # NSDI 全称的子集
        ("arXiv (Cornell University)", False),
        ("International Conference on Learning Representations", True),  # ICLR 全称
        ("", False),
    ]
    for v, want in cases:
        got = is_top_venue(v)
        print(f"top={str(got):5s} want={str(want):5s} | {v}")
        assert got == want, (v, got, want)
    print("top_venues self-check OK")
