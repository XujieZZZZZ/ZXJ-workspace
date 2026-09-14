# 可视化结果说明(visual-test.md · 任务一)

本目录是 **"LLM 生成相关工作 vs 人类相关工作"的时间/空间分布可视化**的全部产物
(对应仓库根目录 `visual-test.md` 任务一)。**全部为新增文件,未改动任何既有结果与代码**;
可随时用下述命令重新生成(结果完全确定,随机种子固定为 42)。

> **2026-09-14 更新**:原来的图只画了 Human 与 LLM 两侧的点,"两者共有的部分"仅在坐标轴
> 说明里给一个数量、看不出是哪些点。本次在脚本(`visualize_related_works.py`)中加入
> **共有部分标注**(两边都有的论文直接画成**绿色方块 ■**),本目录全部图已按新代码
> 重新生成,详见第 3 节。

## 1. 编码复用核对结论(没有重复计算)

任务要求先检查 works 的“现存编码”是否基于摘要等信息。核对结论:

- **是。** works 的既有表示即评估管线(RQ2-1)的 SPECTER2 语义向量:编码输入文本为
  `embedder.paper_doc_text(标题, 摘要)` —— S2 解析成功时取 **Semantic Scholar 规范标题 + 摘要**,
  检索不到时仅用标题(与 `rq2_1.build_vectors` 逐字一致);向量按文本哈希缓存在
  `evaluator/outputs/cache/embeddings/`(默认编码器 specter2_base)。
- **复用命中率(逐条磁盘核对,非估算):**
  - 人类 works(8 篇汇总)**366/366** 命中既有缓存
  - LLM(with search)works **68/68** 命中既有缓存
  - Observation **8/8** 命中既有缓存
  - 即 works/obs 的全部向量**直接读取既有 .npy,零新增计算**。
- **claims 没有既有向量**(RQ2-1 对 claims 走 NLI/LLM 裁判,不产向量),本次按同一
  SPECTER2 口径补充编码共 280 条(人类 200 + LLM 80),结果落盘到同一个缓存目录
  `outputs/cache/embeddings/`(按文本哈希去重、只增不改),后续可直接复用。

> 运行环境说明:本机 zxj 环境 torch(cu130)缺少 V100(sm_70)kernel,无法执行 CUDA;
> 实际生成使用 `ai4system` 环境(已验证 GPU 正常)。脚本对设备无硬性要求,CPU 亦可。

## 2. 数据口径

| 来源 | 数据集 | 说明 |
| :-- | :-- | :-- |
| 人类(Human) | `data/human_data/<pdf_id>.json` | related_works 中的 claims 与 works(GT) |
| LLM(LLM with search) | `data/LLM_data/merged_llm_re_withsearch/<pdf_id>.json` | 给 LLM 输入 Observation、**允许检索**后生成的 claims 与 works |

- works:每篇论文文档内按规范化标题去重(集合语义,同 `dataio.unique_works`)。
- claims:段落内全部 claim 句子,不去重(保留数量语义,同 `dataio.all_claims`)。
- works 年份:人类取数据自带 `year`(288/288 完整);LLM 生成文件不带 year,取 **S2 解析缓存**
  (`outputs/cache/s2_resolution.jsonl`)中的规范年份,检索不到的 12 个 work 不进入年份统计(图中已注明)。
- 论文编号 ↔ pdf_id(总图图例顺序):
  1 Telemetry `52875bf8…` · 2 MAS `5dd2d839…` · 3 NS3 `7d3b6e61…` · 4 Can’t-Be-Late `b93fea40…`
  5 TXN `c252b8a9…` · 6 LLM-SQL `d18c13d0…` · 7 Cloudcast `e3d82baf…` · 8 Prism `f948850c…`

## 3. 两侧共有的论文(图上标注;2026-09-14 新增)

**问题**:原图只画 Human 与 LLM 两侧的点,"两者共有的部分"只在坐标轴说明里给出数量,
图上分不出是哪几个点。现在每一张空间图都把共有部分标出来。

**只认"两边都有同一篇"**:两侧 S2 解析到**同一 DOI 或同一 S2ID** 的才算共有;
标题相近、向量相似但并非同一篇的(评测 S_M 的 L2/L3 语义匹配)**一律不算共有,不标注**。

**怎么标**:两边都有的论文**直接画成一个绿色方块 ■**(一个方块 = 一篇论文),
其余点仍是圆点、颜色语义不变——
每论文图:蓝圆=Human、橙圆=LLM(with search);总图:圆点颜色=论文(8 色相),
实心=Human / 空心=LLM。即"圆点=只有一侧,绿方块=两边都有,不区分来源侧"。

**匹配实现**:直接调用评估管线的 `rq2_1.match_levels` 并只取 L1 判定(与
`run_rq2_1.py` 第 49 行同一条代码路径、同一份 SPECTER2 向量缓存),**零新增编码/检索**。

| 图 | 标注 | 数量(8 篇合计) |
| :-- | :-- | --: |
| 每论文 works 图 | 绿方块 = 该论文两边都引用的那几篇 | 16 篇 |
| works 总图 | 各岛上的绿方块 = 该论文两边都引用的那几篇 | 同上 16 篇 |
| 时间分布图 | **绿色描边台阶** = 这 16 篇的年份分布 | 16 篇 |

细节:

- 图例逐项给出计数:每论文图为 `Human, one side only (n=…)` / `LLM (with search), one side
  only (n=…)` / `both sides, same paper (n=…)`,总图另有每篇论文行 `H n / L n / both n`;
- 两边同篇时两侧向量完全相同(同篇→同向量→同坐标),脚本按 S2 实体合并成**一个方块**
  (取两侧实例中点,即原始坐标),所以图上"方块数 = 两边都有的论文数";
- claims 没有实体匹配口径,"共有"仅指两侧**逐字相同**的 claim(实测 0 条,图上以文字注明);
- 逐点判定可从 `data_points.jsonl` 的 `share`(1 = 两边都有同一篇,0 = 否)与
  `share_with`(对侧那篇同论文的标题)核对。

## 4. 文件清单

| 文件 | 内容 |
| :-- | :-- |
| `works_2d_<论文>.png` ×8 | 每篇论文的 works 语义空间:蓝点=人类、橙点=LLM(with search),金★=该论文 Observation 锚点;**绿方块=两边都引用的同一篇论文**(一个方块一篇) |
| `works_2d_overview.png` | 8 篇论文 works 总图(岛屿布局):每篇论文一个独立区域,**颜色=论文(8 色相,见图例),实心圆=Human,空心圆=LLM(with search),绿方块=两边都有**,黑★=Observation |
| `claims_2d_<论文>.png` ×8 | 每篇论文 claims 表示分布(人类 vs LLM),同空间 t-SNE,含义同上(claims 无实体匹配,绿方块只在逐字相同时出现,实测为 0) |
| `claims_2d_overview.png` | 8 篇论文 claims 总图(岛屿布局同上) |
| `works_time_distribution.png` | works 发表年份分布,**归一化**(人类 288 个 vs LLM 65 个 vs 共有 16 篇,数量悬殊,按各自总数折算比例):台阶直方图 + 中位虚线 + 统计框;绿色描边台阶=两边都引用的那 16 篇 |
| `data_points.jsonl` | 全部图中每个点(图名/来源/论文/文本/年份/**共有标注**/坐标)的溯源数据,可复绘 |
| `README.md` | 本说明 |

绘制方法:works/claims 均为 **SPECTER2(specter2_base)768 维向量 → t-SNE** 降至 2D
(metric=欧氏,L2 归一化后等价余弦;perplexity≈√n;相同向量只拟合一次、共享坐标);
坐标无绝对意义,只反映相对远近;图例在绘图区右侧,不与数据点重叠。

**总图读图方式与布局方法(vs 每论文图)**:每论文图沿用"蓝=人类/橙=LLM"便于同论文内对比;
总图采用**双层合成布局(岛屿图)**:每篇论文一个独立的"岛",岛心按 8 篇论文
Observation 向量的 PCA 排布(主题相近则相邻,过近的岛心经确定性排斥保证不重叠,
岛半径为固定值 0.20),岛内为该论文全部 Human+LLM 点各自独立的局部 t-SNE(保持岛内
真实邻近结构)。颜色=论文(8 个高区分度色相)、实心圆=Human、空心圆=LLM(with search),
黑★=Observation(在岛心)。

**为何不用"8 篇论文同一次全局 t-SNE"**:被引 works 的向量按"被引论文自身主题"
分布,而非按"引用它的论文"聚类——实测对 works 向量按论文分组的高维轮廓系数≈0
(353 个点),即使换任何 t-SNE 参数,每篇论文的点都会被均匀撕裂到两个大团中,
"同论文点分居两侧"是布局伪影而非数据或配色错误。因此总图改为岛屿布局,
保证**同一论文的点必在同一区域、颜色归属无歧义**(归属正确率 100%);
全局距离信息则由岛心的 Observation 相对排布近似表达。

## 5. 关键统计(与图内一致)

**works(每论文,文档内去重后)与 claims 计数:**

| 论文 | Human works | LLM works | 两侧同篇(图上绿方块) | Human claims | LLM claims | 两者逐字相同 claims |
| :-- | --: | --: | --: | --: | --: | --: |
| Telemetry | 16 | 12 | 1 | 14 | 11 | 0 |
| MAS | 56 | 12 | 2 | 33 | 10 | 0 |
| NS3 | 27 | 7 | 4 | 33 | 16 | 0 |
| Can’t-Be-Late | 25 | 4 | 0 | 15 | 7 | 0 |
| TXN | 80 | 9 | 1 | 28 | 8 | 0 |
| LLM-SQL | 18 | 7 | 2 | 12 | 10 | 0 |
| Cloudcast | 29 | 7 | 3 | 37 | 7 | 0 |
| Prism | 37 | 7 | 3 | 28 | 11 | 0 |
| **合计** | **288** | **65** | **16** | **200** | **80** | **0** |

("两侧同篇"= 双方 S2 解析到同一 DOI/S2ID,即图上**绿色方块**,合计 16 篇。
claims 无任何逐字相同句,LLM 不照抄人类句子。

⚠️ 与 RQ2-1 报告数字的对应关系(旧版 README 此处曾写错,已更正):RQ2-1 的 |S_M| 是
**三级**匹配结果(8 篇合计 40 个 LLM works;见 `outputs/reports/rq2_1_withsearch.md` 的
每样本 |S_M| 列,逐行为 3/11/6/1/4/4/5/6),其中只有 **16 篇**是本文意义上的"两边同一篇"
(DOI/S2ID 相同),另外 24 篇是 L2/L3 **语义近似**匹配——SPECTER2 base 在 0.92 余弦阈值下
会把同主题的不同论文判为匹配(实测:"Self-Refine" 与 "Toolformer" cos=0.939、
"Understanding Network Failures in Data Centers" 与 "Evolve or Die" cos=0.951),
故本图**不把它们算作共有**,只标 16 篇同篇论文。)

**works 发表年份(时间图):**

| 系列 | 有年份 works | 年份范围 | 中位年份 | 近 3 年占比(RR) |
| :-- | --: | :-- | --: | --: |
| Human | 288(全部) | 1955–2025 | 2018 | 28.8% |
| LLM (with search) | 53/65 | 1972–2024 | 2016 | 41.5% |
| 两侧共有(同篇 16 篇,按 S2 实体去重) | 16/16 | 2001–2024 | 2018 | 43.8% |
| 年份分布差异 W1(EMD) | | | **2.19 年**(人类侧年份缺失为 0,LLM 12 个 S2 未检索到未计入) | |

(共有部分的年份偏新:近 3 年占比 43.8%,高于人类整体 28.8%——两侧共同引用的是近年
热点论文,而人类独占的那部分里包含更多经典老论文。)

## 6. 复现

```bash
cd evaluator
# ai4system 环境(本机 GPU 可用);zxj 环境亦可但需 CPU 编码
/home/zhangxujie/miniconda3/envs/ai4system/bin/python3 visualize_related_works.py
```

依赖:python3.10+、numpy、matplotlib、scipy、scikit-learn,以及 evaluator 既有
`sentence-transformers/transformers`(仅首次补编码 claims 时加载模型,之后全走缓存)。
