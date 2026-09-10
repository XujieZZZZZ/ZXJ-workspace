# -*- coding: utf-8 -*-
"""报告渲染:统一 Markdown 表格/文本与终端输出(README 要求:最终结果既输出又存文件)。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def fmt(v: Any, nd: int = 4) -> str:
    """数值格式化:None/NaN -> "-";保留 nd 位小数。"""
    if v is None:
        return "-"
    try:
        f = float(v)
        if f != f:            # NaN
            return "-"
        return f"{f:.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def pct(v: Any, nd: int = 1) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return str(v)


def md_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Markdown 表格(表头对齐为左对齐 + 分隔行)。"""
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def md_section(title: str, body: str, level: int = 2) -> str:
    return f"\n{'#' * level} {title}\n\n{body}"


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def banner(text: str) -> str:
    return "\n" + "=" * 78 + f"\n{text}\n" + "=" * 78
