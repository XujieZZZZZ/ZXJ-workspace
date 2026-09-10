# -*- coding: utf-8 -*-
"""
====================================================
generate_solutions.py — RQ2,3 Solution 生成实验
====================================================

作用（对应 README.md 内部实现逻辑第 3 条，即 RQ2-2 / RQ2-3 的输入侧）：
    基于 human 的 observation 与两种来源的 related works，让 LLM 生成 solution
    （分两部分：idea = 思路/理由/内核思想，implementation = 具体实现）。三种输入：

      1) human observation + LLM(withoutsearch) related works
         -> data/LLM_data/solution_llm_re/<pdf_id>_withoutsearch.json
      2) human observation + LLM(withsearch)    related works
         -> data/LLM_data/solution_llm_re/<pdf_id>_withsearch.json
      3) human observation + human              related works
         -> data/LLM_data/solution_human_re/<pdf_id>.json

    提示词要求（与 README 一致）：
    - 每次输入时把其它论文的人类 idea / implementation 作为示例轮转给出
      （示例必须不属于本论文；示例只用于让模型学习相同的表示、风格、长度等，
       禁止参考其内容）；示例数量 --style-examples 控制（默认 2 篇，取目标论文
       之后第 1、2 篇，循环轮转）。
    - solution 分为 idea 与 implementation 两个字段，英文输出。
    - 对三种输入的提示词除 related works 内容不同外完全一致（不告知模型 RW 来源），
      保证 RQ2-3 只比较"RW 来源"这一变量。

    完成后把生成 json 的地址/状态回写原始 jsonl：
      solution_llm_re_withsearch_path / _status        （llm-RW=withsearch 版）
      solution_llm_re_withoutsearch_path / _status     （llm-RW=withoutsearch 版）
      solution_human_re_path / _status                 （human-RW 版）
      （_status: success=文件已生成路径有效 / failed=本次失败，另有 *_error）

输入：
    1) 总 jsonl：每行含唯一索引字段（如 pdf_id），如 data/pdf_mapping.jsonl
    2) human 数据目录（默认 data/human_data/）：<唯一索引>.json，内含 observation、
       related_works（claims 分组 + works[title/authors/year]）、solution{idea,implementation}
    3) LLM related works 目录（默认 data/LLM_data/relatedworks_withsearch 与
       relatedworks_withoutsearch）：<唯一索引>.json，内含 related_works 分组
       （claims + works[title, authors=[首作者]]）

输入归一化（保证两种 RW 来源格式一致，只比较来源差异）：
    相关工作中 claims 原样给出；works 一律只呈现 title + 第一作者（不带年份与
    其它作者），human 与 LLM 版本同格式。

功能特性：
    1. 断点续跑：对应输出文件已存在则跳过（--redo 强制重抽），跳过的同样回写 jsonl
    2. 严格 JSON 输出：思考模式 + json_object；结构不符合要求判失败不落盘
    3. 网络容错：429/5xx/超时指数退避重试
    4. 单篇某一输入缺失（如 LLM related works 未生成）时记为失败并回写原因，
       不阻塞其它论文

API 约定（DeepSeek OpenAI 兼容端点，已实测）：
    base_url : https://api.deepseek.com
    model    : deepseek-v4-flash
    思考模式 : "thinking": {"type": "enabled"}，返回 message.reasoning_content

依赖：
    pip install requests

用法示例：
    export DEEPSEEK_API_KEY=sk-xxxx

    # 三种输入全部生成（默认）
    python generate_solutions.py

    # 只生成某类
    python generate_solutions.py --types human_re,llm_re_withoutsearch

    # 控制范围与行为
    python generate_solutions.py --only 52875bf8ef4b3f8c
    python generate_solutions.py --style-examples 2
    python generate_solutions.py --redo
"""

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

import requests

# --------------------------------------------------------------------------
# 默认配置
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = SCRIPT_DIR / "data" / "pdf_mapping.jsonl"
DEFAULT_HUMAN_DIR = SCRIPT_DIR / "data" / "human_data"
DEFAULT_LLM_RW_DIR = SCRIPT_DIR / "data" / "LLM_data"
DEFAULT_OUT_BASE = SCRIPT_DIR / "data" / "LLM_data"

# 三种输入的目录/文件名（llm 版文件名带模式后缀，human 版不带）
TASK_OUT_DIRS = {
    "llm_re_withsearch": "solution_llm_re",
    "llm_re_withoutsearch": "solution_llm_re",
    "human_re": "solution_human_re",
}
LLM_RW_SOURCE_DIR = {          # llm_re 两种任务对应的 LLM related works 来源目录
    "llm_re_withsearch": "relatedworks_withsearch",
    "llm_re_withoutsearch": "relatedworks_withoutsearch",
}
# 回写 jsonl 的字段名（与 README 输出目录命名一致）
TASK_JSONL_KEYS = {
    "llm_re_withsearch": ("solution_llm_re_withsearch_path",
                          "solution_llm_re_withsearch_status",
                          "solution_llm_re_withsearch_error"),
    "llm_re_withoutsearch": ("solution_llm_re_withoutsearch_path",
                             "solution_llm_re_withoutsearch_status",
                             "solution_llm_re_withoutsearch_error"),
    "human_re": ("solution_human_re_path",
                 "solution_human_re_status",
                 "solution_human_re_error"),
}
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

INDEX_FIELD_CANDIDATES = ["pdf_id", "id", "doc_id", "paper_id"]

HTTP_RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY = 3
BACKOFF_BASE = 5.0
REQUEST_TIMEOUT = (15, 900)

# --------------------------------------------------------------------------
# 提示词（英文，严谨简洁；占位符：<<OBSERVATION>> / <<RELATED_WORKS>> /
#                        <<EXEMPLARS>>）
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a rigorous research assistant acting as a human expert who has just "
    "surveyed the related work of a research problem and now designs a solution for "
    "it. You must write the solution in two parts: idea and implementation. "
    "Reply with exactly one JSON object conforming to the required schema. "
    "No prose, no code fences, no preamble."
)

USER_PROMPT_TEMPLATE = """
You are given: (1) an observation — a phenomenon, empirical finding, or unmet need
that motivates a new research problem — and (2) a related-work review relevant to
that observation, composed of claims about prior work and the papers supporting
each claim. A human expert would use exactly these two inputs to design a solution.
Produce that solution now, in two parts: idea and implementation.

# Observation

<<OBSERVATION>>

# Related work (claims and supporting papers)

<<RELATED_WORKS>>

# Task requirements

- idea: the reasoning of the solution — diagnose why the prior approaches (as
  characterized by the claims) do not satisfy what the observation demands; state
  the direction you choose, its core insight, and why it resolves the observation;
  discuss the key design trade-offs and alternatives you considered and rejected.
- implementation: the concrete design, step by step — the components, algorithms,
  protocols, or mechanisms; the key parameters and their meaning; and how the parts
  fit together. Provide enough detail for another engineer to implement it.
- Grounding: build the solution strictly on the observation and on the provided
  related work. You may build on or adapt works from the list (referring to them by
  title), but do not add literature, citations, or works that are not in the
  provided related-work list, and do not invent their results.
- Do not claim any experimental measurements, evaluation numbers, or deployment
  results (none exist yet).
- Do not refer to "this paper" or any previously proposed solution of your own: the
  solution is being proposed for the first time here.
- Both parts must be in English, internally consistent, and directly responsive to
  the observation.

# Style examples

Below are solution excerpts (idea and implementation) written by human experts for
OTHER research problems. They are provided ONLY as style references: they show the
expected representation, structure, granularity, and overall length of the two
parts. Do NOT reuse their content, ideas, or technique choices.

<<EXEMPLARS>>

# Output format

Reply with a single JSON object only, in exactly this schema:

{
  "solution": {
    "idea": "string",
    "implementation": "string"
  }
}

All field contents must be in English.
"""

# --------------------------------------------------------------------------
# LLM API 客户端（OpenAI 风格 / DeepSeek 兼容端点，与其它脚本同一契约）
# --------------------------------------------------------------------------


class LLMClient:
    """OpenAI 风格 Chat Completions 客户端：思考模式 + 严格 JSON"""

    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    @staticmethod
    def _request_variants():
        return [
            {"thinking": {"type": "enabled"},
             "response_format": {"type": "json_object"}},
            {"thinking": {"type": "enabled"}},
            {},
        ]

    def chat(self, messages, max_tokens):
        """发送对话请求，返回 (回复文本, usage)"""
        payload_base = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        last_err = None
        for variant in self._request_variants():
            payload = dict(payload_base)
            payload.update(variant)
            for attempt in range(1, MAX_RETRY + 1):
                try:
                    resp = self.session.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        msg = data["choices"][0]["message"]
                        text = msg.get("content") or ""
                        finish = data["choices"][0].get("finish_reason")
                        if not text.strip():
                            if finish == "length":
                                raise RuntimeError(
                                    "回复被 max_tokens 截断且无有效输出"
                                    "（思考过程消耗了全部额度），请调大 --max-tokens")
                            raise RuntimeError("模型返回空内容（可能思考超长）")
                        if finish == "length":
                            raise RuntimeError(
                                "回复达到 max_tokens 上限被截断，请调大 --max-tokens")
                        return text, data.get("usage", {})
                    err_msg = resp.text[:500]
                    if resp.status_code == 400:
                        last_err = RuntimeError(
                            f"HTTP 400，尝试降级参数重试: {err_msg}")
                        break
                    if resp.status_code in HTTP_RETRY_STATUS:
                        last_err = RuntimeError(
                            f"HTTP {resp.status_code}: {err_msg}")
                    else:
                        raise RuntimeError(f"HTTP {resp.status_code}: {err_msg}")
                except requests.exceptions.RequestException as e:
                    last_err = RuntimeError(f"网络请求异常: {e}")
                time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)) + attempt)
        raise RuntimeError(f"请求失败: {last_err}")

    def close(self):
        self.session.close()


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


def extract_json_object(text):
    """鲁棒解析 JSON 对象（容忍代码块围栏与前后杂音）"""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, flags=re.S | re.I)
    if fence:
        t = fence.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"回复中找不到 JSON 对象: {t[:200]!r}")
    return json.loads(t[start:end + 1])


def validate_schema(obj, key):
    """校验结构：solution 必须含非空 idea 与 implementation"""
    err = lambda msg: (False, f"[{key}] 输出 JSON 结构不符合要求: {msg}")
    if not isinstance(obj, dict):
        return err("顶层必须是 JSON 对象")
    sol = obj.get("solution")
    if not isinstance(sol, dict):
        return err("solution 必须是对象")
    for field in ("idea", "implementation"):
        if not (isinstance(sol.get(field), str) and sol[field].strip()):
            return err(f"solution.{field} 必须为非空字符串")
    return True, ""


def load_jsonl(path):
    """读取 jsonl，返回 (entries, 警告列表)。entry 为 dict；损坏行保留原文 str。"""
    entries, warns = [], []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                warns.append(f"第 {lineno} 行为损坏 JSON，原样保留并跳过")
                entries.append(line)
    return entries, warns


def save_jsonl(path, entries):
    """原子化整体回写 jsonl（dict 行重新序列化，原样保留损坏行）"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            if isinstance(e, dict):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            else:
                f.write(str(e) + "\n")
    os.replace(tmp, path)


def load_json_file(path, what):
    """读取 json 文件，返回 (dict|None, 错误信息|None)"""
    p = Path(path)
    if not p.is_file():
        return None, f"{what} 不存在: {p}"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"{what} 解析失败 {p}: {e}"
    return d, None


def first_author_name(work):
    """取 work 的第一作者（缺省给空串）"""
    authors = work.get("authors") or []
    return authors[0] if authors else ""


def render_related_works(groups):
    """把 related_works 分组渲染为提示词文本：claims 原样 + works(title + 首作者)

    输入为 human 或 LLM 版本的分组结构均适用：works 一律只呈现 title 与第一作者
    （不带年份与其余作者），保证 human 与 LLM 两种输入格式一致。
    """
    blocks = []
    for gi, g in enumerate(groups, 1):
        lines = [f"[Group {gi}]"]
        for c in g.get("claims", []):
            lines.append(f"Claim: {c}")
        if g.get("works"):
            lines.append("Works:")
            for w in g["works"]:
                lines.append(f"- {w['title']} ({first_author_name(w)})")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_exemplars_text(exemplar_papers):
    """把各篇示例论文的人类 solution{idea,implementation} 转成风格示例文本

    exemplar_papers: [(pdf_id, human_dict), ...]
    """
    blocks = []
    for pid, human in exemplar_papers:
        blocks.append(
            f"Example from another paper (id: {pid}):\n"
            + json.dumps(human["solution"], ensure_ascii=False, indent=2))
    return "\n\n".join(blocks)


def build_messages(observation, rw_text, exemplar_text):
    """组装 system + user 消息（全英文；三种输入共用同一提示词模板）"""
    exemplars_block = (
        f"[Style examples (other papers' human solutions)]\n{exemplar_text}"
        if exemplar_text else
        "[No style examples available in this run; follow the schema above.]"
    )
    user_prompt = (USER_PROMPT_TEMPLATE
                   .replace("<<OBSERVATION>>", observation)
                   .replace("<<RELATED_WORKS>>", rw_text)
                   .replace("<<EXEMPLARS>>", exemplars_block))
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# --------------------------------------------------------------------------
# 统计与单任务生成
# --------------------------------------------------------------------------


class GenStats:
    def __init__(self):
        self.lock = Lock()
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.errors = {}      # "<task>/<pdf_id>" -> 错误信息
        self.tokens = {"in": 0, "out": 0, "reasoning": 0}

    def add_tokens(self, usage):
        with self.lock:
            try:
                self.tokens["in"] += usage.get("prompt_tokens", 0)
                self.tokens["out"] += usage.get("completion_tokens", 0)
                det = usage.get("completion_tokens_details", {}) or {}
                self.tokens["reasoning"] += det.get("reasoning_tokens", 0)
            except TypeError:
                pass


def generate_single(client, pdf_id, task, human, rw_groups, rw_source,
                    exemplar_ids, exemplar_text, out_file, max_tokens, stats):
    """单任务生成 solution → 校验 → 落盘

    task: llm_re_withsearch / llm_re_withoutsearch / human_re
    成功: (status, path, None)  失败: ("failed", None, error)
    """
    rw_text = render_related_works(rw_groups)
    messages = build_messages(human["observation"], rw_text, exemplar_text)
    try:
        text, usage = client.chat(messages, max_tokens=max_tokens)
        stats.add_tokens(usage)
        obj = extract_json_object(text)
    except Exception as e:
        return "failed", None, f"LLM 调用或解析失败: {e}"

    ok, err_msg = validate_schema(obj, f"{task}/{pdf_id}")
    if not ok:
        return "failed", None, err_msg

    record = {
        "pdf_id": pdf_id,
        "task": task,
        "observation": human["observation"],
        "related_works_source": rw_source,
        "style_exemplar_ids": exemplar_ids,
        "solution": obj["solution"],
        "model": client.model,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return "success", str(out_file.resolve()), None


# --------------------------------------------------------------------------
# 批量主入口
# --------------------------------------------------------------------------


def run_batch(cfg):
    jsonl_path = Path(cfg["jsonl_path"])
    human_dir = Path(cfg["human_dir"])
    llm_rw_dir = Path(cfg["llm_rw_dir"])
    out_base = Path(cfg["out_base"])

    if not jsonl_path.is_file():
        print(f"[ERROR] jsonl 文件不存在: {jsonl_path}")
        return None
    if not human_dir.is_dir():
        print(f"[ERROR] human 数据目录不存在: {human_dir}")
        return None

    entries, warns = load_jsonl(jsonl_path)
    for w in warns:
        print(f"  [WARN] {w}")

    sample = next((e for e in entries if isinstance(e, dict)), {})
    index_field = cfg.get("index_field")
    if not index_field:
        index_field = next(
            (k for k in INDEX_FIELD_CANDIDATES if k in sample), None)
    if not index_field:
        print(f"[ERROR] 无法在 jsonl 中探测到唯一索引字段，"
              f"请用 --index-field 指定")
        return None

    # 行号索引：pdf_id -> jsonl 行号列表（供结果回写）
    row_nos_by_pdf = {}
    for rno, e in enumerate(entries):
        if isinstance(e, dict) and e.get(index_field) is not None:
            row_nos_by_pdf.setdefault(str(e[index_field]), []).append(rno)

    # 结果回写原始 jsonl
    save_lock = Lock()

    def _backfill_jsonl(pdf_id, task, status, out_path, error):
        path_key, status_key, error_key = TASK_JSONL_KEYS[task]
        with save_lock:
            for rno in row_nos_by_pdf.get(pdf_id, []):
                e = entries[rno]
                if not isinstance(e, dict):
                    continue
                e[status_key] = status
                if status == "success":
                    e[path_key] = out_path
                    e.pop(error_key, None)
                else:
                    e.pop(path_key, None)      # 失败时不指向旧文件
                    e[error_key] = error
            save_jsonl(jsonl_path, entries)

    # 收集论文（pdf 顺序 + human 数据），供轮转示例
    papers = []          # [(pdf_id, human_dict)]
    for e in entries:
        if not isinstance(e, dict):
            continue
        idx = e.get(index_field)
        if idx is None:
            continue
        idx = str(idx)
        human, err = load_json_file(human_dir / f"{idx}.json", "human 抽取数据")
        if human is None:
            print(f"  [SKIP] {idx}: {err}")
            continue
        if not isinstance(human.get("observation"), str) \
                or not human["observation"].strip():
            print(f"  [SKIP] {idx}: human 数据缺少有效 observation")
            continue
        if not isinstance(human.get("related_works"), list) \
                or not isinstance(human.get("solution"), dict) \
                or "idea" not in human.get("solution", {}) \
                or "implementation" not in human.get("solution", {}):
            print(f"  [SKIP] {idx}: human 数据缺少 related_works / solution 字段")
            continue
        papers.append((idx, human))
    if not papers:
        print("[ERROR] 没有可用的 human 数据（请先运行 extract_paper_info.py）")
        return None

    m = len(papers)
    n_ex = max(0, min(cfg["style_examples"], m - 1))

    tasks = cfg["types"]
    client = LLMClient(api_key=cfg["api_key"],
                       base_url=cfg["base_url"], model=cfg["model"])
    stats = GenStats()

    print(f"[Config] jsonl 输入      : {jsonl_path.resolve()}")
    print(f"[Config] human 数据目录  : {human_dir.resolve()}")
    print(f"[Config] 任务类型        : {', '.join(tasks)}")
    print(f"[Config] 输出目录        : {out_base.resolve()}"
          f"（{TASK_OUT_DIRS['llm_re_withsearch']}/ 与 {TASK_OUT_DIRS['human_re']}/）")
    print(f"[Config] 风格示例轮转    : 每篇取其后 {n_ex} 篇的人类 solution"
          f"（示例不含本论文自身）")
    print(f"[Config] API 端点        : {cfg['base_url']}  模型: {cfg['model']}"
          f"（思考模式 + 严格 JSON）")
    print(f"[Config] max_tokens: {cfg['max_tokens']} | workers: {cfg['max_workers']}")

    # 待处理任务列表
    todo = []            # (pdf_id, task, human, rw_groups, rw_source, ex_ids, ex_text, out_file)
    planned = 0
    for i, (pdf_id, human) in enumerate(papers):
        if cfg["only"] and pdf_id not in cfg["only"]:
            continue
        if cfg["limit"] and planned >= cfg["limit"]:
            break
        planned += 1
        # 轮转示例：目标论文之后第 1..n_ex 篇（循环），必然 ≠ 本论文
        exemplar_papers = [papers[(i + k) % m] for k in range(1, n_ex + 1)]
        exemplar_ids = [pid for pid, _ in exemplar_papers]
        exemplar_text = build_exemplars_text(exemplar_papers)

        for task in tasks:
            if task == "human_re":
                rw_groups = human.get("related_works", [])
                rw_source = str((human_dir / f"{pdf_id}.json").resolve())
                out_file = out_base / TASK_OUT_DIRS[task] / f"{pdf_id}.json"
            else:   # llm_re_withsearch / llm_re_withoutsearch
                src = llm_rw_dir / LLM_RW_SOURCE_DIR[task] / f"{pdf_id}.json"
                llm_rw, err = load_json_file(src, "LLM related works")
                if llm_rw is None:
                    # 本地输入缺失：不调用 API，直接记为失败（重跑可恢复）
                    stats.failed += 1
                    stats.errors[f"{task}/{pdf_id}"] = err
                    _backfill_jsonl(pdf_id, task, "failed", None, err)
                    continue
                rw_groups = llm_rw.get("related_works", [])
                if not rw_groups:
                    stats.failed += 1
                    stats.errors[f"{task}/{pdf_id}"] = \
                        "LLM related works 内容为空"
                    _backfill_jsonl(pdf_id, task, "failed", None,
                                    "LLM related works 内容为空")
                    continue
                rw_source = str(src.resolve())
                out_file = (out_base / TASK_OUT_DIRS[task]
                            / f"{pdf_id}_{task.removeprefix('llm_re_')}.json")

            if not cfg["redo"] and Path(out_file).is_file():
                stats.skipped += 1
                _backfill_jsonl(pdf_id, task, "success",
                                str(Path(out_file).resolve()), None)
                continue
            todo.append((pdf_id, task, human, rw_groups, rw_source,
                         exemplar_ids, exemplar_text, out_file))

    if not todo:
        print("\n[WARN] 没有待处理任务（均已生成过；可用 --redo 强制重抽）")
    else:
        total = len(todo)
        done = 0

        def _work(t):
            pdf_id, task, human, rw_groups, rw_source, ex_ids, ex_text, of = t
            return (pdf_id, task, *generate_single(
                client, pdf_id, task, human, rw_groups, rw_source,
                ex_ids, ex_text, of, cfg["max_tokens"], stats))

        def _finish_one(res):
            nonlocal done
            pdf_id, task, status, out_path, error = res
            _backfill_jsonl(pdf_id, task, status, out_path, error)
            with stats.lock:
                if status == "success":
                    stats.success += 1
                elif status == "failed":
                    stats.failed += 1
                    stats.errors[f"{task}/{pdf_id}"] = error or "未知错误"
                else:
                    stats.skipped += 1
                done += 1
            t = datetime.now().strftime("%H:%M:%S")
            if status == "success":
                print(f"  [{t}] [{done}/{total}] OK   [{task:24s}] {pdf_id}"
                      f" -> {out_path}")
            else:
                print(f"  [{t}] [{done}/{total}] FAIL [{task:24s}] {pdf_id}:"
                      f" {error}")

        print("\n[Generate] 开始生成（Ctrl+C 可中断，已完成文件可断点续跑）...")
        try:
            if cfg["max_workers"] <= 1:
                for t in todo:
                    _finish_one(_work(t))
            else:
                with ThreadPoolExecutor(max_workers=cfg["max_workers"]) as ex:
                    futs = {ex.submit(_work, t): t for t in todo}
                    try:
                        for fut in as_completed(futs):
                            try:
                                res = fut.result()
                            except Exception as e:   # 兜底
                                pdf_id, task = futs[fut][0], futs[fut][1]
                                res = (pdf_id, task, "failed", None,
                                       f"内部异常: {e}")
                            _finish_one(res)
                    except KeyboardInterrupt:
                        for fut in futs:
                            fut.cancel()
                        ex.shutdown(wait=False, cancel_futures=True)
                        print("\n[WARN] 收到中断：已完成文件均已保存，"
                              "等待在途请求结束后退出")
                        raise
        except KeyboardInterrupt:
            print("\n[WARN] 收到中断，重跑脚本可继续未完成部分")

    client.close()

    print(f"\n[Generate] 生成完成")
    print(f"  成功: {stats.success} | 失败: {stats.failed} | 跳过: {stats.skipped}")
    for dname in sorted(set(TASK_OUT_DIRS.values())):
        d = out_base / dname
        n_files = len(list(d.glob("*.json"))) if d.is_dir() else 0
        print(f"  {dname}/ : {n_files} 份")
    if stats.errors:
        print(f"  [WARN] 失败明细:")
        for idx, err in stats.errors.items():
            print(f"    - {idx}: {str(err)[:200]}")
    return {"success": stats.success, "failed": stats.failed,
            "skipped": stats.skipped}


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="RQ2,3 Solution 生成：observation + (LLM-RW | human-RW) "
                    "→ solution{idea, implementation}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例：
  # 设置 API key（命令行或环境变量 DEEPSEEK_API_KEY 二选一）
  python generate_solutions.py --api-key sk-xxxx

  # 只生成某一类
  python generate_solutions.py --types human_re
  python generate_solutions.py --types llm_re_withsearch,llm_re_withoutsearch

  # 控制范围与行为
  python generate_solutions.py --only 52875bf8ef4b3f8c   # 只处理指定论文
  python generate_solutions.py --style-examples 2        # 风格示例轮转篇数
  python generate_solutions.py --redo                    # 忽略已有结果全部重抽
        """,
    )
    parser.add_argument("--jsonl", "-j", default=str(DEFAULT_JSONL),
                        help=f"总 jsonl 路径（默认: {DEFAULT_JSONL}）")
    parser.add_argument("--human-dir", default=str(DEFAULT_HUMAN_DIR),
                        help=f"human 抽取数据目录（默认: {DEFAULT_HUMAN_DIR}）")
    parser.add_argument("--llm-rw-dir", default=str(DEFAULT_LLM_RW_DIR),
                        help="LLM related works 根目录（默认: data/LLM_data，"
                             "其下含 relatedworks_withsearch/ 等子目录）")
    parser.add_argument("--out-base", "-o", default=str(DEFAULT_OUT_BASE),
                        help=f"输出根目录（默认: {DEFAULT_OUT_BASE}，其下建 "
                             f"{TASK_OUT_DIRS['llm_re_withsearch']}/ 与 "
                             f"{TASK_OUT_DIRS['human_re']}/）")
    parser.add_argument("--types", default="llm_re_withsearch,llm_re_withoutsearch,"
                                           "human_re",
                        help="要生成的任务类型，逗号分隔（默认三种全跑）")
    parser.add_argument("--style-examples", type=int, default=2,
                        help="每篇论文提示词中轮转提供的风格示例篇数（取它论文的人"
                             "类 solution，默认: 2；0=不提供示例）")
    parser.add_argument("--api-key", default="sk-626347bcc3b1436abfbee20761eb4940",
                        help="DeepSeek API key（也可用环境变量 DEEPSEEK_API_KEY）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"OpenAI 风格 API 地址（默认: {DEFAULT_BASE_URL}）")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"模型名（默认: {DEFAULT_MODEL}）")
    parser.add_argument("--max-tokens", type=int, default=48000,
                        help="单次回复最大 token 数（含思考，默认: 48000）")
    parser.add_argument("--index-field", default=None,
                        help="jsonl 中唯一索引字段名（默认自动探测）")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="并发线程数（默认: 1，串行最稳）")
    parser.add_argument("--limit", type=int, default=0,
                        help="最多处理前 N 篇论文，0=全部（默认: 0）")
    parser.add_argument("--only", action="append", default=None,
                        help="只处理指定唯一索引的论文，可多次指定")
    parser.add_argument("--redo", action="store_true",
                        help="忽略已有输出文件，全部重新生成")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[ERROR] 缺少 DeepSeek API key：请通过 --api-key 或环境变量 "
              "DEEPSEEK_API_KEY 提供")
        return

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = [t for t in types if t not in TASK_OUT_DIRS]
    if unknown:
        print(f"[ERROR] 未知任务类型: {unknown}（可选: "
              f"{', '.join(TASK_OUT_DIRS)}）")
        return

    cfg = {
        "jsonl_path": args.jsonl,
        "human_dir": args.human_dir,
        "llm_rw_dir": args.llm_rw_dir,
        "out_base": args.out_base,
        "api_key": api_key,
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "index_field": args.index_field,
        "max_workers": args.max_workers,
        "types": types,
        "style_examples": args.style_examples,
        "limit": args.limit,
        "only": set(args.only) if args.only else None,
        "redo": args.redo,
    }

    start_time = time.time()
    result = run_batch(cfg)
    if result is None:
        return
    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f} 秒 ({elapsed / 60:.1f} 分钟)")
    print(f"成功: {result['success']} | 失败: {result['failed']} | "
          f"跳过: {result['skipped']}")


if __name__ == "__main__":
    main()
