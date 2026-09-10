# -*- coding: utf-8 -*-
"""
====================================================
reorganize_dataset.py — RQ2,3 评测语料重组(零 LLM 调用,纯本地重组)
====================================================

作用(对应 README.md 内部逻辑第 4 步):
    把分散在 LLM_data 各子目录的零散产出(observation 存于 human_data、
    related works 存于 relatedworks_*、solution 存于 solution_*),
    按三种输入条件拼装成与 data/human_data/ 同构的完整 JSON
    （observation + related_works + solution + pdf_id/md_path 等元数据）,
    每篇一条、每条件一个文件夹：

      1) data/LLM_data/merged_llm_re_withsearch/    <pdf_id>.json
           human observation + LLM(withoutsearch) related works + solution(llm_re_withsearch)
      2) data/LLM_data/merged_llm_re_withoutsearch/ <pdf_id>.json
           human observation + LLM(withoutsearch) related works + solution(llm_re_withoutsearch)
      3) data/LLM_data/merged_human_re/             <pdf_id>.json
           human observation + human related works(归一化)          + solution(human_re)

    拼接规则（保证三条件可比、不跨篇串接）：
    - observation 一律取自 human_data/<pdf_id>.json（三份 solution 输入的人 obs 已审计一致）；
    - related_works 内嵌“模型实际所见”内容：
        * llm_re_* : 直接拷贝 relatedworks_* / <pdf_id>.json 的 related_works
          （其 works 本身只有 title + 第一作者，与生成时渲染一致）；
        * human_re  : 由 human_data 的 related_works 归一化而来 —— claims 原样，
          works 只保留 title + 第一作者（与 generate_solutions.py 的
          render_related_works 渲染一致，消除与 LLM-RW 条件的格式/信息量差）；
    - solution 取自对应 solution 文件；related_works_source / solution_source /
      style_exemplar_ids 等溯源字段一并保留，供后续追溯；
    - 拼接前逐项断言审计（obs 一致、task/mode 匹配、rw_source 指向正确），
      任一项不通过则跳过该条并报错，绝不静默乱拼。

    完成后把三个重组 JSON 的地址/状态回写原始 jsonl（追加新字段，不删旧字段）：
      merged_llm_re_withsearch_path / merged_llm_re_withsearch_status
      merged_llm_re_withoutsearch_path / merged_llm_re_withoutsearch_status
      merged_human_re_path / merged_human_re_status

输入:
    1) data/pdf_mapping.jsonl（唯一索引 pdf_id + 各阶段产出路径/状态）
    2) data/human_data/<pdf_id>.json
    3) data/LLM_data/relatedworks_with{search,outsearch}/<pdf_id>.json
    4) data/LLM_data/solution_llm_re/<pdf_id>_{with,without}search.json
    5) data/LLM_data/solution_human_re/<pdf_id>.json

用法:
    python reorganize_dataset.py              # 重组全部论文
    python reorganize_dataset.py --only <id>  # 只重组指定论文
    python reorganize_dataset.py --redo       # 忽略已有重组文件重新生成
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# 默认配置
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = SCRIPT_DIR / "data" / "pdf_mapping.jsonl"
DEFAULT_HUMAN_DIR = SCRIPT_DIR / "data" / "human_data"
DEFAULT_LLM_DIR = SCRIPT_DIR / "data" / "LLM_data"

# 三种条件：输出子目录名、RW 来源、solution 来源文件命名
CONDITIONS = {
    "llm_re_withsearch": {
        "out_dir": "merged_llm_re_withsearch",
        "rw_kind": "llm",
        "rw_subdir": "relatedworks_withsearch",      # RW 文件子目录（llm）
        "sol_subdir": "solution_llm_re",
        "sol_name": lambda pid: f"{pid}_withsearch.json",
    },
    "llm_re_withoutsearch": {
        "out_dir": "merged_llm_re_withoutsearch",
        "rw_kind": "llm",
        "rw_subdir": "relatedworks_withoutsearch",   # RW 文件子目录（llm）
        "sol_subdir": "solution_llm_re",
        "sol_name": lambda pid: f"{pid}_withoutsearch.json",
    },
    "human_re": {
        "out_dir": "merged_human_re",
        "rw_kind": "human",                          # human RW 取自 human_data, 落盘时归一化
        "sol_subdir": "solution_human_re",
        "sol_name": lambda pid: f"{pid}.json",
    },
}
# 回写 jsonl 的字段名（与输出目录命名一致）
COND_JSONL_KEYS = {
    "llm_re_withsearch": ("merged_llm_re_withsearch_path",
                          "merged_llm_re_withsearch_status"),
    "llm_re_withoutsearch": ("merged_llm_re_withoutsearch_path",
                             "merged_llm_re_withoutsearch_status"),
    "human_re": ("merged_human_re_path", "merged_human_re_status"),
}

# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


def load_json(path, what):
    p = Path(path)
    if not p.is_file():
        return None, f"{what} 不存在: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, f"{what} 解析失败 {p}: {e}"


def first_author_name(work):
    authors = work.get("authors") or []
    return authors[0] if authors else ""


def normalize_human_works(work):
    """human work -> {title, authors=[首作者]}（丢弃其余作者与年份等字段）"""
    return {"title": work.get("title", ""),
            "authors": [first_author_name(work)] if work.get("authors") else []}


def normalize_human_related_works(groups):
    """human related_works 归一化为模型所见形式：claims 原样、works 仅 title+首作者

    与 generate_solutions.py render_related_works 的语义一致，
    使合并产物中 human-RW 与 LLM-RW 两条件的数据结构/信息量对齐。
    """
    out = []
    for g in groups:
        ng = {"claims": list(g.get("claims", []))}
        works = g.get("works", [])
        ng["works"] = [normalize_human_works(w) for w in works] if works else []
        out.append(ng)
    return out


def build_merged(pdf_id, human_dir, llm_dir, cond, redo=False):
    """拼装单个条件的一份重组 JSON

    返回 (out_path, error)。内部逐项断言审计，不通过即返回错误、不落盘。
    """
    cfg = CONDITIONS[cond]
    human, err = load_json(human_dir / f"{pdf_id}.json", "human 数据")
    if human is None:
        return None, err

    # ---- 1) solution 文件 ----
    sol_file = (llm_dir / cfg["sol_subdir"]
                / cfg["sol_name"](pdf_id)).resolve()
    sol, err = load_json(sol_file, "solution 文件")
    if sol is None:
        return None, err

    # ---- 2) related works 来源（llm 版额外读 RW 文件） ----
    if cfg["rw_kind"] == "llm":
        rw_file = (llm_dir / cfg["rw_subdir"] / f"{pdf_id}.json").resolve()
        rw_rec, err = load_json(rw_file, "LLM related works 文件")
        if rw_rec is None:
            return None, err
        rw_groups = rw_rec.get("related_works")
        rw_source = str(rw_file)
    else:
        rw_groups = normalize_human_related_works(
            human.get("related_works", []))
        rw_source = str((human_dir / f"{pdf_id}.json").resolve())

    # ---- 3) 审计断言（保证不跨篇、不串条件） ----
    checks = {
        "solution.pdf_id": sol.get("pdf_id") == pdf_id,
        "solution.task": sol.get("task") == cond,
        "solution.observation 与 human 一致":
            sol.get("observation") == human.get("observation"),
        "rw 分组结构合法":
            isinstance(rw_groups, list) and rw_groups,
    }
    if cfg["rw_kind"] == "llm":
        checks["rw.mode"] = rw_rec.get("mode") in ("withsearch", "withoutsearch")
        checks["rw.pdf_id"] = rw_rec.get("pdf_id") == pdf_id
        checks["rw.observation 与 human 一致"] = \
            rw_rec.get("observation") == human.get("observation")
        checks["solution.related_works_source 指向所用 RW 文件"] = \
            sol.get("related_works_source") == rw_source
    sol_obj = sol.get("solution") or {}
    checks["solution.idea 非空"] = bool(
        isinstance(sol_obj.get("idea"), str) and sol_obj["idea"].strip())
    checks["solution.implementation 非空"] = bool(
        isinstance(sol_obj.get("implementation"), str)
        and sol_obj["implementation"].strip())

    bad = [name for name, ok in checks.items() if not ok]
    if bad:
        return None, (f"[{pdf_id}/{cond}] 审计不通过: "
                      + "; ".join(bad) + " —— 已拒绝拼接")

    # ---- 4) 组 JSON（字段顺序对齐 human_data：内容三件套在前） ----
    record = {
        "observation": human["observation"],
        "related_works": rw_groups,
        "solution": sol_obj,
        "pdf_id": pdf_id,
        "md_path": human.get("md_path", ""),
        "model": sol.get("model", ""),
        "generated_at": sol.get("generated_at", ""),
        # 溯源字段
        "task": cond,
        "related_works_source": rw_source,
        "solution_source": str(sol_file),
        "style_exemplar_ids": sol.get("style_exemplar_ids", []),
    }
    out_file = (llm_dir / cfg["out_dir"] / f"{pdf_id}.json").resolve()
    if out_file.is_file() and not redo:
        return str(out_file), None      # 已存在：幂等跳过（不覆盖）

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return str(out_file), None


# --------------------------------------------------------------------------
# 批量主入口
# --------------------------------------------------------------------------

def run_batch(cfg):
    jsonl_path = Path(cfg["jsonl_path"])
    human_dir = Path(cfg["human_dir"])
    llm_dir = Path(cfg["llm_dir"])

    if not jsonl_path.is_file():
        print(f"[ERROR] jsonl 文件不存在: {jsonl_path}")
        return None

    entries = []
    for lineno, line in enumerate(jsonl_path.read_text(encoding="utf-8")
                                  .splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[WARN] 第 {lineno} 行为损坏 JSON，原样保留并跳过")
            entries.append(line)

    done = ok = 0
    for e in entries:
        if not isinstance(e, dict) or not e.get("pdf_id"):
            continue
        pid = str(e["pdf_id"])
        if cfg["only"] and pid not in cfg["only"]:
            continue
        for cond in CONDITIONS:
            out_path, error = build_merged(
                pid, human_dir, llm_dir, cond, redo=cfg["redo"])
            done += 1
            if error:
                ok_path = None
                print(f"  [FAIL] {pid}/{cond}: {error}")
            else:
                ok += 1
                print(f"  [ OK ] {pid}/{cond} -> {out_path}")
                ok_path = out_path
            # 回写 jsonl：成功补 path/status，失败补 status=failed（旧 path 保留与否见下）
            path_key, status_key = COND_JSONL_KEYS[cond]
            if ok_path:
                e[path_key] = ok_path
                e[status_key] = "success"
            elif cfg["redo"] or path_key not in e:
                e[status_key] = "failed"     # 首次失败标记；redo 时清掉过期成功标记
                e.pop(path_key, None)
            # 非 redo 且文件已存在（幂等跳过成功）时上面的 status 已是 success

    # 原子化整体回写（dict 行重新序列化，损坏行原样保留）
    tmp = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            if isinstance(e, dict):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            else:
                f.write(str(e) + "\n")
    os.replace(tmp, jsonl_path)

    print(f"\n[Reorganize] 重组完成: {ok}/{done} 条成功")
    for cond, cfg_d in CONDITIONS.items():
        d = llm_dir / cfg_d["out_dir"]
        n = len(list(d.glob("*.json"))) if d.is_dir() else 0
        print(f"  {cfg_d['out_dir']}/ : {n} 份")
    return {"ok": ok, "total": done}


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="RQ2,3 评测语料重组：把 LLM_data 的零散产出拼装成 "
                    "human_data 同构 JSON（三条件三目录），并回写 pdf_mapping.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jsonl", "-j", default=str(DEFAULT_JSONL),
                        help=f"总 jsonl 路径（默认: {DEFAULT_JSONL}）")
    parser.add_argument("--human-dir", default=str(DEFAULT_HUMAN_DIR),
                        help=f"human 数据目录（默认: {DEFAULT_HUMAN_DIR}）")
    parser.add_argument("--llm-dir", default=str(DEFAULT_LLM_DIR),
                        help=f"LLM 数据根目录（默认: {DEFAULT_LLM_DIR}，"
                             f"其下新建 merged_*/ 子目录）")
    parser.add_argument("--only", action="append", default=None,
                        help="只重组指定唯一索引的论文，可多次指定")
    parser.add_argument("--redo", action="store_true",
                        help="忽略已存在的重组文件，重新生成并覆盖")
    args = parser.parse_args()

    cfg = {
        "jsonl_path": args.jsonl,
        "human_dir": args.human_dir,
        "llm_dir": args.llm_dir,
        "only": set(args.only) if args.only else None,
        "redo": args.redo,
    }
    result = run_batch(cfg)
    if result is None:
        return
    print(f"成功: {result['ok']} | 总计: {result['total']}")


if __name__ == "__main__":
    main()
