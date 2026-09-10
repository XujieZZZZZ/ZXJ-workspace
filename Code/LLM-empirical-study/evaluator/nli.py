# -*- coding: utf-8 -*-
"""DeBERTa NLI 蕴含概率计算(对应 evaluation-guide.md 1.4.1 论文事实忠实度)。

Premise=论文摘要, Hypothesis=Claim;P(Entailment | premise, hypothesis) 取
cross-encoder/nli-deberta-v3-base 三分类(矛盾/中立/蕴含)softmax 中蕴含概率。
模型同样按 README 要求从 hf.mirror 下载到本地 model/ 文件夹,GPU 批量推理。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

import config
from utils import log


class NliScorer:
    """蕴含概率评分器(懒加载,GPU 优先;predict 返回蕴含概率向量)。"""

    def __init__(self, model_dir: Path = config.NLI_DIR, device: Optional[str] = None):
        self.model_dir = Path(model_dir)
        self.device = device
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import CrossEncoder
        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"模型不存在: {self.model_dir}。请先运行 "
                f"HF_ENDPOINT=https://hf-mirror.com python model/download_models.py")
        # cross-encoder 输出三分类 logits(顺序: contradiction / neutral / entailment)
        self._model = CrossEncoder(str(self.model_dir), device=self.device)
        log(f"NLI 模型已加载: {self.model_dir} (device={self._model.device})")
        return self._model

    def entail_prob(self, premise_hypothesis: List[Tuple[str, str]],
                    batch_size: int = 32) -> np.ndarray:
        """对 (premise, hypothesis) 序列批量返回蕴含概率 [0,1]^N。"""
        model = self._load()
        probs = []
        for i in range(0, len(premise_hypothesis), batch_size):
            batch = premise_hypothesis[i:i + batch_size]
            logits = model.predict(batch, batch_size=batch_size,
                                   show_progress_bar=False, convert_to_numpy=True)
            soft = np.exp(logits - logits.max(axis=1, keepdims=True))
            soft /= soft.sum(axis=1, keepdims=True)
            probs.append(soft[:, 2])  # 蕴含概率
        return np.concatenate(probs) if probs else np.zeros((0,), dtype=np.float64)


if __name__ == "__main__":  # 自检:同义对蕴含概率高,矛盾对低
    nli = NliScorer()
    pairs = [
        ("The SDN controller operates correctly but receives incorrect inputs.",
         "A software-defined network controller can fail because it receives incorrect inputs."),
        ("The SDN controller operates correctly.",
         "The controller is broken and computes wrong routes."),
        ("Router hardware and software bugs can corrupt telemetry.",
         "We propose a new database join algorithm."),
    ]
    print("entail probs:", [round(float(x), 4) for x in nli.entail_prob(pairs)])
    print("nli self-check OK")
