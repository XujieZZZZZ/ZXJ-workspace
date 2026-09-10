# -*- coding: utf-8 -*-
"""数据加载层:统一读取 human_data 与 LLM_data/merged_* 四套评测样本。

口径(对应 data/README.md):
- S_H(GroundTruth related works / Sol_H) 取自 data/human_data/<pdf_id>.json(元数据完整);
- LLM 侧三套(Sol 输入相关工作的三个来源)取自 merged_* 目录:
    human_re        = Observation + Human RW            -> RQ2-2 的 Sol_L(也是 RQ2-3 的 Sol_Human_RW)
    llm_re_withsearch    = Observation + LLM RW(带检索)     -> RQ2-1 变体 A / RQ2-3 变体 A
    llm_re_withoutsearch = Observation + LLM RW(不带检索)   -> RQ2-1 变体 B / RQ2-3 变体 B
- 集合内按规范化标题去重(同一论文被多个段落重复引用只算一次)。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import config
from utils import norm_title

# 数据集合的语义标签与路径
SET_GT = "gt"                       # 人类数据
SET_HUMAN_RW = "human_re"           # LLM solution,输入人类 RW
SET_WS = "withsearch"               # LLM RW(带检索)及对应 solution
SET_WOS = "withoutsearch"           # LLM RW(不带检索)及对应 solution

DIR_BY_SET = {
    SET_GT: config.HUMAN_DATA_DIR,
    SET_HUMAN_RW: config.MERGED_HUMAN_RE_DIR,
    SET_WS: config.MERGED_WITHSEARCH_DIR,
    SET_WOS: config.MERGED_WITHOUTSEARCH_DIR,
}

# LLM 相关工作的两个变体(逐变体分别测评,evaluator/README.md 要求)
RW_VARIANTS = [SET_WS, SET_WOS]


def list_pdf_ids() -> List[str]:
    """返回全部样本 pdf_id(以 human_data 为准,四套目录同构)。"""
    return sorted(p.name[:-5] for p in config.HUMAN_DATA_DIR.glob("*.json")
                  if p.name != "extraction_log.json")


def load_doc(set_key: str, pdf_id: str) -> dict:
    """加载单个样本文件(json)。"""
    p = DIR_BY_SET[set_key] / f"{pdf_id}.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def doc_works(doc: dict) -> List[dict]:
    """平铺 related_works 段落内所有 works,并携带其所在段落的 claims 引用。

    返回 work 记录: {title, authors, year, block_idx, claims(所在段落 claims 列表)}
    """
    works: List[dict] = []
    for b_idx, block in enumerate(doc.get("related_works") or []):
        claims = block.get("claims") or []
        for w in block.get("works") or []:
            rec = {
                "title": (w.get("title") or "").strip(),
                "authors": list(w.get("authors") or []),
                "year": w.get("year"),
                "block_idx": b_idx,
                "claims": claims,
                "_norm": norm_title(w.get("title") or ""),
            }
            if rec["_norm"]:
                works.append(rec)
    return works


def unique_works(doc: dict) -> List[dict]:
    """文档内按规范化标题去重后的 works(集合语义)。"""
    seen: Dict[str, dict] = {}
    for w in doc_works(doc):
        seen.setdefault(w["_norm"], w)
    return list(seen.values())


def all_claims(doc: dict) -> List[str]:
    """该文档全部 claims(按段落顺序展平)。"""
    claims: List[str] = []
    for block in doc.get("related_works") or []:
        claims.extend(block.get("claims") or [])
    return claims


def collect_work_pool() -> List[dict]:
    """收集全部四套样本中的所有唯一论文(全局去重),供 S2 解析与向量编码统一调度。"""
    seen: Dict[str, dict] = {}
    for set_key in (SET_GT, SET_HUMAN_RW, SET_WS, SET_WOS):
        for pdf_id in list_pdf_ids():
            doc = load_doc(set_key, pdf_id)
            for w in doc_works(doc):
                key = w["_norm"]
                if key not in seen:
                    # 人类数据含完整 authors/year,优先作为解析候选元数据
                    seen[key] = {"title": w["title"], "authors": w["authors"],
                                 "year": w["year"], "set_keys": [set_key],
                                 "pdf_ids": [pdf_id]}
                else:
                    rec = seen[key]
                    rec["set_keys"].append(set_key)
                    rec["pdf_ids"].append(pdf_id)
                    if set_key == SET_GT:
                        rec["authors"], rec["year"] = w["authors"], w["year"]
    return list(seen.values())
