本文件夹下是完成LLM生成相关工作部分和solution部分的测试实验结果。

以下是各个子文件夹的介绍：

human_data 文件夹是从论文中提取出的完整的Observation、related works（包含claims 和 works）、solution链路，分别属于8个论文，均带有唯一标识。

LLM_data 文件夹下有三个子文件夹：

/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data/merged_human_re  该文件夹包含Observation(与人类相同)、related works（包含claims 和 works，与人类相同）、solution （给LLM输入前面两个内容，生成的解决方案） 

/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data/merged_llm_re_withoutsearch      该文件夹包含 Observation(与人类相同)、related works（包含claims 和 works，这部分内容是给LLM输入observation，让模型生成的，不允许模型进行检索）、solution （给LLM输入前面两个内容，生成的解决方案）

/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data/merged_llm_re_withsearch         该文件夹包含 Observation(与人类相同)、related works（包含claims 和 works，这部分内容是给LLM输入observation，让模型生成的，要求模型进行检索）、solution （给LLM输入前面两个内容，生成的解决方案）

oringe_data是原始生成的数据结果，在此处作为数据溯源的根据，无需在实际应用中考虑。