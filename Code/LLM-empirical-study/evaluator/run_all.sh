#!/usr/bin/env bash
# =============================================================================
# RQ2-1/2/3 评测一键运行脚本(本地执行;所有阶段可中断续跑,重复执行同一命令即断点续传)
#
# 用法:
#   bash run_all.sh            # 全流程:RQ2-1 -> RQ2-2 -> RQ2-3(推荐后台 nohup bash run_all.sh > logs 2>&1)
#   bash run_all.sh --redo     # 强制重跑全部 LLM 裁判阶段(S2/嵌入缓存保留)
#   bash run_all.sh --limit 1  # 只跑 1 个样本(调试用)
#
# 可选环境变量:
#   GPU="0,1"                 # 使用的 GPU(默认 0,1;需在已配好的环境里运行)
#   LLM_WORKERS=6            # LLM 并发(默认 6)
#   LLM_BACKEND=qwen|glm     # 裁判后端(默认 qwen=DashScope;README 指定的 zai/GLM 需自行配置)
#   QWEN_API_KEY=...         # 覆盖 config.py 中的 key
# =============================================================================
set -u
cd "$(dirname "$0")"

# ---------- 1) 环境与 GPU(Python 环境由用户自行配好,脚本不做检测) ----------
PY="${PY:-python}"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"   # huggingface.co 被墙,统一走镜像
export CUDA_VISIBLE_DEVICES="${GPU:-0,1}"
export LLM_WORKERS="${LLM_WORKERS:-6}"
export LLM_BACKEND="${LLM_BACKEND:-qwen}"

ARGS=""
for a in "$@"; do ARGS="$ARGS $a"; done

echo "==> Python: $PY | GPU: $CUDA_VISIBLE_DEVICES | 参数:$ARGS"
mkdir -p outputs/logs

# ---------- 2) 模型完整性检查(缺则从 hf.mirror 下载) ----------
check_model() {  # $1=目录 $2=描述
    if [ ! -f "$1/config.json" ] || { [ ! -f "$1/model.safetensors" ] && [ ! -f "$1/pytorch_model.bin" ]; }; then
        echo "==> 缺失编码模型($2),开始从 hf-mirror 下载(约 1.3GB)…"
        "$PY" -B model/download_models.py || { echo "[错误] 模型下载失败" >&2; exit 1; }
        return
    fi
    echo "==> 模型就绪: $2"
}
check_model model/specter2_base "SPECTER2(论文/文本语义向量)"
check_model model/nli-deberta-v3-base "DeBERTa-NLI(Claim 忠实度)"

# ---------- 3) 依次执行三个子任务评测 ----------
echo; echo "################ RQ2-1:相关工作与 Claim 生成能力 ################"
"$PY" -B run_rq2_1.py $ARGS 2>&1 | tee outputs/logs/run_rq2_1.log
[ ${PIPESTATUS[0]} -eq 0 ] || { echo "[错误] RQ2-1 未成功结束(可重跑续传)" >&2; exit 1; }

echo; echo "################ RQ2-2:基于人类 RW 的 Solution 质量 ################"
"$PY" -B run_rq2_2.py $ARGS 2>&1 | tee outputs/logs/run_rq2_2.log
[ ${PIPESTATUS[0]} -eq 0 ] || { echo "[错误] RQ2-2 未成功结束(可重跑续传)" >&2; exit 1; }

echo; echo "################ RQ2-3:LLM-RW vs Human-RW 对 Solution 影响与归因 ################"
"$PY" -B run_rq2_3.py $ARGS 2>&1 | tee outputs/logs/run_rq2_3.log
[ ${PIPESTATUS[0]} -eq 0 ] || { echo "[错误] RQ2-3 未成功结束(可重跑续传)" >&2; exit 1; }

# ---------- 4) 汇总提示 ----------
cat <<'EOF'

================================= 全部评测完成 =================================
最终报告(均为 md + json):
  outputs/reports/rq2_1_withsearch.md    outputs/reports/rq2_1_withsearch.json
  outputs/reports/rq2_1_withoutsearch.md outputs/reports/rq2_1_withoutsearch.json
  outputs/reports/rq2_2.md               outputs/reports/rq2_2.json
  outputs/reports/rq2_3_withsearch.md    outputs/reports/rq2_3_withsearch.json
  outputs/reports/rq2_3_withoutsearch.md outputs/reports/rq2_3_withoutsearch.json
中间结果(可溯源/续跑):
  outputs/cache/      S2 解析与文本向量缓存
  outputs/judge/      每条 LLM 裁判原始结果(含 usage 记账)
说明文档:README-评测说明.md
==============================================================================
EOF
