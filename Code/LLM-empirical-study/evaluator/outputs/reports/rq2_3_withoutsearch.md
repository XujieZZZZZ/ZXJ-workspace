# RQ2-3 评估报告:LLM-RW vs Human-RW 对 Solution 的影响(变体: withoutsearch)

- 样本数: 8;双盲成对判定:位置对调两次,冲突判 Tie
- 主裁判后端: qwen;交叉裁判(胜率稳定性): deepseek;
- identical-pair 控制实验默认开启(同方案 A==B,理想输出为 Tie)


## 3.1 成对双盲对比(位置对调;裁判=qwen)

| 样本 | O1 偏好 | O2 偏好 | 有效判定 | Sol_LLM 总分 | Sol_HumanRW 总分 | Δ total |
| --- | --- | --- | --- | --- | --- | --- |
| 52875bf8ef4b3f8c | A | B | Tie | 4.8750 | 3.8750 | 1.0000 |
| 5dd2d839c66d339a | A | B | Tie | 4.7500 | 3.7500 | 1.0000 |
| 7d3b6e61ea96cc4f | A | B | Tie | 4.6250 | 3.7500 | 0.8750 |
| b93fea400aedf898 | A | Tie | Tie | 4.5000 | 3.8750 | 0.6250 |
| c252b8a901feea74 | A | B | Tie | 4.2500 | 3.5000 | 0.7500 |
| d18c13d036b3708f | Tie | Tie | Tie | 4.7500 | 4.5000 | 0.2500 |
| e3d82bafe7cb11e7 | A | B | Tie | 4.3750 | 3.2500 | 1.1250 |
| f948850caef3d25f | A | B | Tie | 4.6250 | 3.5000 | 1.1250 |
| mean(全部样本) | - | - | - | 4.5938 | 3.7500 | 0.8438 |

**胜率统计**

| 指标 | 值 |
| --- | --- |
| WinRate_LLM_RW | 0.0% |
| WinRate_Human_RW | 0.0% |
| Tie 率 | 100.0% |
| 有效样本 N | 8 |

注:O1/O2 列为裁判输出的原始偏好标签(A/B/Tie);两轮任务中标签与内容绑定一致(A=Sol_LLM_RW、B=Sol_Human_RW),仅交换展示顺序(O1 先展示 Sol_LLM_RW、O2 先展示 Sol_Human_RW)。两轮偏好指向不同内容(即位置冲突)时,按指南有效判定为 Tie。

## 方案得分差值 Δ_i^k = Score_k(Sol_LLM_RW) - Score_k(Sol_Human_RW)(成对两轮均值;裁判=qwen)

| 样本 | targetedness | feasibility | novelty | groundedness | Δ total |
| --- | --- | --- | --- | --- | --- |
| 52875bf8ef4b3f8c | 1.0000 | 1.5000 | 0.5000 | 1.0000 | 1.0000 |
| 5dd2d839c66d339a | 1.0000 | 1.0000 | 0.5000 | 1.5000 | 1.0000 |
| 7d3b6e61ea96cc4f | 0.5000 | 1.0000 | 0.5000 | 1.5000 | 0.8750 |
| b93fea400aedf898 | 0.5000 | 0.5000 | 0.5000 | 1.0000 | 0.6250 |
| c252b8a901feea74 | 1.0000 | 1.0000 | 0.5000 | 0.5000 | 0.7500 |
| d18c13d036b3708f | 0.0000 | 0.5000 | 0.0000 | 0.5000 | 0.2500 |
| e3d82bafe7cb11e7 | 1.0000 | 1.5000 | 0.5000 | 1.5000 | 1.1250 |
| f948850caef3d25f | 1.0000 | 1.0000 | 1.0000 | 1.5000 | 1.1250 |
| mean(全部样本) | 0.7500 | 1.0000 | 0.5000 | 1.1250 | 0.8438 |

## 3.1d 交叉裁判胜率稳定性(主=qwen vs 交叉=deepseek,同一批双盲成对任务)

| 样本 | 判定(qwen) | 判定(deepseek) | 一致? |
| --- | --- | --- | --- |
| 52875bf8ef4b3f8c | Tie | Tie | 一致 |
| 5dd2d839c66d339a | Tie | Win_LLM | 分歧 |
| 7d3b6e61ea96cc4f | Tie | Tie | 一致 |
| b93fea400aedf898 | Tie | Tie | 一致 |
| c252b8a901feea74 | Tie | Tie | 一致 |
| d18c13d036b3708f | Tie | Tie | 一致 |
| e3d82bafe7cb11e7 | Tie | Tie | 一致 |
| f948850caef3d25f | Tie | Tie | 一致 |

**胜率对比**

| 指标 | qwen | deepseek |
| --- | --- | --- |
| WinRate_LLM_RW | 0.0% | 12.5% |
| WinRate_Human_RW | 0.0% | 0.0% |
| Tie 率 | 100.0% | 87.5% |
| 样本一致率 | - | 87.5% |

## 3.1e identical-pair 控制实验(同方案 A==B;理想输出应全部 Tie)

| 裁判 | Tie 率 | N | 非 Tie 样本 |
| --- | --- | --- | --- |
| qwen | 100.0% | 8 | (全部 Tie) |
| deepseek | 100.0% | 8 | (全部 Tie) |

解读:Tie 率高说明位置偏置/判定噪声小;若某裁判大量非 Tie,其成对胜率需谨慎解读。

## 3.1c 独立 Rubric 交叉验证(带 RW 上下文,非盲;裁判=qwen)

| 样本 | targetedness | feasibility | novelty | groundedness |
| --- | --- | --- | --- | --- |
| 52875bf8ef4b3f8c | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 5(Human) |
| 5dd2d839c66d339a | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 3(Human) |
| 7d3b6e61ea96cc4f | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 4(Human) |
| b93fea400aedf898 | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 5(Human) | 5(LLM) / 3(Human) |
| c252b8a901feea74 | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 5(Human) |
| d18c13d036b3708f | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 5(Human) |
| e3d82bafe7cb11e7 | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 5(Human) | 5(LLM) / 5(Human) |
| f948850caef3d25f | 5(LLM) / 5(Human) | 4(LLM) / 4(Human) | 4(LLM) / 4(Human) | 5(LLM) / 5(Human) |
| mean(全部样本) | 5.00(LLM) / 5.00(Human) | 4.00(LLM) / 4.00(Human) | 4.00(LLM) / 4.25(Human) | 5.00(LLM) / 4.38(Human) |

## 3.2 归因:Spearman 相关(N=样本数,小样本解释力有限,仅作趋势参考)

| 假设 | X -> Y | 预期 | ρ | p | n |
| --- | --- | --- | --- | --- | --- |
| 检索召回假说 | recall -> groundedness | 正相关(r_s>0):LLM 遗漏核心文献 -> Solution 失去继承性 | 0.3858 | 0.345 | 8 |
| 贴合度传导假说 | rel -> targetedness | 正相关(r_s>0):相关工作偏离主题 -> 方案针对性差 | -0.3574 | 0.385 | 8 |
| 幻觉/噪音干扰假说 | halluc -> feasibility | 负相关(r_s<0):幻觉文献误导 -> 方案不可行 | 0.1552 | 0.714 | 8 |

样本数: X=8, Δ=8