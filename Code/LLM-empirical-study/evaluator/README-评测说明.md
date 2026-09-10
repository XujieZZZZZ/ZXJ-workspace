# RQ2 评估代码说明(评测方法、口径与局限)

本文档是对 `evaluation-guide.md` 的实现说明:模块划分、运行方式、口径决策与已知局限,
供评审与复现核对。原始任务书见本目录 `README.md`。

## 1. 运行方式

```bash
# 一键全流程(可 nohup 后台):RQ2-1 → RQ2-2 → RQ2-3
bash run_all.sh
# 常用参数:
bash run_all.sh --redo      # 强制重跑 LLM 裁判(默认断点续跑)
bash run_all.sh --limit 1   # 仅 1 个样本(冒烟/调试)
```
单步运行:`python run_rq2_1.py / run_rq2_2.py / run_rq2_3.py`(同参数)。
要求:含 torch/sentence-transformers 的 Python 环境(推荐 conda `ai4system`);
GPU 用于 SPECTER2 与 DeBERTa-NLI(模型已下载至 `model/`,可被 `model/download_models.py`
从 hf.mirror 重新下载)。**所有阶段均可中断,重跑同一命令即续传**(中间结果逐条落盘)。

## 2. 模块与文件

| 文件 | 职责 |
| :--- | :--- |
| config.py | 路径/API key/模型与全部阈值(唯一配置点,环境变量可覆盖) |
| dataio.py | 读 human_data 与 LLM_data/merged_* 四套样本;集合去重语义 |
| s2_client.py | Semantic Scholar 检索(match→search),429 指数退避,缓存续跑 |
| embedder.py / nli.py | 本地 SPECTER2 编码与 DeBERTa-NLI 蕴含概率(GPU) |
| top_venues.py(+data_refs/top_venues.json) | TVR 顶会名册(CCF-2022 A/B + 补遗)与匹配 |
| metrics_calc.py | 指南公式的数值实现(R/P/J、RR、W1、类内/类间/Rel、MLC、TVR) |
| rq2_1.py / run_rq2_1.py | RQ2-1:实体解析→三级匹配→指标→Claim 三件套 |
| rq2_2.py / run_rq2_2.py | RQ2-2:Rubric 四维+加权、语义相似、AspectRecall |
| rq2_3.py / run_rq2_3.py | RQ2-3:双盲成对判定、WinRate/Δ、Spearman 归因 |
| judge.py | LLM-as-Judge 后端(默认 Qwen)+ 全部裁判 prompt/校验 |
| report.py | Markdown/控制台输出渲染 |
| outputs/ | 中间缓存(cache/)、逐条裁判结果(judge/)、最终报告(reports/) |

## 3. 对照指南的实现口径(evaluation-guide.md)

- **数据对应**:RQ2-1 的 S_H/C_H 取 `human_data`;S_L/C_L 分别取
  `merged_llm_re_withsearch`(带检索)与 `merged_llm_re_withoutsearch`(不带检索),
  **两条链路各自成卷**(README 要求分别测评)。RQ2-2 输入=Observation+Human RW 的
  solution(`merged_human_re`),GT=`human_data` 的人类 solution。RQ2-3 的
  Sol_LLM_RW 与 Sol_Human_RW 即前两条链路各自的 solution。
- **S2 唯一标识**:对全部去重后论文标题做 match→search 两段检索,保存
  s2Id/DOI/year/venue/citationCount/authors/abstract(缓存可续跑)。**检索失败率**
  按样本分侧统计并出现在报告中——检索不到的论文按指南视为编造/失败,仅供质量参考。
- **三级匹配**:① DOI/S2ID 精确(两侧均解析成功才可能);② JaroWinkler(原始标题)≥0.90
  且年份差≤1(年份取人类元数据,LLM 缺省年份用 S2 规范年份;两侧年份都必须可知);
  ③ SPECTER2 余弦≥0.92。匹配矩阵 M 与命中清单逐样本保留。
- **v_p 向量**:S2 API 不对外提供 SPECTER 向量,按 README 指示下载 allenai/specter2_base
  至本地 `model/`,在 GPU 上计算(格式:已解析论文用 规范标题+摘要,否则用 引用时的标题)。
- **时间分布**:RR 以当年(=2026)起 3 年为窗口;W1 为年份经验 CDF 差的精确积分
  (样本量不等亦成立),**仅对年份可知的论文计算**,样本内缺失论文数在报告中注明。
- **质量指标**:MLC=mean ln(1+引用);TVR 用内置名册(见 4);两者只对 S2 解析成功的论文
  计算并在报告注明有效数——避免给"编造论文"臆造引用/venue 的虚假惩罚或奖励。
- **Claim 三件套**:忠实度 premise=引文摘要、hypothesis=所在段落 claim(缺摘要跳过,
  报告分母);覆盖率=LLM 把该样本全部人类 claims 拆成原子断言→判定 LLM claims 文本
  对每个原子的支持占比;G-Eval 按 Obs→C_L 的 CoT 打 1–5 分。
- **RQ2-2**:四维 Rubric 按指南表(1–5 整数),裁判可见 Observation+输入 RW+Sol;
  加权总分均权 w=0.25(config 可调);语义相似度用 SPECTER2 对 Sol 全文(idea+implementation)
  编码(指南所举 SciNBERT 属"学术文本编码器"示例,本实现用同款学术编码模型口径统一);
  AspectRecall=人类 Sol 抽取 K 个关键技术要素→判定 LLM Sol 是否落地,覆盖 K。
- **RQ2-3**:每样本成对判定两轮(候选顺序对调),输出偏好+两侧四维分;两轮偏好一致
  方为有效,冲突记 Tie;Δ_k 取两轮两侧分数均值之差;胜率分母为全部样本。
  归因:三个假设(Recall→Δ_grd、Rel→Δ_tgt、幻觉率=1−P→Δ_feas,并附 1/P 变体可查)
  做 Spearman(报告 ρ、p、n;N=8 小样本仅作趋势参考)。
- **RQ2-3 新增(默认开启)**:
  * 3.1d 交叉裁判胜率稳定性:同一批双盲成对任务用第二个后端(默认 **DeepSeek
    deepseek-v4-flash**)再评一轮,报告两裁判的 WinRate 与逐样本一致率;
  * 3.1e identical-pair 控制实验:把同一方案放在 A/B 两侧提交裁判,理想输出全部
    Tie——用于暴露位置偏置/判定噪声(两裁判均 100% Tie,见报告)。
  关闭开关:`--no-cross` / `--no-sanity`;主裁判与交叉裁判可通过
  `--backend qwen|deepseek` 与 `--cross-backend` 互换。
  缓存按 (任务,后端) 分文件存放:同一后端 key 相同,不同后端互不覆盖;
  裁判失败(ok=False)的缓存条目不参与续跑,下次运行自动清理重试——重复执行同一
  命令即"只补缺失、不重跑已有"。
- **RQ2-2 人类 Solution 基线(默认开启)**:2.1b 以同上下文同量表 rubric 对 Sol_H
  (人类 solution)打分,2.1c 给出 LLM-Sol 与人类基线的逐维与总分差,用于校准
  LLM 方案的绝对水平(实测 LLM 4.25 vs 人类 4.59,Δ=−0.34)。
- **一致性**:S2/嵌入/裁判三处缓存均落盘;同一样本重跑不重复计费(除非 --redo)。

## 4. 已知决策与局限(评审请注意)

1. **LLM 后端与 README 的差异**:README 要求 `from zai import ZhipuAiClient`(GLM),
   该包(公共 PyPI 上为无关占位包)与本机可用 key 均无法接入(2026-09 实测对
   bigmodel.cn / api.z.ai 均 401)。经确认改用具 OpenAI 兼容接入的**阿里云 DashScope
   Qwen**(模型 id 实测为 `qwen3-max`,即任务书所称"Qwen3.8max"的对应模型)。
   config.py 保留 `LLM_BACKEND=glm` 的 zai 适配位,将来 GLM 可用时改 config 即可,
   无需改动评测逻辑。
2. **TVR 名册**:源为 CCF-2022 更名版官方 PDF(会议+期刊 A/B)解析 + 公开整理清单补遗
   (github.com/LiXin97/CCF2022List;cnblogs.com/xyz/p/17115088)。解析/排版或有个别出入,
   规则宁缺毋滥(未命中计非顶会),全部**未命中的 venue 原串**在 RQ2-1 中间结果中保留
   可供人工核查;Human/LLM 两侧使用同一名册,指标对比不受漏网影响。
3. **年份/venue/引用缺失**:LLM 生成的 works 自带元数据仅 title+第一作者,年份等一律
   以 S2 解析为准;解析失败则相关指标按"不可知"处理并在报告中标注有效数(不臆造)。
4. **NLI 忠实度仅覆盖含摘要且解析成功的引文**(分母随文注明),摘要缺失是 S2 数据侧
   客观缺失。
5. **成对盲评的裁判上下文**不含输入 RW(避免泄露身份破坏双盲);RW 上下文版本的
   独立 Rubric 分(3.1c)提供交叉验证。
6. 裁判温度固定 0.2、结果做 JSON schema 校验(失败自动重试一次并落盘失败记录),
   复现时可直接使用 outputs/judge/ 下逐条原文。

## 5. 关键阈值/权重汇总(与指南一致;实验可改,改动请记录)

| 参数 | 值 | 位置 |
| :--- | :--- | :--- |
| Level-2 JaroWinkler 阈值 / 年份差 | 0.90 / ≤1 | config.py |
| Level-3 余弦阈值 | 0.92 | config.py |
| RR 时间窗(年) | 3 | config.py |
| Sol 加权总分权重 | 0.25×4(均权) | config.py `SOL_WEIGHTS` |
| S2 检索判定相似度下限 | 0.90 | config.py |
