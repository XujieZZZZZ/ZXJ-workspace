# -*- coding: utf-8 -*-
"""LLM-as-Judge 后端与各评测任务的提示词/校验(供 RQ2-1/2/3 共用)。

后端(可配置,见 config.py):
- 默认 qwen(DashScope OpenAI 兼容端点,模型 qwen3-max;用户指定,已实测可用);
- 保留 README 指定的 zai/GLM 适配位(backend="glm" 时按 zai 接口调用,
  与 evaluator/README.md 中 from zai import ZhipuAiClient 用法一致)。
所有裁判回复要求严格 JSON,校验失败自动重试一次;usage 逐条记账落盘。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests

import config
from utils import (JsonlStore, clean_json_number, extract_json_object, load_jsonl,
                   log, run_pool, truncate_chars)

USAGE_FILE = config.JUDGE_DIR / "usage.jsonl"
FAIL_FILE = config.JUDGE_DIR / "failed.jsonl"

SYSTEM_JUDGE = (
    "You are a rigorous, impartial computer-science research evaluator. You evaluate "
    "strictly and fairly, grounding every judgment in the semantic content of the provided "
    "texts. You NEVER let text length, writing style, formatting, citation count, or "
    "terminology density influence any score. You reason carefully (following any requested "
    "procedure) and then answer with a single valid JSON object matching the requested "
    "schema — no markdown fences, no prose outside the JSON."
)


# =========================================================================== #
# 后端客户端
# =========================================================================== #
class JudgeLLM:
    """统一裁判客户端:qwen(DashScope)与 glm(zai 适配)两种后端。"""

    def __init__(self, backend: Optional[str] = None):
        self.backend = backend or config.LLM_BACKEND
        self._usage_lock = threading.Lock()
        self._usage_total = {"prompt": 0, "completion": 0}
        self.session = requests.Session()
        self._glm_client = None
        self.force_json = False   # deepseek:强制 json_object 输出(400 时自动降级)
        if self.backend == "qwen":
            self.base_url = config.QWEN_BASE_URL.rstrip("/")
            self.api_key = config.QWEN_API_KEY
            self.model = config.QWEN_MODEL
        elif self.backend == "deepseek":
            self.base_url = config.DEEPSEEK_BASE_URL.rstrip("/")
            self.api_key = config.DEEPSEEK_API_KEY
            self.model = config.DEEPSEEK_MODEL
            self.force_json = True
        elif self.backend == "glm":
            # README 规定的 zai.ZhipuAiClient(不可达时给出明确提示);若 zai 未安装,
            # 则退化为 GLM 官方 OpenAI 兼容端点(仍需有效 key 与可达网络)。
            self.base_url = config.GLM_BASE_URL.rstrip("/")
            self.api_key = config.GLM_ZAI_API_KEY
            self.model = config.GLM_MODEL
            try:
                from zai import ZhipuAiClient
                self._glm_client = ZhipuAiClient(api_key=self.api_key)
            except Exception:
                self._glm_client = None
        else:
            raise ValueError(f"未知后端: {backend}(可选 qwen / glm / deepseek)")

    # ---------------- 基础对话 ---------------- #
    def chat(self, messages: List[dict], temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> str:
        """一次 chat 调用(带重试),返回回复文本。"""
        temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        if max_tokens is None:
            # deepseek 默认思考(reasoning 计入 completion),需更大输出上限防止 content 为空
            max_tokens = config.LLM_MAX_TOKENS_DS if self.backend == "deepseek" \
                else config.LLM_MAX_TOKENS
        if self.backend == "qwen":
            return self._chat_http(messages, temperature, max_tokens)
        if self._glm_client is not None:
            resp = self._glm_client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature)
            return resp.choices[0].message.content
        return self._chat_http(messages, temperature, max_tokens)  # GLM 官方端点兜底

    def _chat_http(self, messages, temperature, max_tokens) -> str:
        last_err: Optional[Exception] = None
        # force_json:deepseek 用 json_object 模式(要求 prompt 中含 "json" 字样,
        # 本框架所有裁判 prompt 均满足);若端点 400 拒绝该参数则降级重试一次。
        use_json = self.force_json
        for attempt in range(4):
            body: Dict[str, Any] = {"model": self.model, "messages": messages,
                                    "temperature": temperature, "max_tokens": max_tokens}
            if use_json:
                body["response_format"] = {"type": "json_object"}
            try:
                r = self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json=body,
                    timeout=(20, 300), proxies=config.PROXIES)
            except requests.RequestException as exc:
                last_err = exc
                log(f"[judge] 网络异常(第{attempt + 1}次): {exc}")
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                if not content.strip():
                    # 偶发空内容(如 deepseek 思考占满配额/瞬时异常):短等后重试
                    if attempt < 3:
                        time.sleep(3 * (attempt + 1))
                        continue
                    raise RuntimeError("LLM 返回空内容(多次重试仍为空)")
                usage = js.get("usage") or {}
                with self._usage_lock:
                    self._usage_total["prompt"] += usage.get("prompt_tokens", 0)
                    self._usage_total["completion"] += usage.get("completion_tokens", 0)
                    # 逐次记账落盘(便于审计与成本核算)
                    try:
                        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with open(USAGE_FILE, "a", encoding="utf-8") as f:
                            f.write(json.dumps(
                                {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "model": self.model, "backend": self.backend,
                                 "prompt_tokens": usage.get("prompt_tokens", 0),
                                 "completion_tokens": usage.get("completion_tokens", 0)},
                                ensure_ascii=False) + "\n")
                    except OSError:
                        pass
                return content
            if r.status_code in (401, 403):
                raise RuntimeError(f"LLM 鉴权失败({r.status_code}): {r.text[:200]}")
            if r.status_code == 400 and use_json:
                # json_object 参数被端点拒绝:降级为普通模式再试一次
                log(f"[judge] 400,response_format 降级重试: {r.text[:120]}")
                use_json = False
                continue
            wait = 3 * (attempt + 1)
            log(f"[judge] HTTP {r.status_code},退避 {wait}s: {r.text[:120]}")
            time.sleep(wait)
            last_err = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError(f"LLM 调用多次失败: {last_err}")

    # ---------------- 记账 ---------------- #
    def usage(self) -> dict:
        with self._usage_lock:
            return dict(self._usage_total)


# =========================================================================== #
# JSON 会话辅助
# =========================================================================== #
def ask_json(judge: JudgeLLM, messages: List[dict], validator: Callable[[dict], Any],
             task_key: str = "") -> Any:
    """调用 LLM 并校验 JSON;失败补一句"必须输出合法 JSON 对象"再试一次。"""
    content = judge.chat(messages)
    try:
        obj = extract_json_object(content)
        return validator(obj)
    except Exception as exc:
        # 记录首次失败片段,便于诊断(第二段日志会带完整片段)
        log(f"[judge:{task_key}] 首次输出校验失败: {str(exc)[:150]} | 片段: {content[:120]!r}")
    retry = list(messages)
    if retry and retry[-1]["role"] == "user":
        retry[-1] = {"role": "user",
                     "content": retry[-1]["content"] +
                     "\n\nIMPORTANT: Respond with ONLY a valid JSON object (no prose, no code fences)."}
    content2 = judge.chat(retry)
    try:
        obj = extract_json_object(content2)
        return validator(obj)   # 二次失败则抛出由上层记 fail
    except Exception as exc:
        raise ValueError(f"二次校验仍失败: {exc} | 回复片段: {content2[:200]!r}") from exc


def _render_rw(doc: dict) -> str:
    """把 related_works 段落渲染成评审输入文本(Claim 与其 Works)。"""
    out = []
    for b_idx, block in enumerate(doc.get("related_works") or []):
        for c in block.get("claims") or []:
            out.append(f"[Paragraph {b_idx + 1} Claim] {c}")
        for w in block.get("works") or []:
            auth = (w.get("authors") or [""])[0]
            yr = w.get("year") or "n/a"
            out.append(f"  - {w.get('title', '')} ({auth}, {yr})")
    return "\n".join(out)


def render_solution(sol: dict, limit: int = 16000) -> str:
    """渲染 solution 文本(idea + implementation,截断防超长)。"""
    idea = (sol.get("idea") or "").strip()
    impl = (sol.get("implementation") or "").strip()
    body = f"[Idea]\n{idea}\n\n[Implementation]\n{impl}"
    return truncate_chars(body, limit)


# =========================================================================== #
# 各评测任务:消息构造 + 结果校验
#
# 提示词严格依据 evaluation-guide.md 的各任务定义撰写,并补充可操作约束:
#   · 每维评分给出 1-5 的行为锚点,要求"理由必须引用方案/文本中的具体机制";
#   · 明令禁止以篇幅、文采、术语密度、格式等表面特征作为评分依据;
#   · 成对任务明确 A/B 仅是占位标签,要求先逐侧独立评估再比较(Tie 判据明确)。
# =========================================================================== #

# ---------- 1) 原子断言拆解(evaluation-guide.md §1.4.2-1:把人类 Claim C_H
#            拆解为 N 个原子断言集合 A(C_H)={a_1..a_N}) ----------
DECOMPOSE_SYS = SYSTEM_JUDGE + (
    " You are an expert in scientific-claim decomposition. An ATOMIC ASSERTION is a single, "
    "self-contained, independently verifiable factual or technical statement (e.g. one system "
    "property, one limitation, one empirical finding, one comparison). "
    "Decomposition rules you MUST follow:\n"
    "1. SPLIT compound claims: if a claim asserts several things (joined by 'and', 'but', "
    "';', 'as well as', or a list), emit one assertion per distinct fact.\n"
    "2. PRESERVE INFORMATION: every assertion must keep its full original semantics — subject, "
    "verb, objects, and qualifiers (degree, condition, scope, comparison object). Do NOT add "
    "facts that are not stated, do NOT merge two claims, do NOT drop any stated fact.\n"
    "3. RESOLVE REFERENCES: rewrite pronouns/ellipsis into complete sentences that are "
    "understandable without the rest of the claim.\n"
    "4. Do NOT emit motivation, rhetorical framing, or examples unless they state an "
    "independent verifiable fact.\n"
    "5. Each assertion must read as a standalone sentence that an expert could mark true or "
    "false on its own.")

def build_atomic_decompose(claims: List[str]) -> List[dict]:
    content = ("Decompose each of the following related-work claims into atomic assertions "
               "following the rules above. Output ALL atomic assertions across all claims in "
               "one flat list (keep their order).\n"
               'Return JSON: {"atomic_assertions": [string, ...]}\n\n'
               "=== Human Claims (C_H) ===\n"
               + "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(claims)))
    return [{"role": "system", "content": DECOMPOSE_SYS},
            {"role": "user", "content": content}]

def v_atomic(obj) -> dict:
    atoms = obj.get("atomic_assertions")
    if not isinstance(atoms, list) or not atoms or not all(isinstance(a, str) and a.strip() for a in atoms):
        raise ValueError("atomic_assertions 缺失或为空")
    return {"atomic_assertions": [a.strip() for a in atoms]}

# ---------- 2) 原子 Claim 支持判定(evaluation-guide.md §1.4.2-2:
#            逐一判定 C_L 是否支持 a_i,即 C_L ⇒ a_i 的语义包含/可推导指示函数) ----------
SUPPORT_SYS = SYSTEM_JUDGE + (
    " You are a strict textual-entailment judge. For every atomic assertion a_i you decide "
    "whether the provided text 'Model Claims' (C_L) supports it — notation C_L ⇒ a_i — "
    "i.e., whether C_L entails the assertion or a_i is derivable from C_L with at most 1-2 "
    "obvious domain-knowledge steps.\n"
    "Mark 1 (supported) ONLY when: at least one statement in Model Claims directly asserts the "
    "core proposition of a_i, or a_i follows from it with the explicit stated content "
    "(rephrasing with identical information counts; a different but true-sounding sentence "
    "about the same topic does NOT count).\n"
    "Mark 0 when: Model Claims never asserts the core proposition (information absent), only "
    "touches the same topic without covering a_i, or contradicts a_i.\n"
    "IMPORTANT: this is pure textual entailment between the two provided texts. Do not judge "
    "whether the human's paper is better, do not penalize the model for not citing specific "
    "papers, and do not use any outside knowledge beyond what is written.")

def build_support_check(model_claims_text: str, atoms: List[str]) -> List[dict]:
    items = "\n".join(f'{{"index": {i}, "atom": {json.dumps(a, ensure_ascii=False)}}}' for i, a in enumerate(atoms))
    content = ("For EVERY atomic assertion below, decide C_L ⇒ a_i (1 = supported, 0 = not "
               "supported), following the entailment rules above. Give one verdict per given "
               "index, in the same order. In 'evidence', quote the shortest supporting sentence "
               "of Model Claims, or write \"no supporting statement found\".\n"
               'Return JSON: {"verdicts": [{"index": int, "supported": 0 or 1, "evidence": string}, ...]}\n\n'
               f"=== Model Claims (C_L) ===\n{model_claims_text}\n\n"
               f"=== Atomic Assertions ===\n[{items}]")
    return [{"role": "system", "content": SUPPORT_SYS},
            {"role": "user", "content": truncate_chars(content, 22000)}]

def v_support(obj, n_atoms: int) -> dict:
    verdicts = obj.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) != n_atoms:
        raise ValueError("verdicts 数量与原子数不一致")
    out = []
    for v in verdicts:
        if v.get("supported") not in (0, 1):
            raise ValueError(f"supported 取值非法: {v}")
        out.append({"index": int(v.get("index")), "supported": int(v["supported"]),
                    "evidence": str(v.get("evidence", ""))[:220]})
    return {"verdicts": sorted(out, key=lambda x: x["index"])}

# ---------- 3) G-Eval 逻辑关联度(evaluation-guide.md §1.4.3:
#            LLM-as-a-Judge 评估由 Obs 推导至 C_L 的逻辑合理性,
#            标准思维链(CoT)评分,1-5 分) ----------
LOGIC_SYS = SYSTEM_JUDGE + (
    " You are an expert judge of scientific reasoning. Your task: score how logically sound "
    "the derivation from a Research Observation to a generated Core Claim is.\n"
    "Mandatory CoT procedure (do it inside 'reason'):\n"
    "STEP 1 — List the key facts/observations stated in the Observation (F).\n"
    "STEP 2 — List every premise that the Core Claim needs to be concluded (P1, P2, ...).\n"
    "STEP 3 — For each premise P: state whether it (a) is directly implied by F, (b) is a "
    "widely accepted domain fact/commonsense, or (c) has no support in F and no obvious "
    "domain basis.\n"
    "STEP 4 — Score 1-5 by the number and importance of premises of type (c):\n"
    "  1 = the claim is unrelated to the observation or directly contradicts it;\n"
    "  2 = only weakly related, key derivation steps are unsupported or jumpy;\n"
    "  3 = plausible overall but with at least one visible gap (a non-trivial premise of "
    "      type (c), or a leap the observation does not warrant);\n"
    "  4 = reasoning is essentially sound, only minor elaborations missing;\n"
    "  5 = the observation (plus obvious domain knowledge) suffices to conclude the claim; "
    "      no gap, the derivation is closed.\n"
    "Score the logic of the DERIVATION, not the truth of the claim itself, and not the style "
    "or length of the text.")

def build_logic_score(obs: str, claims_text: str) -> List[dict]:
    content = (f"Apply the CoT procedure (STEP 1-4) and return the final integer score.\n\n"
               f"=== Research Observation ===\n{obs}\n\n"
               f"=== Core Claim (C_L, generated by an LLM) ===\n{claims_text}\n\n"
               'Return JSON: {"score": int 1-5, "reason": "STEP1..STEP4 summary, then the score"}')
    return [{"role": "system", "content": LOGIC_SYS},
            {"role": "user", "content": truncate_chars(content, 12000)}]

def v_logic(obj) -> dict:
    return {"score": clean_json_number(obj.get("score"), 1, 5, 3),
            "reason": str(obj.get("reason", ""))[:800]}

# ---------- 4) 4 维 Rubric 独立打分(evaluation-guide.md §2.1 四维:针对性 s_tgt /
#            技术可行性 s_feas / 创新性 s_nov / 继承性 s_grd,各 1-5) ----------
RUBRIC_DIMS = ["targetedness", "feasibility", "novelty", "groundedness"]

RUBRIC_ANCHORS = {
    "targetedness": (
        "TARGETEDNESS — whether the solution precisely addresses the CORE CONTRADICTION/"
        "problem stated in the Observation.\n"
        "How to judge: (i) identify the core problem the observation raises; (ii) check whether "
        "the solution's mechanism is aimed at exactly that problem (not a neighbouring or "
        "generic one).\n"
        "1 = solution ignores the observed core problem or targets a different problem;\n"
        "2 = only superficially related to the core problem, main thrust misses it;\n"
        "3 = targets the core problem but with partial or indirect coverage;\n"
        "4 = clearly aimed at the core problem and covers its central aspect(s);\n"
        "5 = precisely targets and systematically resolves the core contradiction raised by "
        "the observation."),
    "feasibility": (
        "FEASIBILITY — whether the solution is sound in mathematics, logic and "
        "engineering, i.e. has no fatal loopholes.\n"
        "How to judge: scan for (a) mathematical/logical errors or circular reasoning, "
        "(b) engineering impossibilities or violations of clearly stated physical/system "
        "constraints, (c) dependence on unstated magic or unrealistic assumptions, "
        "(d) internally inconsistent component design. If a fatal flaw exists, the score "
        "must be <= 2 regardless of how well the text is written.\n"
        "1 = contains a fatal, disqualifying flaw (impossible, self-contradictory);\n"
        "2 = major unresolved feasibility problems or key components left unverifiable;\n"
        "3 = basically workable; a few non-trivial details lack argumentation;\n"
        "4 = technically sound with only minor, clearly fixable loose ends;\n"
        "5 = rigorous: mathematics/logic/engineering are self-consistent with no substantive "
        "flaw or unjustified assumption."),
    "novelty": (
        "NOVELTY — whether the solution goes beyond a trivial stacking of existing "
        "baseline techniques (平庸解).\n"
        "How to judge: compare against 'what any competent engineer would assemble from the "
        "surveyed techniques'. New mechanisms, non-obvious design moves, or genuinely "
        "different solution principles score higher; renaming, re-ordering or plain "
        "combination of known parts does not.\n"
        "1 = trivial re-assembly or renaming of existing components;\n"
        "2 = mostly known techniques with at most cosmetic changes;\n"
        "3 = some non-trivial adaptation/integration beyond naive stacking, but idea still "
        "close to existing combinations;\n"
        "4 = clearly novel mechanism or design that a baseline assembler would not produce;\n"
        "5 = highly original, non-obvious solution principle that breaks with the obvious "
        "baseline path."),
    "groundedness": (
        "GROUNDEDNESS — whether the solution EXPLICITLY and LOGICALLY builds on the "
        "technical routes provided in the input Related Work (S_H).\n"
        "How to judge: check that concrete mechanisms of the cited related works are named "
        "and converted into design decisions of the solution (e.g., 'we extend X's loss', "
        "'unlike Y's module we ...'). Generic statements ('prior work exists', 'inspired by "
        "the literature') without a concrete route do NOT count as grounded.\n"
        "1 = no use at all of the provided related work;\n"
        "2 = vague references, no technical route is actually exploited;\n"
        "3 = some concrete mechanisms are used but weakly integrated;\n"
        "4 = explicitly names and reasonably builds on several related technical routes;\n"
        "5 = systematically and coherently derives its key design from the input related "
        "work's routes and clearly states each inheritance relation."),
}

def _rubric_scale() -> str:
    return "\n".join(RUBRIC_ANCHORS[k] for k in RUBRIC_DIMS)

_RUBRIC_RULES = (
    "General rules for all four dimensions:\n"
    "1. Judge each dimension INDEPENDENTLY, using only the anchors above.\n"
    "2. Base every score on the technical content of the Solution text; cite the concrete "
    "mechanism/sentence you rely on inside 'reason' (one short quote or pointer per dimension).\n"
    "3. NEVER let text length, formatting, eloquence, number of named papers, or "
    "terminology density influence any score.\n"
    "4. If a dimension cannot be judged from the text at all, score it at the level matching "
    "the weakest anchor you can defend and say why in the reason.\n"
    "5. Scores are integers 1-5.")

def build_rubric_score(obs: str, rw_text: str, sol_text: str) -> List[dict]:
    content = (f"Evaluate the Solution below with the rubric.\n\n{_rubric_scale()}\n\n"
               f"{_RUBRIC_RULES}\n\n"
               f"=== Observation ===\n{obs}\n\n"
               f"=== Related Work (S_H — the input the solution was built from) ===\n{rw_text}\n\n"
               f"=== Solution to score (Sol) ===\n{sol_text}\n\n"
               'Return JSON: {"targetedness": int, "feasibility": int, "novelty": int, '
               '"groundedness": int, "reason": string with one evidence sentence per dimension}. Use EXACTLY the keys targetedness / feasibility / novelty / groundedness (never abbreviate them)')
    return [{"role": "system", "content": SYSTEM_JUDGE},
            # 截断仅作兜底:Solution 位于 prompt 末尾,24000 上限曾截掉过长方案的
            # Implementation 尾部(2026-09-07 修正,46000 覆盖本数据集最坏 ~28k 字符)
            {"role": "user", "content": truncate_chars(content, 46000)}]

def v_rubric(obj) -> dict:
    scores = _scores_from(obj)   # 兼容 targetedness 规范键与 s_tgt 等别名键
    return {**scores, "reason": str(obj.get("reason", ""))[:900]}

# ---------- 5) 关键技术要素抽取(evaluation-guide.md §2.2.2-1:
#            Sol_H 抽取 K 个关键技术要素 T(Sol_H)={t_1..t_K};
#            要素例如:损失函数改进、新网络模块、启发式算法等) ----------
ASPECT_SYS = SYSTEM_JUDGE + (
    " You extract KEY TECHNICAL ASPECTS of a research solution. A key technical aspect is a "
    "concrete, independently implementable design decision that materially determines the "
    "solution's behavior (e.g., a loss/objective-function change, a new network module or "
    "layer, a scheduling or routing heuristic, a novel algorithmic component, a specific "
    "system mechanism, a protocol rule). \n"
    "Rules: extract 5-12 aspects ordered by importance; each aspect string must be of the form "
    "\"<short name>: <one-sentence definition of the mechanism>\"; DO NOT include motivation, "
    "problem restatement, experimental/evaluation content, or performance numbers.")

def build_aspect_extract(sol_text: str) -> List[dict]:
    content = ("Extract the key technical aspects of the Human-written solution below.\n"
               'Return JSON: {"aspects": ["<name>: <definition>", ...]}\n\n'
               f"=== Human Solution (Sol_H, reference for aspect extraction) ===\n{sol_text}")
    return [{"role": "system", "content": ASPECT_SYS},
            {"role": "user", "content": truncate_chars(content, 16000)}]

def v_aspects(obj) -> dict:
    a = obj.get("aspects")
    if not isinstance(a, list) or not a:
        raise ValueError("aspects 缺失或为空")
    return {"aspects": [str(x).strip() for x in a][:12]}

# ---------- 6) 关键技术要素覆盖判定(evaluation-guide.md §2.2.2-2:
#            t_j is addressed in Sol_L 的指示函数) ----------
def build_aspect_coverage(sol_text: str, aspects: List[str]) -> List[dict]:
    items = "\n".join(f'{{"index": {i}, "aspect": {json.dumps(a, ensure_ascii=False)}}}' for i, a in enumerate(aspects))
    content = ("For each key technical aspect t_j (extracted from the human solution), decide "
               "whether the Candidate Solution (an LLM solution for the same observation) "
               "ADDRESSES it.\n"
               "addressed = 1 ONLY when the candidate solution explicitly describes the "
               "mechanism itself (a concrete component/steps/rule that realizes t_j), not "
               "merely the same goal. Mentioning t_j only as related work, background, or "
               "future work => 0. A different mechanism that serves the same purpose without "
               "implementing t_j => 0.\n"
               "In 'evidence', quote the shortest candidate-solution sentence supporting your "
               "decision, or write \"no matching mechanism found\".\n"
               'Return JSON: {"coverage": [{"index": int, "addressed": 0 or 1, "evidence": string}, ...]}\n\n'
               f"=== Key Technical Aspects ===\n[{items}]\n\n"
               f"=== Candidate Solution (Sol_L) ===\n{sol_text}")
    return [{"role": "system", "content": SYSTEM_JUDGE},
            {"role": "user", "content": truncate_chars(content, 24000)}]

def v_coverage(obj, n: int) -> dict:
    cov = obj.get("coverage")
    if not isinstance(cov, list) or len(cov) != n:
        raise ValueError("coverage 数量不一致")
    out = []
    for c in cov:
        if c.get("addressed") not in (0, 1):
            raise ValueError(f"addressed 取值非法: {c}")
        out.append({"index": int(c.get("index")), "addressed": int(c["addressed"]),
                    "evidence": str(c.get("evidence", ""))[:220]})
    return {"coverage": sorted(out, key=lambda x: x["index"])}

# ---------- 7) 成对双盲对比(evaluation-guide.md §3.1:消除位置偏置的位置对调双盲评估;
#            每轮输出四维度评分及偏好判断 O ∈ {Win_A, Tie, Win_B}) ----------
def build_pairwise(obs: str, sol_a: str, sol_b: str, label_a: str = "A", label_b: str = "B") -> List[dict]:
    la, lb = label_a, label_b
    content = (
        f"Below are two candidate solutions (labeled {la} and {lb}) for the same "
        f"research Observation. The labels are arbitrary placeholders assigned at random — "
        f"they carry NO information about order, source, or expected quality. Judge the two "
        f"candidates strictly by their content.\n\n"
        f"{_rubric_scale()}\n\n{_RUBRIC_RULES}\n\n"
        f"=== Observation ===\n{obs}\n\n"
        f"=== Candidate {la} ===\n{sol_a}\n\n"
        f"=== Candidate {lb} ===\n{sol_b}\n\n"
        "Evaluation procedure:\n"
        f"1) Score Candidate {la} on the four dimensions -> a_scores.\n"
        f"2) Score Candidate {lb} on the four dimensions -> b_scores.\n"
        f"3) Compare the two score vectors: prefer \"{la}\" only if it is clearly better "
        f"overall or wins the decisive dimension(s); prefer \"{lb}\" analogously; choose "
        "\"Tie\" when the two are comparable — each wins some dimension, or the gap is "
        "within 1 point on most dimensions. Do NOT invent a winner for similar candidates.\n"
        "4) In 'reason', give the main score evidence for each candidate and the comparison "
        "conclusion (2-4 sentences).\n"
        f'Return JSON: {{"preference": "{la}" | "{lb}" | "Tie", '
        '"a_scores": {"targetedness": int, "feasibility": int, "novelty": int, '
        '"groundedness": int}, "b_scores": {same 4 fields}, "reason": string}')
    return [{"role": "system", "content": SYSTEM_JUDGE},
            # 截断仅作兜底:两候选(各 ≤16k)位于 prompt 末尾,32000 曾截掉最长样本
            # Candidate B 尾部 ~300 字符(2026-09-07 修正为 46000)
            {"role": "user", "content": truncate_chars(content, 46000)}]

_PREF_MAP = {"a": "A", "b": "B", "tie": "Tie", "ties": "Tie", "win_a": "A",
             "win_b": "B", "candidate a": "A", "candidate b": "B", "equal": "Tie",
             "no preference": "Tie", "none": "Tie", "cannot decide": "Tie"}


def _norm_key(k) -> str:
    return str(k).lower().replace(" ", "").replace("_", "").replace("-", "")


# 四维分数的键名别名(模型偶发输出 s_tgt / tgt 等缩写) -> 规范键
_ALIAS_TO_CANON = {
    "targetedness": "targetedness", "stgt": "targetedness", "tgt": "targetedness",
    "feasibility": "feasibility", "sfeas": "feasibility", "feas": "feasibility",
    "novelty": "novelty", "snov": "novelty", "nov": "novelty",
    "groundedness": "groundedness", "sgrd": "groundedness", "grd": "groundedness",
}


def _num_or_score(val) -> Optional[int]:
    """把值收敛为 1-5 整数:直接数字,或 dict 中的 score/value/rating 子键。"""
    if isinstance(val, dict):
        for sub in ("score", "value", "rating"):
            if sub in val:
                val = val[sub]
                break
        else:
            return None
    try:
        n = int(round(float(val)))
    except (TypeError, ValueError):
        return None
    return max(1, min(5, n))


def _scores_from(container: dict) -> dict:
    """从任意容器(dict)中抽取四维分数(兼容规范键、s_tgt 等别名键、score 子键嵌套)。"""
    found = {}
    for key, val in container.items():
        canon = _ALIAS_TO_CANON.get(_norm_key(key))
        if not canon:
            continue
        if isinstance(val, dict):
            # 嵌套 {A:{score}, B:{score}} 之类:取第一个可解析值(调用方负责转置时已拆)
            n = _num_or_score(val)
            if n is None:
                # 深层 dict:在任意子值中找数字/score 键
                for sub in val.values():
                    n = _num_or_score(sub)
                    if n is not None:
                        break
        else:
            n = _num_or_score(val)
        if n is not None:
            found[canon] = n
    missing = [k for k in RUBRIC_DIMS if k not in found]
    if missing:
        raise ValueError(f"候选缺维度 {missing},键: {list(container.keys())[:6]}")
    return {k: found[k] for k in RUBRIC_DIMS}


def _parse_candidate(cd: dict) -> dict:
    """解析单侧四维分(兼容规范键与 'Targetedness'/'s_tgt' 等变体);缺维度视为非法。"""
    return _scores_from(cd)


def v_pairwise(obj, identical: bool = False) -> dict:
    """兼容多种返回结构:
    约定式: {preference, a_scores{4维}, b_scores{4维}, reason}
    漂移式 1: {"Candidate A": {4维}, "Candidate B": {4维}} / 顶层 "A"/"B"
    漂移式 2: {candidate_a_scores: {...}, candidate_b_scores: {...}}
    漂移式 3: {targetedness: {A: {...}}, feasibility: {B: {...}}, ...}(按标签转置)
    缺失 preference 且两侧四维分完全相同 -> 判 Tie(identical-pair 控制的合理落点);
    对 identical 控制任务(两候选实为同一文本),即便裁判给出不同分数也按 Tie 计
    (同文不同分本身即判定噪声,不应判任何一方胜);否则视为非法并重试。"""
    a_s = b_s = None

    def _two_side(a_container, b_container) -> bool:
        nonlocal a_s, b_s
        if a_s is not None or b_s is not None:
            return False
        if isinstance(a_container, dict) and isinstance(b_container, dict):
            a_s = _scores_from(a_container)
            b_s = _scores_from(b_container)
            return True
        return False

    # 结构 1/2: a_scores/b_scores 或 candidate_a_scores/candidate_b_scores 键
    sides = {}
    for key, val in obj.items():
        nk = _norm_key(key)
        if nk in ("ascores", "candidateascores", "scoresa", "solutionascores", "modelascores"):
            sides["a"] = val
        elif nk in ("bscores", "candidatebscores", "scoresb", "solutionbscores", "modelbscores"):
            sides["b"] = val
    if "a" in sides and "b" in sides:
        _two_side(sides["a"], sides["b"])
    else:
        # 结构 3: "Candidate A"/"Candidate B" / 顶层 "A"/"B"(大小写不敏感)
        for key, val in obj.items():
            nk = _norm_key(key)
            if nk in ("candidatea", "solutiona", "modela", "a", "candidate1", "solution1"):
                if isinstance(val, dict) and a_s is None:
                    a_s = _scores_from(val)
            elif nk in ("candidateb", "solutionb", "modelb", "b", "candidate2", "solution2"):
                if isinstance(val, dict) and b_s is None:
                    b_s = _scores_from(val)
    if a_s is None or b_s is None:
        # 结构 4: 顶层按维度组织 {targetedness: {A: {...}, B: {...}}, ...}(转置回两侧)
        per_dim = {k: v for k, v in obj.items()
                   if _norm_key(k) in RUBRIC_DIMS and isinstance(v, dict)}
        if len(per_dim) >= 3:
            ta, tb = {}, {}
            ok4 = True
            for k, v in per_dim.items():
                la = lb = None
                for sub_key, sub_val in v.items():
                    nk = _norm_key(sub_key)
                    if nk in ("a", "candidatea"):
                        la = sub_val
                    elif nk in ("b", "candidateb"):
                        lb = sub_val
                if la is None or lb is None:
                    ok4 = False
                    break
                ta[k] = la
                tb[k] = lb
            if ok4:
                try:
                    a_s = _scores_from(ta)
                    b_s = _scores_from(tb)
                except ValueError:
                    a_s = b_s = None
    if a_s is None or b_s is None:
        raise ValueError(f"无法定位两侧四维分: {list(obj.keys())[:6]}")
    # preference:顶层键(大小写/连字符不敏感)
    pref = None
    for key, val in obj.items():
        if _norm_key(key) in ("preference", "winner", "verdict", "decision", "preferred"):
            if isinstance(val, str):
                cand = _PREF_MAP.get(val.strip().lower())
                if cand:
                    pref = cand
                    break
            elif isinstance(val, dict):
                # 偶发结构: preference: {"winner": "A"}
                for k2, v2 in val.items():
                    if _norm_key(k2) in ("winner", "choice", "preference") and isinstance(v2, str):
                        cand = _PREF_MAP.get(v2.strip().lower())
                        if cand:
                            pref = cand
                            break
    if pref is None:
        if identical:
            pref = "Tie"        # identical 控制:同文 -> Tie(分数不一致 = 判定噪声)
        elif a_s == b_s:
            pref = "Tie"        # 缺失偏好但双方案四维分完全相同 -> Tie
    if pref not in ("A", "B", "Tie"):
        raise ValueError(f"preference 无法判定: {pref}")
    # reason:顶层 reason 或各候选结构中的说明
    reason = ""
    for key in ("reason", "rationale", "explanation"):
        if obj.get(key):
            reason = str(obj[key])
            break
    return {"preference": pref,
            "a_scores": {k: (a_s.get(k) if a_s.get(k) is not None else 3) for k in RUBRIC_DIMS},
            "b_scores": {k: (b_s.get(k) if b_s.get(k) is not None else 3) for k in RUBRIC_DIMS},
            "reason": reason[:500]}


# =========================================================================== #
# 任务注册:批量执行(断点续跑)入口
# =========================================================================== #
def _worker_factory(kind: str):
    """构造 (messages_builder, validator) 配置:kind -> (build, validate)"""
    builders = {
        "atomic_decompose": (lambda it: (build_atomic_decompose(it["claims"]), v_atomic)),
        "support_check": (lambda it: (build_support_check(it["model_claims"], it["atoms"]),
                                      lambda obj: v_support(obj, len(it["atoms"])))),
        "logic_score": (lambda it: (build_logic_score(it["obs"], it["claims_text"]), v_logic)),
        "rubric_score": (lambda it: (build_rubric_score(it["obs"], it["rw_text"], it["sol_text"]), v_rubric)),
        "aspect_extract": (lambda it: (build_aspect_extract(it["sol_text"]), v_aspects)),
        "aspect_coverage": (lambda it: (build_aspect_coverage(it["sol_text"], it["aspects"]),
                                        lambda obj: v_coverage(obj, len(it["aspects"])))),
        "pairwise": (lambda it: (build_pairwise(it["obs"], it["sol_a"], it["sol_b"],
                                                it.get("label_a", "A"), it.get("label_b", "B")),
                                 lambda obj: v_pairwise(obj, identical=bool(it.get("_identical"))))),
    }
    return builders[kind]


def run_judge_tasks(items: List[dict], kind: str, judge: JudgeLLM,
                    store: JsonlStore, redo: bool = False,
                    workers: Optional[int] = None, desc: Optional[str] = None) -> Dict[str, dict]:
    """对一组任务批量调用裁判。item 需含 _key;结果 {_key, kind, ok, result/error, ts}。

    已缓存(store 中 ok=True)自动跳过 -> 支持断点续跑;redo=True 时先清空缓存重算全部。
    """
    desc = desc or f"judge:{kind}"
    if redo and store.path.exists():
        store.path.unlink()
        store = JsonlStore(store.path)
    # 失败(ok=False)的缓存条目清掉,保证重跑时自动重试(幂等补跑的关键)
    bad = [it["_key"] for it in items
           if (store.get(it["_key"]) or {}).get("ok") is False]
    for k in bad:
        store.remove(k)
    if bad:
        log(f"[{desc}] 清理 {len(bad)} 条失败缓存,将自动重试")

    def worker(it: dict) -> Optional[dict]:
        msg_builder, validator = _worker_factory(kind)(it)
        try:
            obj = ask_json(judge, msg_builder, validator, task_key=it["_key"])
            return {"_key": it["_key"], "kind": kind, "ok": True, "result": obj,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as exc:
            log(f"[{desc}] {it['_key']} 裁判失败: {exc}")
            return {"_key": it["_key"], "kind": kind, "ok": False,
                    "error": str(exc)[:300], "ts": time.strftime("%Y-%m-%d %H:%M:%S")}

    results = run_pool(items, worker, store, workers=workers or config.LLM_WORKERS,
                       min_interval=config.LLM_MIN_INTERVAL, desc=desc)
    return results
