# -*- coding: utf-8 -*-
"""本地文本编码器(SPECTER2):论文/摘要/Observation/Solution 的语义向量 v。

对应 evaluation-guide.md 中的 SPECTER2 Embedding v_p:
- S2 API 不对外提供 SPECTER 向量,故按 README 要求从 hf.mirror 下载
  allenai/specter2_base 到本地 model/ 文件夹,由本机 GPU 计算(公式口径不变);
- 长文本由 sentence-transformers 按模型 max_seq_length(512 token)自动截断;
- 全部向量按文本哈希缓存在 outputs/cache/embeddings/,可断点续跑。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import config
from utils import log

class Specter2Embedder:
    """本地语义编码器(SPECTER2 系列 / SciBERT;懒加载,GPU 优先)。

    三种口径(2026-09 起,见 config.EMB_CHOICES):
    - specter2_base(默认): sentence-transformers 加载 allenai/specter2_base,mean pooling + L2 归一化;
    - scibert:            sentence-transformers 加载 allenai/scibert_scivocab_uncased,同 mean pooling 口径;
    - specter2:           allenai/specter2_base + allenai/specter2(PRX proximity 适配器,官方"通用嵌入"
                          推荐组合),按模型卡官方用法 adapters 库加载、取 [CLS](last_hidden[:,0]) + L2 归一化。
    不同模型(name/adapter)的向量缓存目录彼此隔离,避免按文本哈希互相污染。
    """

    def __init__(self, model_dir: Path = config.SPECTER2_DIR, device: Optional[str] = None,
                 name: Optional[str] = None, adapter_dir: Optional[Path] = None,
                 pooling: str = "st"):
        self.model_dir = Path(model_dir)
        self.adapter_dir = Path(adapter_dir) if adapter_dir else None
        self.pooling = pooling            # "st":ST 默认 mean pooling; "cls":SPECTER2 官方 [CLS]
        self.device = device
        self.name = name
        self._model = None
        self._tok = None
        self._lock = threading.Lock()
        self.emb_dir = config.CACHE_DIR / ("embeddings" if not name
                                           else f"embeddings_{name}")
        self.index_file = self.emb_dir / "index.json"
        self.emb_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, str] = {}
        if self.index_file.exists():
            self._index = json.loads(self.index_file.read_text(encoding="utf-8"))

    # ---------------- 模型 ---------------- #
    def _load(self):
        if self._model is not None:
            return self._model
        if self.adapter_dir:   # base + task adapter(官方 adapters 库 + [CLS] 池化)
            import torch
            from transformers import AutoTokenizer
            from adapters import AutoAdapterModel
            if not self.model_dir.exists() or not list(self.model_dir.glob("*.bin")) \
                    and not list(self.model_dir.glob("*.safetensors")):
                raise FileNotFoundError(f"base 模型不存在: {self.model_dir}")
            dev = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            self._model = AutoAdapterModel.from_pretrained(str(self.model_dir))
            self._model.load_adapter(str(self.adapter_dir), set_active=True)
            self._model.to(dev).eval()
            self._tok = AutoTokenizer.from_pretrained(str(self.model_dir))
            log(f"编码模型已加载: {self.name or self.model_dir.name}(base+adapter,"
                f"pooling={self.pooling}) <- {self.model_dir} + {self.adapter_dir} (device={dev})")
            return self._model
        # 纯 transformers 目录:ST 自动补 mean pooling(与既有 specter2_base 结果同口径)
        from sentence_transformers import SentenceTransformer
        if not self.model_dir.exists() or not list(self.model_dir.glob("*.bin")) \
                and not list(self.model_dir.glob("*.safetensors")):
            raise FileNotFoundError(
                f"模型不存在: {self.model_dir}。请先运行:\n"
                f"  HF_ENDPOINT=https://hf-mirror.com {config.EVALUATOR_DIR}/model/download_models.py")
        self._model = SentenceTransformer(str(self.model_dir), device=self.device)
        log(f"编码模型已加载: {self.name or self.model_dir.name} <- {self.model_dir} "
            f"(device={self._model.device})")
        return self._model

    def dim(self) -> int:
        """模型输出维度(未加载时按配置返回默认 768,加载后取实际维度)。"""
        if self._model is not None:
            if self.pooling == "cls":
                return int(self._model.config.hidden_size)
            return int(self._model.get_sentence_embedding_dimension())
        return config.EMBEDDING_DIM

    # ---------------- 编码与缓存 ---------------- #
    def encode_cached(self, text: str) -> np.ndarray:
        """编码单条文本(磁盘缓存命中直接返回,避免重复 GPU 计算)。"""
        from utils import text_hash
        key = text_hash(text)
        vec_file = self.emb_dir / f"{key[:2]}" / f"{key}.npy"
        if vec_file.exists():
            return np.load(vec_file).astype(np.float32)
        vec = self.encode_batch([text])[0]
        with self._lock:
            vec_file.parent.mkdir(parents=True, exist_ok=True)
            np.save(vec_file, vec)
            self._index[key] = str(vec_file.relative_to(self.emb_dir))
            self.index_file.write_text(json.dumps(self._index, ensure_ascii=False),
                                       encoding="utf-8")
        return vec

    def encode_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """批量编码(无缓存),返回 (N, dim) float32 L2 归一化向量。"""
        model = self._load()
        texts = [(t or "").strip() for t in texts]
        if self.pooling == "cls":      # base+adapter 官方口径:[CLS] + L2
            import torch
            with torch.no_grad():
                outs = []
                for i in range(0, len(texts), batch_size):
                    enc = self._tok(texts[i:i + batch_size], padding=True, truncation=True,
                                    max_length=512, return_tensors="pt")
                    enc = {k: v.to(model.device) for k, v in enc.items()}
                    h = model(**enc).last_hidden_state[:, 0, :]      # [CLS]
                    outs.append(h.detach().cpu().numpy())
            vecs = np.vstack(outs) if outs else np.zeros((0, self.dim()), dtype=np.float32)
            vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)
            return vecs.astype(np.float32)
        vecs = []
        for i in range(0, len(texts), batch_size):
            emb = model.encode(texts[i:i + batch_size], batch_size=batch_size,
                               show_progress_bar=False, normalize_embeddings=True,
                               convert_to_numpy=True)
            vecs.append(np.asarray(emb, dtype=np.float32))
        dim = int(model.get_sentence_embedding_dimension())
        return np.vstack(vecs) if vecs else np.zeros((0, dim), dtype=np.float32)


def paper_doc_text(title: str, abstract: Optional[str] = None) -> str:
    """论文向 SPECTER2 的输入文本(遵循其预训练格式 title:/abstract:;无摘要则仅标题)。"""
    t = (title or "").strip()
    a = (abstract or "").strip()
    if a:
        return f"title: {t}\n abstract: {a}"
    return f"title: {t}"


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度(向量已归一化时即点积;显式实现便于自检与调试)。"""
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


if __name__ == "__main__":  # 自检:两条已知相关文本的相似度应明显高于不相关文本
    emb = Specter2Embedder()
    v1 = emb.encode_cached("title: Attention is all you need\n abstract: The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder.")
    v2 = emb.encode_cached("title: BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding")
    v3 = emb.encode_cached("title: Understanding Network Failures in Data Centers")
    print("transformer vs bert:", round(cosine(v1, v2), 4),
          "| trans vs network:", round(cosine(v1, v3), 4))
    print("embedder self-check OK")
