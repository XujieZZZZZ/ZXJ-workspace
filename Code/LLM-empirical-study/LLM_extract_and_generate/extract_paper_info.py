# -*- coding: utf-8 -*-
"""
====================================================
extract_paper_info.py — RQ2 论文信息抽取（任务1）
====================================================

作用（对应 LLM-empirical-study/README.md 内部实现逻辑第 1 条）：
    从典型论文集中抽取每篇论文的三要素作为"人类逻辑"数据：
      1) observation   —— 人类专家着手撰写本文前的核心观察点
      2) related_works —— 论文对已有工作的论断(claims)及支撑这些论断的 works
                          （分组结构：每条元素含 claims 数组 + works 数组，
                          每条 work 带 title / authors / year）
      3) solution      —— 论文原文使用的解决方案（idea 思路 + implementation 具体实现）
    抽取方式：读取 jsonl（存储 md 文件位置信息）→ 按"唯一索引 + 位置"找到对应
    md 全文 → 调用 OpenAI 风格 API（默认 deepseek-v4-flash，开思考模式，
    要求严格 JSON 输出）。给模型的提示词与要求的输出正文一律为英文。

输入：
    1) jsonl 文件：每行一个 JSON，含唯一索引字段（如 pdf_id）与 md 文件位置字段
       （如 md_path），例如 dataset/ADRS-and-let/md/pdf_mapping.jsonl。
       未指定 --index-field / --md-field 时自动从 ["pdf_id","id","doc_id","paper_id"]
       与 ["md_path","markdown_path","md"] 中探测。
    2) 对应的论文 Markdown 文件（按 jsonl 中的位置读取）。

输出：
    1) 每篇论文一份 JSON：<输出目录>/<唯一索引>.json，结构：
       {
         "observation":    "<string>",
         "related_works": [                       // 分组：一元素 = 一组相关论断
           {
             "claims": ["<string>", ...],         // 该组内每条独立的论断
             "works":  [{"title": "...", "authors": [...], "year": 2020}, ...]
           }
         ],
         "solution": {"idea": "<string>", "implementation": "<string>"},
         // 之后为溯源元信息：pdf_id / md_path / model / extracted_at
       }
       默认输出目录：Code/LLM-empirical-study/data（README 指定）
    2) 原始 jsonl 被回写：给每一行插入
       extraction_path（抽取结果 JSON 的绝对路径）、
       extraction_status（success / failed / skipped）、
       extraction_error（失败原因，仅失败时写入）
    3) <输出目录>/extraction_log.json：本次运行统计日志

功能特性：
    1. 断点续跑：已成功（jsonl 行中已有 extraction_path 且文件存在）的论文自动跳过
    2. 失败重试：单篇失败不影响其它论文，重跑本脚本会自动重新处理失败行
    3. 严格 JSON 输出：API 使用 json_object 模式 + 思考模式；
       输出结构不符合要求时判定失败并记录原因（不把脏数据落盘）
    4. 网络容错：429/5xx/超时 自动指数退避重试（默认 3 次）

API 约定（DeepSeek OpenAI 兼容端点，已实测）：
    base_url : https://api.deepseek.com
    model    : deepseek-v4-flash
    思考模式 : 请求体附 "thinking": {"type": "enabled"}
               返回体 message.reasoning_content 为思考内容，content 为最终输出

依赖：
    pip install requests

用法示例：
    # 设置 API key（命令行或环境变量二选一）
    export DEEPSEEK_API_KEY=sk-xxxx

    # 默认参数运行（jsonl、输出目录均带默认值）
    python extract_paper_info.py

    # 指定输入与输出
    python extract_paper_info.py \
        /path/to/pdf_mapping.jsonl \
        /path/to/LLM-empirical-study/data

    # 具名参数 + 常用开关
    python extract_paper_info.py \
        --jsonl /path/to/pdf_mapping.jsonl \
        --out-dir /path/to/LLM-empirical-study/data \
        --api-key sk-xxxx \
        --max-tokens 24000 \
        --max-workers 2 \
        --only 52875bf8ef4b3f8c      # 只处理指定唯一索引
        # --limit 3                   # 只处理前 3 行
        # --redo                     # 忽略已有成功结果，全部重新抽取
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
DEFAULT_JSONL = (
    "/home/zhangxujie/ai4research/ZXJ-workspace/Code/dataset/"
    "ADRS-and-let/md/pdf_mapping.jsonl"
)
DEFAULT_OUT_DIR = (
    "/home/zhangxujie/ai4research/ZXJ-workspace/Code/"
    "LLM-empirical-study/data/human_data/"
)
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

INDEX_FIELD_CANDIDATES = ["pdf_id", "id", "doc_id", "paper_id"]
MD_FIELD_CANDIDATES = ["md_path", "markdown_path", "md"]

HTTP_RETRY_STATUS = {429, 500, 502, 503, 504}   # 网络抖动类错误，自动重试
MAX_RETRY = 3                                    # 单候选请求的最大尝试次数
BACKOFF_BASE = 5.0                               # 指数退避基数（秒）
REQUEST_TIMEOUT = (15, 900)                      # (连接超时, 读取超时)

# --------------------------------------------------------------------------
# 提示词（英文，严谨简洁；<<MD_TEXT>> 由模板替换为论文全文）
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a rigorous research assistant. You will be given the full text of an "
    "academic paper in Markdown and must extract the requested components from it. "
    "Reply with exactly one JSON object conforming to the required schema. "
    "No prose, no code fences, no preamble."
)

USER_PROMPT_TEMPLATE = """
Below is the full text of an academic paper in Markdown (converted from PDF; some
formulas, figures, or tables may be corrupted — see Rule 4). Extract the three
components defined below. Be faithful to the paper: do not invent, omit, or reword
content in a way that changes its meaning.

# Rule 1: observation

State the core observation that motivated the authors to write this paper: the
phenomenon, empirical finding, problem, or unmet need they faced before the work.
- Write an observation about the problem domain, not about the paper: never mention
  the paper itself, its title, authors, institution, venue, or any specific
  publication (no "this paper", no "we propose"). It must stand alone as the
  starting point of a research problem.
- Keep key numbers, scenarios, and conditions exactly as reported.
- Do not include the proposed solution or the contributions.

# Rule 2: related_works

Extract the paper's claims about prior work and the works supporting them. Consider
every passage that discusses existing work — not only a section titled "Related
Work": introduction, background, problem statement, design-time comparisons, and
baseline discussion in the evaluation all count. Group the discussion by topic into
elements; each element carries the claims of that group and all works supporting them.

Element structure:
- claims: one or more complete sentences, each a distinct assertion about the state
  of prior work (what has or has not been done, its limitations, or the gap). Return
  every distinct assertion as its own string in the claims array — never merge
  distinct assertions into one string, never split one assertion into several, and
  never embed citation lists inside a claim.
- works: every prior paper cited in support of the claims of this group. Cover all
  such citations; omit none. The same work may appear under more than one element.
- Each work has exactly three fields: title (as in the original), authors (array,
  in the original order), year (integer; derive it from the reference-list entry,
  e.g. "[12] A. Author, B. Author. 2020. Title. In ..."). Set year to null only if
  it truly cannot be determined — never guess.
- Works must be formal academic publications (papers in conferences or journals).
  Exclude non-academic sources (vendor documentation, web pages, GitHub
  repositories, blogs): do not list them and do not invent a substitute for them.
- If the paper makes no claims about prior work, return an empty array. Never
  fabricate claims or works to fill the structure.

# Rule 3: solution

Describe the paper's solution to the problem in the observation, in two fields:
- idea: the rationale and core insight of the approach — which aspect of the
  observation it targets, why this approach solves it, and the key design trade-offs.
- implementation: a step-by-step, complete account of the method in the paper's
  original order: components, algorithms or protocols, the meaning of key formulas
  and parameters, and how the parts connect — detailed enough to re-implement.

# Rule 4: Faithfulness

The extraction must match the paper exactly: no omissions, no substitutions, no
additions. Where a detail is corrupted or missing in the Markdown (garbled formulas,
lost figures, broken tables), state at that point: "Unavailable in source:
corrupted or lost during Markdown conversion." Never reconstruct or invent it.

# Rule 5: Output format

Reply with a single JSON object only, in exactly this schema:

{
  "observation": "string",
  "related_works": [
    {
      "claims": ["string", "string"],
      "works": [
        {"title": "string", "authors": ["string"], "year": 2020}
      ]
    }
  ],
  "solution": {
    "idea": "string",
    "implementation": "string"
  }
}

All field contents must be in English.

# PAPER (Markdown)

<<MD_TEXT>>
"""

# --------------------------------------------------------------------------
# LLM API 客户端（OpenAI 风格 / DeepSeek 兼容端点）
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

    # 候选请求参数：优先"思考模式 + json 模式"，端点不兼容时逐级降级
    @staticmethod
    def _request_variants():
        return [
            {"thinking": {"type": "enabled"},
             "response_format": {"type": "json_object"}},   # 首选：思考+严格JSON
            {"thinking": {"type": "enabled"}},              # 降级1：仅思考模式
            {},                                             # 降级2：无附加参数
        ]

    def chat(self, messages, max_tokens):
        """发送对话请求，返回 (回复文本, usage)

        Raises:
            RuntimeError: 所有候选参数组合与所有重试都失败（含内容为空 / 被截断）
        """
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
                                    "（思考过程消耗了全部额度），请调大 --max-tokens"
                                )
                            raise RuntimeError("模型返回空内容（可能思考超长）")
                        if finish == "length":
                            # 有输出但被截断：JSON 一定不完整，按失败处理并给出建议
                            raise RuntimeError(
                                "回复达到 max_tokens 上限被截断，请调大 --max-tokens"
                            )
                        return text, data.get("usage", {})

                    err_msg = resp.text[:500]
                    if resp.status_code == 400:
                        # 参数不被端点支持（如 thinking / response_format 非法）：
                        # 记录后尝试下一组候选参数
                        last_err = RuntimeError(
                            f"HTTP 400，尝试降级参数重试: {err_msg}"
                        )
                        break
                    if resp.status_code in HTTP_RETRY_STATUS:
                        last_err = RuntimeError(
                            f"HTTP {resp.status_code}: {err_msg}"
                        )
                    else:
                        raise RuntimeError(f"HTTP {resp.status_code}: {err_msg}")
                except requests.exceptions.RequestException as e:
                    last_err = RuntimeError(f"网络请求异常: {e}")

                # 退避后重试
                sleep_s = BACKOFF_BASE * (2 ** (attempt - 1)) + attempt
                time.sleep(sleep_s)

        raise RuntimeError(f"请求失败: {last_err}")

    def close(self):
        self.session.close()


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


def extract_json_object(text):
    """从模型回复中鲁棒地解析 JSON 对象（容忍代码块围栏与前后杂音）"""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, flags=re.S | re.I)
    if fence:
        t = fence.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"回复中找不到 JSON 对象: {t[:200]!r}")
    return json.loads(t[start:end + 1])


def validate_schema(obj, index):
    """校验抽取结果是否符合约定的 JSON 结构，返回 (ok, 错误信息)

    结构约定（与提示词一致）：
        observation: string
        related_works: [ { claims: [string, ...], works: [ {title, authors, year} ] } ]
        solution: { idea: string, implementation: string }
    """
    err = lambda msg: (False, f"[{index}] 输出 JSON 结构不符合要求: {msg}")
    if not isinstance(obj, dict):
        return err("顶层必须是 JSON 对象")
    if not isinstance(obj.get("observation"), str) or not obj["observation"].strip():
        return err("observation 必须为非空字符串")
    rw = obj.get("related_works")
    if not isinstance(rw, list):
        return err("related_works 必须是数组")
    for i, item in enumerate(rw):
        if not isinstance(item, dict):
            return err(f"related_works[{i}] 必须是对象")
        claims = item.get("claims")
        if not isinstance(claims, list) or not claims:
            return err(f"related_works[{i}] 的 claims 必须为非空字符串数组")
        for k, c in enumerate(claims):
            if not isinstance(c, str) or not c.strip():
                return err(f"related_works[{i}].claims[{k}] 必须为非空字符串")
        works = item.get("works")
        if not isinstance(works, list):
            return err(f"related_works[{i}] 的 works 必须是数组")
        for j, w in enumerate(works):
            if not isinstance(w, dict):
                return err(f"related_works[{i}].works[{j}] 必须是对象")
            if not isinstance(w.get("title"), str) or not w["title"].strip():
                return err(f"related_works[{i}].works[{j}] 缺少非空 title")
            if not isinstance(w.get("authors"), list) or not all(
                    isinstance(a, str) for a in w["authors"]):
                return err(f"related_works[{i}].works[{j}] 的 authors 必须为字符串数组")
            y = w.get("year")
            if y is not None and not isinstance(y, int):
                return err(f"related_works[{i}].works[{j}] 的 year 必须为整数或 null")
    sol = obj.get("solution")
    if not isinstance(sol, dict):
        return err("solution 必须是对象")
    for key in ("idea", "implementation"):
        if not (isinstance(sol.get(key), str) and sol[key].strip()):
            return err(f"solution.{key} 必须为非空字符串")
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


def read_markdown(md_path):
    """读取论文 md 全文（转换损坏字节容错）"""
    with open(md_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def build_messages(md_text):
    """按抽取要求组装 system + user 消息（全英文提示词）"""
    user_prompt = USER_PROMPT_TEMPLATE.replace("<<MD_TEXT>>", md_text)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# --------------------------------------------------------------------------
# 单篇论文抽取
# --------------------------------------------------------------------------


class ExtractionStats:
    """多线程安全统计"""

    def __init__(self):
        self.lock = Lock()
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.errors = {}          # index -> 错误信息
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


def extract_single(client, index, md_path, out_dir, max_tokens, stats):
    """抽取单篇论文：LLM 调用 → 校验 → 落盘 data/<index>.json

    Returns: (状态, 结果json绝对路径或None, 错误信息或None)
    """
    try:
        md_text = read_markdown(md_path)
    except OSError as e:
        return "failed", None, f"读取 md 失败: {e}"

    messages = build_messages(md_text)
    try:
        text, usage = client.chat(messages, max_tokens=max_tokens)
        stats.add_tokens(usage)
        obj = extract_json_object(text)
    except Exception as e:
        return "failed", None, f"LLM 调用或解析失败: {e}"

    ok, err_msg = validate_schema(obj, index)
    if not ok:
        return "failed", None, err_msg

    # 落盘：三要素字段在前，溯源元信息在后
    out_file = out_dir / f"{index}.json"
    record = dict(obj)
    record.update({
        "pdf_id": index,
        "md_path": str(md_path.resolve()),
        "model": client.model,
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return "success", str(out_file.resolve()), None


def process_entries(client, entries, cfg, stats):
    """主循环：断点续跑 + 并发处理 + 回写 jsonl

    cfg: dict(index_field, md_field, jsonl_path, out_dir, redo, only,
              limit, max_workers, max_tokens)
    """
    jsonl_path = Path(cfg["jsonl_path"])
    out_dir = cfg["out_dir"]
    index_field, md_field = cfg["index_field"], cfg["md_field"]
    write_lock = Lock()

    # 收集待处理任务（行号 + 唯一索引），跳过已完成/重复/无 md 的行
    tasks = []                 # (row_no, index, md_path)
    seen_index, processed_count, skipped = {}, 0, 0
    for row_no, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        index = e.get(index_field)
        md_path = e.get(md_field)
        if index is None or md_path is None:
            stats.failed += 1
            stats.errors[str(row_no)] = \
                f"行 {row_no} 缺少索引字段 {index_field!r} 或 md 字段 {md_field!r}"
            continue
        index = str(index)
        if index in seen_index:
            stats.skipped += 1
            continue
        seen_index[index] = row_no
        if cfg["only"] and index not in cfg["only"]:
            continue
        if cfg["limit"] and processed_count >= cfg["limit"]:
            break
        processed_count += 1

        # 断点续跑：已有成功结果且文件存在 → 跳过（--redo 除外）
        if not cfg["redo"] and e.get("extraction_status") == "success":
            if e.get("extraction_path") and Path(e["extraction_path"]).is_file():
                stats.skipped += 1
                continue

        md_file = Path(md_path)
        if not md_file.is_file():
            stats.failed += 1
            stats.errors[index] = f"md 文件不存在: {md_path}"
            _update_row(entries, jsonl_path, row_no, index, "failed",
                        f"md 文件不存在: {md_path}", None, write_lock)
            continue
        tasks.append((row_no, index, md_file))

    if not tasks:
        return

    total = len(tasks)
    done = 0

    def _work(task):
        return extract_single(client, task[1], task[2], out_dir,
                              cfg["max_tokens"], stats)

    def _finish_one(task, status, out_path, error):
        nonlocal done
        row_no, index, _ = task
        with stats.lock:
            stats.success += status == "success"
            stats.failed += status == "failed"
            stats.skipped += status == "skipped"
            if status == "failed":
                stats.errors[index] = error or "未知错误"
            done += 1
        _update_row(entries, jsonl_path, row_no, index, status, error,
                    out_path, write_lock)
        t = datetime.now().strftime("%H:%M:%S")
        if status == "success":
            print(f"  [{t}] [{done}/{total}] OK     {index} -> {out_path}")
        elif status == "skipped":
            print(f"  [{t}] [{done}/{total}] SKIP   {index}")
        else:
            print(f"  [{t}] [{done}/{total}] FAIL   {index}: {error}")

    if cfg["max_workers"] <= 1:
        for task in tasks:
            status, out_path, error = _work(task)
            _finish_one(task, status, out_path, error)
    else:
        with ThreadPoolExecutor(max_workers=cfg["max_workers"]) as ex:
            futs = {ex.submit(_work, t): t for t in tasks}
            try:
                for fut in as_completed(futs):
                    task = futs[fut]
                    try:
                        status, out_path, error = fut.result()
                    except Exception as e:      # 线程内未捕获异常兜底
                        status, out_path, error = "failed", None, f"内部异常: {e}"
                    _finish_one(task, status, out_path, error)
            except KeyboardInterrupt:
                for fut in futs:
                    fut.cancel()
                ex.shutdown(wait=False, cancel_futures=True)
                print("\n[WARN] 收到中断：已完成条目均已保存，等待在途请求结束后退出")
                raise


def _update_row(entries, jsonl_path, row_no, index, status, error,
                out_path, lock):
    """把抽取位置信息插入到 jsonl 行中，并立即原子回写整个文件"""
    e = entries[row_no]
    if not isinstance(e, dict):
        return
    e["extraction_status"] = status
    if status == "success":
        e["extraction_path"] = out_path
        e.pop("extraction_error", None)
    else:
        e["extraction_error"] = error
    with lock:
        save_jsonl(jsonl_path, entries)


# --------------------------------------------------------------------------
# 批量主入口
# --------------------------------------------------------------------------


def extract_batch(cfg):
    """批量抽取。cfg 字段见 process_entries。返回运行统计字典。"""
    jsonl_path = Path(cfg["jsonl_path"])
    out_dir = cfg["out_dir"]

    if not jsonl_path.is_file():
        print(f"[ERROR] jsonl 文件不存在: {jsonl_path}")
        return None

    out_dir.mkdir(parents=True, exist_ok=True)

    entries, warns = load_jsonl(jsonl_path)
    for w in warns:
        print(f"  [WARN] {w}")

    # 探测唯一索引字段与 md 位置字段
    sample = next((e for e in entries if isinstance(e, dict)), {})
    if cfg["index_field"]:
        index_field = cfg["index_field"]
    else:
        index_field = next(
            (k for k in INDEX_FIELD_CANDIDATES if k in sample), None)
    if cfg["md_field"]:
        md_field = cfg["md_field"]
    else:
        md_field = next(
            (k for k in MD_FIELD_CANDIDATES if k in sample), None)
    if not index_field or not md_field:
        print(f"[ERROR] 无法在 jsonl 中探测到唯一索引字段 / md 位置字段，"
              f"请用 --index-field / --md-field 指定")
        return None

    client = LLMClient(api_key=cfg["api_key"],
                       base_url=cfg["base_url"], model=cfg["model"])
    stats = ExtractionStats()

    print(f"[Config] jsonl 输入   : {jsonl_path.resolve()}")
    print(f"[Config] 输出目录     : {out_dir.resolve()}")
    print(f"[Config] 唯一索引字段 : {index_field} | md 位置字段: {md_field}")
    print(f"[Config] API 端点     : {cfg['base_url']}  模型: {cfg['model']}"
          f"（思考模式 + 严格 JSON）")
    print(f"[Config] max_tokens: {cfg['max_tokens']} | workers: {cfg['max_workers']}")

    print("\n[Extract] 开始批量抽取（Ctrl+C 可中断，进度已完成的条目可断点续跑）...")
    try:
        process_entries(client, entries, {**cfg, "index_field": index_field,
                                          "md_field": md_field}, stats)
    except KeyboardInterrupt:
        print("\n[WARN] 收到中断，已完成的条目已保存，重跑脚本可继续未完成部分")

    client.close()

    # 运行统计日志
    log_data = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "jsonl": str(jsonl_path.resolve()),
        "out_dir": str(out_dir.resolve()),
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "success": stats.success,
        "failed": stats.failed,
        "skipped": stats.skipped,
        "errors": stats.errors,
        "tokens": stats.tokens,
    }
    log_path = out_dir / "extraction_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    print(f"\n[Extract] 抽取完成")
    print(f"  成功: {stats.success} | 失败: {stats.failed} | 跳过: {stats.skipped}")
    print(f"  输出目录: {out_dir.resolve()}")
    print(f"  日志文件: {log_path}")
    if stats.errors:
        print(f"  [WARN] 失败明细:")
        for idx, err in stats.errors.items():
            print(f"    - {idx}: {str(err)[:200]}")
    return log_data


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="RQ2 论文信息抽取：md 全文 → observation / related_works / solution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例：
  # 设置 API key（命令行或环境变量 DEEPSEEK_API_KEY 二选一）
  python extract_paper_info.py --api-key sk-xxxx
  python extract_paper_info.py

  # 指定输入 jsonl 与输出目录（也支持两个位置参数）
  python extract_paper_info.py --jsonl <jsonl路径> --out-dir <输出目录>

  # 控制范围与行为
  python extract_paper_info.py --only <唯一索引>      # 只处理指定论文
  python extract_paper_info.py --limit 3              # 只处理前 3 篇
  python extract_paper_info.py --redo                 # 忽略已有结果全部重抽
        """,
    )

    parser.add_argument("jsonl_pos", nargs="?", default=None,
                        help="md位置信息jsonl路径（位置参数，可选）")
    parser.add_argument("out_dir_pos", nargs="?", default=None,
                        help="抽取结果输出目录（位置参数，可选）")
    parser.add_argument("--jsonl", "-j", default=None,
                        help=f"md位置信息jsonl路径（默认: {DEFAULT_JSONL}）")
    parser.add_argument("--out-dir", "-o", default=None,
                        help=f"输出目录，自动创建（默认: {DEFAULT_OUT_DIR}）")
    parser.add_argument("--api-key", default="sk-626347bcc3b1436abfbee20761eb4940",
                        help="DeepSeek API key（也可用环境变量 DEEPSEEK_API_KEY）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"OpenAI 风格 API 地址（默认: {DEFAULT_BASE_URL}）")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"模型名（默认: {DEFAULT_MODEL}）")
    parser.add_argument("--max-tokens", type=int, default=48000,
                        help="单次回复最大 token 数（含思考，默认: 24000）")
    parser.add_argument("--index-field", default=None,
                        help="jsonl 中唯一索引字段名（默认自动探测 pdf_id/id/doc_id/paper_id）")
    parser.add_argument("--md-field", default=None,
                        help="jsonl 中 md 位置字段名（默认自动探测 md_path/markdown_path/md）")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="并发线程数（默认: 1，串行最稳；API 余量充足可调大）")
    parser.add_argument("--limit", type=int, default=0,
                        help="最多处理前 N 篇，0=全部（默认: 0）")
    parser.add_argument("--only", action="append", default=None,
                        help="只处理指定唯一索引的论文，可多次指定")
    parser.add_argument("--redo", action="store_true",
                        help="忽略 jsonl 中已有的成功结果，全部重新抽取")

    args = parser.parse_args()

    jsonl_path = args.jsonl or args.jsonl_pos or DEFAULT_JSONL
    out_dir = Path(args.out_dir or args.out_dir_pos or DEFAULT_OUT_DIR)
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[ERROR] 缺少 DeepSeek API key：请通过 --api-key 或环境变量 "
              "DEEPSEEK_API_KEY 提供")
        return

    cfg = {
        "jsonl_path": jsonl_path,
        "out_dir": out_dir,
        "api_key": api_key,
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "index_field": args.index_field,
        "md_field": args.md_field,
        "max_workers": args.max_workers,
        "limit": args.limit,
        "only": set(args.only) if args.only else None,
        "redo": args.redo,
    }

    start_time = time.time()
    result = extract_batch(cfg)
    if result is None:
        return
    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f} 秒 ({elapsed / 60:.1f} 分钟)")
    print(f"成功: {result['success']} | 失败: {result['failed']} | "
          f"跳过: {result['skipped']}")


if __name__ == "__main__":
    main()
