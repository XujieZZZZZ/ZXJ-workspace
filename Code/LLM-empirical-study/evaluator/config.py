# -*- coding: utf-8 -*-
"""评估框架全局配置:路径、API keys、模型与阈值(全部集中在此,便于核对与切换)。

设计说明:
- 评测公式与阈值严格来自 evaluation-guide.md(不得随意更改);如需实验性调整,
  请在命令行/调用处覆盖,不要改动本文件的默认值。
- API key 遵循项目既有习惯(明文默认值 + 环境变量覆盖,见 data/LLM_extract_and_generate 下脚本)。
- LLM 后端:evaluator/README.md 要求 GLM(zai 客户端),经实测该 key/端点/包不可达,
  用户改用阿里云 DashScope 的 OpenAI 兼容端点(Qwen),模型 id 实测为 qwen3-max
  (README 中 "Qwen3.8max" 并非有效 id)。代码保留 backend="glm" 的适配入口,
  将来 zai/GLM 可用时仅需在 GLM_BASE_URL/GLM_API_KEY 处填入并设 backend="glm"。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# 目录路径
# --------------------------------------------------------------------------- #
EVALUATOR_DIR = Path(__file__).resolve().parent            # evaluator/
PROJECT_DIR   = EVALUATOR_DIR.parent                        # LLM-empirical-study/
DATA_DIR      = PROJECT_DIR / "data"
HUMAN_DATA_DIR   = DATA_DIR / "human_data"
LLM_DATA_DIR     = DATA_DIR / "LLM_data"
# 评估只读这三份 merged 数据(已由 reorganize_dataset.py 审计对齐;pdf_mapping.jsonl 中旧路径已失效)
MERGED_HUMAN_RE_DIR   = LLM_DATA_DIR / "merged_human_re"          # Observation+Human RW -> LLM Solution
MERGED_WITHSEARCH_DIR = LLM_DATA_DIR / "merged_llm_re_withsearch"     # LLM RW(带检索) -> LLM Solution
MERGED_WITHOUTSEARCH_DIR = LLM_DATA_DIR / "merged_llm_re_withoutsearch"  # LLM RW(不带检索) -> LLM Solution

MODEL_DIR    = EVALUATOR_DIR / "model"                     # README 要求单独建立的 model 文件夹
SPECTER2_DIR = MODEL_DIR / "specter2_base"                 # 论文/文本编码模型(allenai/specter2_base)
NLI_DIR      = MODEL_DIR / "nli-deberta-v3-base"           # 蕴含判定模型(cross-encoder/nli-deberta-v3-base)

# 可选语义编码器(2026-09 新增;--emb 切换,模型从 hf-mirror 下载,见 model/download_models.py)
#  key -> (主模型目录, 展示名, adapter 目录(None=无), 池化口径)
#    "st"  = sentence-transformers 默认 mean pooling + L2(specter2_base/scibert 同口径,与既有结果一致)
#    "cls" = SPECTER2 官方用法:adapters 库加载 base+adapter 后取 [CLS] + L2
EMB_CHOICES = {
    "specter2_base": (MODEL_DIR / "specter2_base", "allenai/specter2_base", None, "st"),
    "specter2": (MODEL_DIR / "specter2_base",
                 "allenai/specter2_base + allenai/specter2 [PRX proximity]", MODEL_DIR / "specter2", "cls"),
    "scibert": (MODEL_DIR / "scibert_scivocab_uncased", "allenai/scibert_scivocab_uncased", None, "st"),
}
EMB_DEFAULT = "specter2_base"

OUTPUTS_DIR  = EVALUATOR_DIR / "outputs"
CACHE_DIR    = OUTPUTS_DIR / "cache"                       # S2 解析 / 嵌入向量等中间缓存
JUDGE_DIR    = OUTPUTS_DIR / "judge"                       # LLM 裁判逐条结果(断点续跑)
REPORTS_DIR  = OUTPUTS_DIR / "reports"                     # 最终报告(md / json)
TOP_VENUES_FILE = EVALUATOR_DIR / "data_refs" / "top_venues.json"   # CCF-A/B + Core A* 名册

# 兼容本项目的共享模型目录中的大模型:如无则忽略(本评估只用上述两个小模型)

def ensure_dirs() -> None:
    """确保全部输出/缓存目录存在(评估可随时中断,结果落盘后即可续跑)。"""
    for d in (MODEL_DIR, OUTPUTS_DIR, CACHE_DIR, JUDGE_DIR, REPORTS_DIR,
              EVALUATOR_DIR / "data_refs"):
        d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# API keys(环境变量可覆盖)
# --------------------------------------------------------------------------- #
# Semantic Scholar(README 提供;探测结论:key 有效,免费层共享池易 429,客户端已做退避)
S2_API_KEY = os.environ.get("S2_API_KEY", "s2k-47rvmMbF6pmi4CLwEfi75iZb9JTCLssKiZOIl8TS")

# LLM 裁判后端(默认 Qwen / DashScope,OpenAI 兼容;README 指定的 zai/GLM 信息保留于下方常量)
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_API_KEY   = os.environ.get("QWEN_API_KEY",
    "sk-ws-H.PMERDDE.KUlR.MEUCIHKULdlR-lOjIZwBh6YzobtE4imvY5x5vfzAZwpbxBenAiEA9GNxZbvR6ODilv1rtdrV1Ei9m4N-H2AmG_VcCq35OP0")
QWEN_MODEL     = os.environ.get("QWEN_MODEL", "qwen3-max")   # 用户所称 "Qwen3.8max" 对应此模型 id(实测)

# README 中的 GLM 接入信息(暂不可达,保留以备接入;backend="glm" 时使用)
GLM_ZAI_API_KEY = os.environ.get("GLM_ZAI_API_KEY", "653c63813b434d8592e86ce3119b3a5a.OmxKZCphP0iQsGij")
GLM_BASE_URL    = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
GLM_MODEL       = os.environ.get("GLM_MODEL", "glm-5.3")

# DeepSeek(OpenAI 兼容端点):用作 RQ2-3 的交叉裁判(胜率稳定性),与生成阶段同款 key/模型
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY",
    "sk-626347bcc3b1436abfbee20761eb4940")   # 与 data/LLM_extract_and_generate 脚本同一把
DEEPSEEK_MODEL    = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# --------------------------------------------------------------------------- #
# LLM 后端选择与调用参数
# --------------------------------------------------------------------------- #
LLM_BACKEND = os.environ.get("LLM_BACKEND", "qwen")   # "qwen"(DashScope 实测可用) | "glm"(zai 兼容位) | "deepseek"
LLM_TEMPERATURE = 0.2                                 # 裁判任务统一低温,增强可复现
LLM_MAX_TOKENS  = 4096
# DeepSeek-v4-flash 默认自带思考(reasoning_content 计入 completion 配额),
# 长评审任务思考可能占满 4096 导致 content 为空 -> 单独给足上限
LLM_MAX_TOKENS_DS = int(os.environ.get("LLM_MAX_TOKENS_DS", "20000"))
LLM_WORKERS     = int(os.environ.get("LLM_WORKERS", "6"))   # 并发线程数
LLM_MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "0.5"))  # 两次请求最小间隔(秒),防限流

# Semantic Scholar 请求间隔(秒):教程规定个人 key = 1 req/s;按用户要求保守取
# 6s/次(≤10 次/分钟),可通过环境变量 S2_MIN_INTERVAL 调整(如改 1.0 恢复满速)。
S2_MIN_INTERVAL = float(os.environ.get("S2_MIN_INTERVAL", "6.0"))

# --------------------------------------------------------------------------- #
# 编码模型与 GPU
# --------------------------------------------------------------------------- #
CUDA_DEVICE = os.environ.get("CUDA_VISIBLE_DEVICES", "0")  # 由 launch 脚本/命令设置,默认 GPU0
EMBEDDING_DIM = 768            # specter2_base 输出维度(与模型一致,勿改)

# --------------------------------------------------------------------------- #
# evaluation-guide.md 阈值与参数(一一对应,勿随意改;如需实验请在调用处覆盖)
# --------------------------------------------------------------------------- #
JW_THRESHOLD  = 0.90      # Level2: JaroWinkler(标题) 下界
YEAR_MAX_DELTA = 1        # Level2: 年份差上界
COS_THRESHOLD = 0.92      # Level3: SPECTER2 向量余弦下界
RECENT_YEARS  = 3         # 近 3 年论文判定区间(Recency Ratio)
CURRENT_YEAR  = datetime.now().year   # RR 的基准年份(=2026,发文环境年份)
# RQ2-2 综合质量得分权重(指南: Σw_k=1;用户确认取均权,权重可在此调整)
SOL_WEIGHTS = {"targetedness": 0.25, "feasibility": 0.25, "novelty": 0.25, "groundedness": 0.25}
S2_FOUND_MIN_SIM = 0.90   # S2 解析认为"检索到同一篇"的最低归一化标题相似度(低于视为检索失败/可能编造)

# --------------------------------------------------------------------------- #
# LLM 调用代理等
# --------------------------------------------------------------------------- #
LOCAL = os.environ.get("LOCAL", "")  # 预留(如需本地代理如 clash,设 http://127.0.0.1:7890)
PROXIES = {"http": LOCAL, "https": LOCAL} if LOCAL else None
