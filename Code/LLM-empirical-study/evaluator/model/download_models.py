# -*- coding: utf-8 -*-
"""从国内镜像 hf.mirror 下载评估所需编码模型到本 model/ 文件夹(evaluator/README.md 要求)。

用法(需具备 torch/sentence-transformers 的环境,如 conda ai4system):
    HF_ENDPOINT=https://hf-mirror.com python download_models.py
已下载的模型会自动跳过(支持断点)。
"""
import os
import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
MODELS = [  # (hf repo id, 本地目录名, 用途)
    ("allenai/specter2_base", "specter2_base", "论文/文本语义向量 SPECTER2(base,默认)"),
    ("allenai/specter2", "specter2", "论文/文本语义向量 SPECTER2(官方完整版,1024 维)"),
    ("allenai/scibert_scivocab_uncased", "scibert_scivocab_uncased", "论文/文本语义向量 SciBERT(对照)"),
    ("cross-encoder/nli-deberta-v3-base", "nli-deberta-v3-base", "Claim 忠实度蕴含判定"),
]


def _complete(dir_path: Path) -> bool:
    has_weights = list(dir_path.glob("model.safetensors")) or list(dir_path.glob("pytorch_model.bin"))
    return dir_path.joinpath("config.json").exists() and bool(has_weights)


def main() -> None:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")  # huggingface.co 被墙,必走镜像
    from huggingface_hub import snapshot_download
    for repo, name, usage in MODELS:
        target = MODEL_DIR / name
        if _complete(target):
            print(f"[skip] {name} 已存在")
            continue
        print(f"[download] {repo} -> {target} ({usage})")
        snapshot_download(repo_id=repo, local_dir=str(target))
    print("全部模型下载完成:", MODEL_DIR)


if __name__ == "__main__":
    main()
