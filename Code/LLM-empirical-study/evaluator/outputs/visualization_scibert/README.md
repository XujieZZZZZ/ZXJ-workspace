# 可视化结果(SciBERT 编码批次 · visual-test.md 任务一)

本目录与 `../visualization/`(SPECTER2/specter2_base 批次)同属一个可视化任务,
**编码器为 SciBERT(`allenai/scibert_scivocab_uncased`,sentence-transformers mean
pooling + L2 归一化,与评测报告 `rq2_1_*_emb_scibert.*` 同一口径)**;
原有 SPECTER2 批次全部保留在 `../visualization/`,未做任何改动。

## 1. 编码复用核对(零重复计算)

- works 编码输入与评测管线逐字一致(`embedder.paper_doc_text`:标题 + S2 摘要,无摘要仅标题),
  向量按文本哈希缓存在 `outputs/cache/embeddings_scibert/`(评测期 `--emb scibert` 已生成):
  - 人类 works **366/366**、LLM(with search) works **68/68**、Observation **8/8**
    全部命中既有缓存,直接读盘;
- claims 无既有 SciBERT 向量,本次补编码 280 条(人类 200 + LLM 80,GPU),
  已落盘同一缓存目录,后续可直接复用。

## 2. 数据口径与图集

与 `../visualization/README.md` 完全一致(数据源、去重/年份口径、统计表、"两边都有"的
标注口径均相同),仅编码器不同:

| 文件 | 内容 |
| :-- | :-- |
| `works_2d_<论文>.png` ×8 | 每篇论文 works 语义空间:蓝点=Human、橙点=LLM(with search)、金★=Observation;**绿方块=两边都引用的同一篇论文**(一个方块一篇) |
| `works_2d_overview.png` | 8 篇论文 works 总图(岛屿布局):每篇论文一个独立区域,**颜色=论文(8 色相,见图例),实心圆=Human,空心圆=LLM(with search),绿方块=两边都有**,黑★=Observation |
| `claims_2d_<论文>.png` ×8 | 每篇论文 claims 表示分布(claims 无实体匹配,绿方块只在逐字相同时出现,实测为 0) |
| `claims_2d_overview.png` | 8 篇论文 claims 总图(岛屿布局同上) |
| `works_time_distribution.png` | works 年份分布(归一化;含"两边都有"的 16 篇;**与编码器无关,与 SPECTER2 批次同为同一文件内容**) |
| `data_points.jsonl` | 全部数据点(含 `emb: SciBERT` 字段、`share`/`share_with` 共有标注)与坐标,可复绘 |
| `README.md` | 本说明 |

> "两边都有"= 两侧 S2 解析到同一 DOI/S2ID(与编码器无关,两批次都是 16 篇);
> 评测 S_M 的语义近似匹配(L2/L3)**不算共有、图上不标**,原因见 `../visualization/README.md` 第 3 节。

绘制方法:每论文图为 **SciBERT 768 维向量 → t-SNE**;总图为**双层合成布局(岛屿图)**:
每篇论文一个独立的"岛",岛心按 8 篇论文 Observation 向量的 PCA 排布(主题相近则相邻,
过近岛心确定性排斥、岛半径固定 0.20),岛内为该论文全部 Human+LLM 点的局部 t-SNE
(保持岛内真实邻近结构);颜色=论文、实心圆=Human、空心圆=LLM(with search)、黑★=Observation。

**为何不用"8 篇论文同一次全局 t-SNE"**:works 向量按"被引论文自身主题"而非"引用它的
论文"分布——实测按论文分组的高维轮廓系数≈0,任何 t-SNE 参数都会把每篇论文的点均匀
撕裂到两个大团("同论文点分居两侧"是布局伪影而非数据/配色错误)。岛屿布局保证
**同一论文的点必在同一区域、归属无歧义(100%)**;全局距离由岛心的相对排布近似表达。

## 3. 与 SPECTER2 批次的客观对比(供参考)

对 8 篇论文的 Human works 表示做论文=类别的量化(平均类内/类间余弦):

| 编码器 | 类内平均 cos | 类间平均 cos | 备注 |
| :-- | --: | --: | :-- |
| SPECTER2 (specter2_base) | 0.856 | 0.945 | 评测默认口径 |
| **SciBERT** | **0.763** | **0.946** | 本批次 |

说明:两类编码的"论文间(主题)相似度"都较高;SciBERT 类内余弦更低
(点群内更"发散"),在 t-SNE 上通常表现为点群铺得更开、不同论文区域的边界更直观,
但整体聚类分离度差异请以两批图对照判断。若仍觉区分不够,可考虑:
① 调大 t-SNE perplexity 或换 UMAP(低维布局更稳);
② 降维前对向量做"去全局质心(mean-centering)"以凸显论文间差异方向。

## 4. 复现

```bash
cd evaluator
/home/zhangxujie/miniconda3/envs/ai4system/bin/python3 visualize_related_works.py --emb scibert
```

默认(不带参数)仍输出 SPECTER2 批次到 `outputs/visualization/`,互不覆盖。
