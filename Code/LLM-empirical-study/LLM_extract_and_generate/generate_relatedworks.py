# -*- coding: utf-8 -*-
"""
====================================================
generate_relatedworks.py — RQ1 相关工作生成实验
====================================================

作用（对应 README.md 内部实现逻辑第 2 条）：
    以"总 jsonl + human 提取数据"为输入：对其中每一篇论文，取 human 数据中的
    observation 交给 LLM，让 LLM 生成与 observation 相符的 related works
    （claim + 支撑 works，每条 work 只提供名称 title 和第一作者 authors[0]）。
    为保持后续评分的风格/长短一致性，提示词中以"轮转"方式提供其它论文的
    human related works 作为风格示例（只保留第一作者，作者列表与年份一律去掉）；
    示例仅用于展示风格、长度与格式，禁止模型参考其内容。

    两种运行模式：
      1) withoutsearch —— 模型不得检索，只能依据自身参数知识组织与输出；
      2) withsearch    —— 提示词声明模型可依据 observation 检索相关论文后再组织输出
                          （脚本当前不接入真实检索后端，仅以提示词区分两种模式；
                           后续如需真实检索，可在 retrieve 处接入搜索引擎/学术 API）。
    分别输出到：
      data/LLM_data/relatedworks_withoutsearch/<pdf_id>.json
      data/LLM_data/relatedworks_withsearch/<pdf_id>.json

输入：
    1) 总 jsonl：每行含唯一索引字段（如 pdf_id），如 data/pdf_mapping.jsonl
    2) human 抽取数据目录（默认 data/human_data/）：文件名为 <唯一索引>.json，
       内含 observation 与 related_works（分组结构：claims 数组 + works 数组，
       works 含完整 authors 与 year —— 生成示例时会被裁剪为 title + 第一作者）

输出（每篇论文、每个模式一份）：
    {
      "pdf_id":        "<唯一索引>",
      "mode":          "withsearch" | "withoutsearch",
      "observation":   "<输入的观察>",
      "related_works": [                       // 与 human 数据同构的分组结构
        {
          "claims": ["<论断1>", "<论断2>", ...],
          "works":  [{"title": "<论文题目>", "authors": ["<第一作者>"]}, ...]
        }
      ],
      "style_exemplar_ids": ["<风格示例来源论文的pdf_id>", ...],  // 仅供溯源
      "model":         "<模型名>",
      "generated_at":  "<时间>"
    }

    2) 原始 jsonl 回写：每完成一种模式，即将生成 json 的地址与状态插入原始 jsonl
       对应行（pdf_id 匹配；两种模式都补齐），字段：
       relatedworks_withsearch_path / relatedworks_withsearch_status
       relatedworks_withoutsearch_path / relatedworks_withoutsearch_status
       （_status 取值 success=文件已生成路径有效 / failed=本次失败，
       failed 时另有 *_error 记录原因；断点续跑跳过时同样回写 success 路径）

功能特性：
    1. 两种模式一次跑完（--mode both），输出目录分开落盘
    2. 风格示例轮转：目标论文 i 取其后第 1、2 篇（按 jsonl 顺序循环）的 human
       related works 为示例，示例必然不属于目标论文本身
    3. 断点续跑：对应输出文件已存在则跳过（--redo 强制重抽）
    4. 严格 JSON 输出：思考模式 + json_object；结构不符合要求判失败不落盘
    5. 网络容错：429/5xx/超时指数退避重试
    6. 结果回写：生成结果（withsearch 与 withoutsearch 各自独立）即时回写原始 jsonl

API 约定（DeepSeek OpenAI 兼容端点，已实测）：
    base_url : https://api.deepseek.com
    model    : deepseek-v4-flash
    思考模式 : "thinking": {"type": "enabled"}，返回 message.reasoning_content

依赖：
    pip install requests

用法示例：
    export DEEPSEEK_API_KEY=sk-xxxx

    # 两种模式全部论文（默认）
    python generate_relatedworks.py

    # 只跑某一种模式 / 指定范围
    python generate_relatedworks.py --mode withsearch
    python generate_relatedworks.py --only 52875bf8ef4b3f8c --limit 3
    python generate_relatedworks.py --redo            # 忽略已有结果全部重抽
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
DEFAULT_OUT_BASE = SCRIPT_DIR / "data" / "LLM_data"

MODE_DIR_NAMES = {
    "withsearch": "relatedworks_withsearch",
    "withoutsearch": "relatedworks_withoutsearch",
}
# 回写 jsonl 时使用的字段名（与目录命名一致，便于追溯）
LLM_RW_KEYS = {
    "withsearch": ("relatedworks_withsearch_path",
                   "relatedworks_withsearch_status",
                   "relatedworks_withsearch_error"),
    "withoutsearch": ("relatedworks_withoutsearch_path",
                      "relatedworks_withoutsearch_status",
                      "relatedworks_withoutsearch_error"),
}
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

INDEX_FIELD_CANDIDATES = ["pdf_id", "id", "doc_id", "paper_id"]

HTTP_RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY = 3
BACKOFF_BASE = 5.0
REQUEST_TIMEOUT = (15, 900)

# --------------------------------------------------------------------------
# 提示词（英文，严谨简洁；占位符：<<OBSERVATION>> / <<EXEMPLARS>> / <<MODE_RULE>>）
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a rigorous research assistant. Given a research observation, you must "
    "write the related-work part that a human expert would write before proposing a "
    "solution: claims about the state of prior work, each supported by real papers. "
    "Reply with exactly one JSON object conforming to the required schema. "
    "No prose, no code fences, no preamble."
)

# 两种模式的差异仅在此规则块
MODE_RULE_WITHOUTSEARCH = (
    "MODE — NO SEARCH: In this run you are NOT allowed to perform any retrieval, "
    "searching (web, databases, libraries, tools), or consult any external source. "
    "Produce the related work entirely from your internal knowledge."
)

MODE_RULE_WITHSEARCH = (
    "MODE — SEARCH ALLOWED: In this run you ARE allowed to retrieve or search for "
    "relevant papers (web, academic databases) before composing your answer, and to "
    "ground your works in what you find."
)

USER_PROMPT_TEMPLATE = """
You are given an observation: a phenomenon, empirical finding, or unmet need that
motivates a new research problem (no specific paper is attached). Your task is to
write the related-work part that a human expert would write at this stage: a
structured review of prior work relevant to the observation.

# Observation

<<OBSERVATION>>

# Task requirements

- Scope and relevance: every claim and every work must concern the topic raised by
  the observation. Cover the most important and representative directions of prior
  work around it; do not pad with tangential or generic works.
- claims: complete, standalone sentences, each stating one distinct assertion about
  the state of prior work (what has or has not been done, its limitations, or the
  gap that the observation points to). Multiple claims on the same topic are grouped
  into one element of related_works. Never merge distinct assertions into one claim,
  never split one assertion, and never embed citation lists inside a claim.
- works: the real, published academic papers supporting the claims of their group.
  Provide exactly two fields per work: title (exact, as published) and
  authors (an array containing ONLY the first author's name).
- Fidelity: do not fabricate. Any work whose existence, exact title, or first author
  you cannot state with confidence must be omitted — a correct small set beats a
  large one containing invented or misattributed entries. Titles and author names
  must be spelled exactly; do not paraphrase titles.
- The target paper under study does not exist yet: claims must not refer to "this
  paper" or any proposed method.

# Style examples

Below are human-written related-work excerpts of OTHER papers. They are provided
ONLY as style references: they show the expected JSON structure, topic grouping,
claim granularity, and overall length. Do NOT reuse their content, topics, claims,
or titles.

<<EXEMPLARS>>

# Mode rule

<<MODE_RULE>>

# Output format

Reply with a single JSON object only, in exactly this schema:

{
  "related_works": [
    {
      "claims": ["string", "string"],
      "works": [
        {"title": "string", "authors": ["First Author"]}
      ]
    }
  ]
}

All field contents must be in English.
"""

# --------------------------------------------------------------------------
# LLM API 客户端（OpenAI 风格 / DeepSeek 兼容端点，与抽取脚本同一契约）
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


def validate_schema(obj, pdf_id):
    """校验结构：related_works 分组，每组 claims[] + works[]（title + 首作者）"""
    err = lambda msg: (False, f"[{pdf_id}] 输出 JSON 结构不符合要求: {msg}")
    if not isinstance(obj, dict):
        return err("顶层必须是 JSON 对象")
    rw = obj.get("related_works")
    if not isinstance(rw, list):
        return err("related_works 必须是数组")
    if not rw:
        return err("related_works 不允许为空（须产出相关工作）")
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
            authors = w.get("authors")
            if not isinstance(authors, list) or len(authors) != 1 \
                    or not isinstance(authors[0], str) or not authors[0].strip():
                return err(f"related_works[{i}].works[{j}] 的 authors 必须为"
                           f"只含第一作者的数组（长度1）")
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


def load_human_entry(human_dir, index):
    """按唯一索引读取 human 抽取数据（文件名 <index>.json）

    Returns: (dict|None, 错误信息|None)
    """
    p = human_dir / f"{index}.json"
    if not p.is_file():
        return None, f"human 抽取数据不存在: {p}"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"human 抽取数据解析失败 {p}: {e}"
    if not isinstance(d.get("observation"), str) or not d["observation"].strip():
        return None, f"human 数据缺少有效 observation: {p}"
    if not isinstance(d.get("related_works"), list):
        return None, f"human 数据缺少 related_works 数组: {p}"
    return d, None


def first_author_only(work):
    """裁剪 work 为 title + 第一作者（去掉其余作者与年份，供风格示例使用）"""
    authors = work.get("authors") or []
    return {"title": work["title"], "authors": [authors[0]] if authors else []}


def build_exemplars_text(exemplar_papers):
    """把各篇示例论文的 human related_works 转成带编号的风格示例文本（JSON）

    exemplar_papers: [(pdf_id, human_dict), ...] —— 仅取 title + 第一作者，
    去掉其余作者与年份；每篇示例单独成块并标注来源论文（仅供溯源/风格）。
    """
    blocks = []
    for pid, human in exemplar_papers:
        trimmed = []
        for g in human.get("related_works", []):
            trimmed.append({
                "claims": g.get("claims", []),
                "works": [first_author_only(w) for w in g.get("works", [])],
            })
        blocks.append(
            f"Example from another paper (id: {pid}):\n"
            + json.dumps(trimmed, ensure_ascii=False, indent=2))
    return "\n\n".join(blocks)


def build_messages(observation, exemplar_text, mode):
    """组装 system + user 消息（全英文）"""
    mode_rule = (MODE_RULE_WITHSEARCH if mode == "withsearch"
                 else MODE_RULE_WITHOUTSEARCH)
    exemplars_block = (
        f"[Style examples (other papers' human related work)]\n{exemplar_text}"
        if exemplar_text else
        "[No style examples available in this run; follow the schema above.]"
    )
    user_prompt = (USER_PROMPT_TEMPLATE
                   .replace("<<OBSERVATION>>", observation)
                   .replace("<<EXEMPLARS>>", exemplars_block)
                   .replace("<<MODE_RULE>>", mode_rule))
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# --------------------------------------------------------------------------
# 单篇论文 × 单个模式生成
# --------------------------------------------------------------------------


class GenStats:
    def __init__(self):
        self.lock = Lock()
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.errors = {}      # "<mode>/<pdf_id>" -> 错误信息
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


def generate_single(client, pdf_id, human, exemplar_ids, exemplar_text,
                    mode, out_dir, max_tokens, stats):
    """单个模式单篇生成 → 校验 → 落盘 <mode_dir>/<pdf_id>.json"""
    try:
        messages = build_messages(human["observation"], exemplar_text, mode)
        text, usage = client.chat(messages, max_tokens=max_tokens)
        stats.add_tokens(usage)
        obj = extract_json_object(text)
    except Exception as e:
        return "failed", None, f"LLM 调用或解析失败: {e}"

    ok, err_msg = validate_schema(obj, pdf_id)
    if not ok:
        return "failed", None, err_msg

    record = {
        "pdf_id": pdf_id,
        "mode": mode,
        "observation": human["observation"],
        "related_works": obj["related_works"],
        "style_exemplar_ids": exemplar_ids,
        "model": client.model,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_file = out_dir / f"{pdf_id}.json"
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

    sample = next(iter(entries), {})
    index_field = cfg.get("index_field")
    if not index_field:
        index_field = next(
            (k for k in INDEX_FIELD_CANDIDATES if k in sample), None)
    if not index_field:
        print(f"[ERROR] 无法在 jsonl 中探测到唯一索引字段，"
              f"请用 --index-field 指定")
        return None

    # 行号索引：pdf_id -> jsonl 行号列表（供结果回写，同一索引可对应多行）
    row_nos_by_pdf = {}
    for rno, e in enumerate(entries):
        if isinstance(e, dict) and e.get(index_field) is not None:
            row_nos_by_pdf.setdefault(str(e[index_field]), []).append(rno)

    # 结果回写：把某模式生成的 json 路径/状态插入原始 jsonl 的对应行
    save_lock = Lock()

    def _backfill_jsonl(pdf_id, mode, status, out_path, error):
        path_key, status_key, error_key = LLM_RW_KEYS[mode]
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

    # 收集：pdf 顺序 + human 数据 + 有效论文顺序（用于轮转示例）
    papers = []          # 按 jsonl 顺序 (pdf_id, human)
    for e in entries:
        if not isinstance(e, dict):
            continue
        idx = e.get(index_field)
        if idx is None:
            continue
        idx = str(idx)
        human, err = load_human_entry(human_dir, idx)
        if human is None:
            print(f"  [SKIP] {idx}: {err}")
            continue
        papers.append((idx, human))
    if not papers:
        print("[ERROR] 没有可用的 human 数据（请先运行 extract_paper_info.py）")
        return None

    m = len(papers)
    n_ex = max(0, min(cfg["style_examples"], m - 1))

    modes = cfg["modes"]
    client = LLMClient(api_key=cfg["api_key"],
                       base_url=cfg["base_url"], model=cfg["model"])
    stats = GenStats()

    print(f"[Config] jsonl 输入    : {jsonl_path.resolve()}")
    print(f"[Config] human 数据目录: {human_dir.resolve()}")
    print(f"[Config] 唯一索引字段  : {index_field} | 有效论文: {m} 篇")
    print(f"[Config] 输出目录      : {out_base.resolve()}")
    print(f"[Config] 模式          : {', '.join(modes)}")
    print(f"[Config] 风格示例轮转  : 每篇取其后 {n_ex} 篇（示例不含本论文自身）")
    print(f"[Config] API 端点      : {cfg['base_url']}  模型: {cfg['model']}"
          f"（思考模式 + 严格 JSON）")
    print(f"[Config] max_tokens: {cfg['max_tokens']} | workers: {cfg['max_workers']}")

    # 待处理任务列表
    tasks = []           # (pdf_id, human, exemplar_ids, exemplar_text, mode, out_dir)
    planned = 0
    for i, (pdf_id, human) in enumerate(papers):
        if cfg["only"] and pdf_id not in cfg["only"]:
            continue
        if cfg["limit"] and planned >= cfg["limit"]:
            break
        planned += 1
        # 轮转选取示例：本论文之后第 1..n_ex 篇（循环），必然 ≠ 本论文
        exemplar_papers = [papers[(i + k) % m] for k in range(1, n_ex + 1)]
        exemplar_ids = [pid for pid, _ in exemplar_papers]
        exemplar_text = build_exemplars_text(exemplar_papers)
        for mode in modes:
            out_dir = out_base / MODE_DIR_NAMES[mode]
            out_file = out_dir / f"{pdf_id}.json"
            if not cfg["redo"] and out_file.is_file():
                # 断点续跑：文件已存在同样把地址回写 jsonl（保证两种模式都补齐）
                stats.skipped += 1
                _backfill_jsonl(pdf_id, mode, "success",
                                str(out_file.resolve()), None)
                continue
            tasks.append((pdf_id, human, exemplar_ids, exemplar_text,
                          mode, out_dir))

    if not tasks:
        print("\n[WARN] 没有待处理任务（均已生成过；可用 --redo 强制重抽）")
    else:
        total = len(tasks)
        done = 0

        def _work(task):
            pdf_id, human, ex_ids, ex_text, mode, out_dir = task
            return (pdf_id, mode, *generate_single(
                client, pdf_id, human, ex_ids, ex_text, mode, out_dir,
                cfg["max_tokens"], stats))

        def _finish_one(res):
            nonlocal done
            pdf_id, mode, status, out_path, error = res
            # 结果回写原始 jsonl（success/failed 都即时回写，可断点续跑）
            _backfill_jsonl(pdf_id, mode, status, out_path, error)
            with stats.lock:
                if status == "success":
                    stats.success += 1
                elif status == "failed":
                    stats.failed += 1
                    stats.errors[f"{mode}/{pdf_id}"] = error or "未知错误"
                else:
                    stats.skipped += 1
                done += 1
            t = datetime.now().strftime("%H:%M:%S")
            if status == "success":
                print(f"  [{t}] [{done}/{total}] OK   [{mode:13s}] {pdf_id}"
                      f" -> {out_path}")
            else:
                print(f"  [{t}] [{done}/{total}] FAIL [{mode:13s}] {pdf_id}:"
                      f" {error}")

        print("\n[Generate] 开始生成（Ctrl+C 可中断，已完成的文件可断点续跑）...")
        try:
            if cfg["max_workers"] <= 1:
                for task in tasks:
                    _finish_one(_work(task))
            else:
                with ThreadPoolExecutor(max_workers=cfg["max_workers"]) as ex:
                    futs = {ex.submit(_work, t): t for t in tasks}
                    try:
                        for fut in as_completed(futs):
                            try:
                                res = fut.result()
                            except Exception as e:   # 兜底
                                pdf_id, _, _, _, mode, _ = futs[fut]
                                res = (pdf_id, mode, "failed", None,
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
    for mode in modes:
        d = out_base / MODE_DIR_NAMES[mode]
        n_files = len(list(d.glob("*.json"))) if d.is_dir() else 0
        print(f"  {MODE_DIR_NAMES[mode]}/ : {n_files} 份")
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
        description="RQ1 相关工作生成：observation → related works(claims + title/首作者)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例：
  # 设置 API key（命令行或环境变量 DEEPSEEK_API_KEY 二选一）
  python generate_relatedworks.py --api-key sk-xxxx

  # 只跑某一模式
  python generate_relatedworks.py --mode withsearch

  # 风格示例数量（轮转取自其它论文，默认 2，0=不给示例）
  python generate_relatedworks.py --style-examples 2

  # 控制范围与行为
  python generate_relatedworks.py --only 52875bf8ef4b3f8c   # 只处理指定论文
  python generate_relatedworks.py --redo                    # 忽略已有结果全部重抽
        """,
    )
    parser.add_argument("--jsonl", "-j", default=str(DEFAULT_JSONL),
                        help=f"总 jsonl 路径（默认: {DEFAULT_JSONL}）")
    parser.add_argument("--human-dir", default=str(DEFAULT_HUMAN_DIR),
                        help=f"human 抽取数据目录（默认: {DEFAULT_HUMAN_DIR}）")
    parser.add_argument("--out-base", "-o", default=str(DEFAULT_OUT_BASE),
                        help=f"输出根目录，其下分 relatedworks_withsearch / "
                             f"relatedworks_withoutsearch（默认: {DEFAULT_OUT_BASE}）")
    parser.add_argument("--mode", choices=["withsearch", "withoutsearch", "both"],
                        default="both",
                        help="运行模式（默认: both，两种模式都跑）")
    parser.add_argument("--style-examples", type=int, default=2,
                        help="每篇论文提示词中轮转提供的风格示例篇数（取它论文，"
                             "默认: 2；0=不提供示例）")
    parser.add_argument("--api-key", default="sk-626347bcc3b1436abfbee20761eb4940",
                        help="DeepSeek API key（也可用环境变量 DEEPSEEK_API_KEY）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"OpenAI 风格 API 地址（默认: {DEFAULT_BASE_URL}）")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"模型名（默认: {DEFAULT_MODEL}）")
    parser.add_argument("--max-tokens", type=int, default=24000,
                        help="单次回复最大 token 数（含思考，默认: 24000）")
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

    modes = ["withsearch", "withoutsearch"] if args.mode == "both" \
        else [args.mode]

    cfg = {
        "jsonl_path": args.jsonl,
        "human_dir": args.human_dir,
        "out_base": args.out_base,
        "api_key": api_key,
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "index_field": args.index_field,
        "max_workers": args.max_workers,
        "modes": modes,
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
