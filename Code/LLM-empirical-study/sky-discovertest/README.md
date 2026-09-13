本文件夹用于进行idea和implement转为相应的代码，并且进行完整测试。

使用的资源范围如下：

/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data/merged_llm_re_withsearch 这是LLM针对8篇论文生成的related works和solution，其中solution包括idea和implement两个部分。8篇论文对应的任务可以在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/pdf_mapping.jsonl中找到。

测试文件：/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS 这个文件夹是对应上述多个任务的测试文件夹。提供了原始的测试代码和数据。其也提供了原始被测试代码，在每个文件夹中的名字为：initial_program.py，只有can't be late 原始文件叫initial_greedy.py。其中每一个任务如何测试在各自的README文件中已经写明，包括注意事项。

你的任务是：

1. 读取LLM生成的8个文件的结果，按照映射关系找到对应的论文，获取LLM生成结果solution的部分和对应测试文件的initial_program.py。为了保证测试进行，你需要将solution实现为initial_program.py的形式（指各种接口完全和initial_program.py一致，保证正确测试，单内部算法使用solution提供的）。严格按照solution提出的算法进行实现，不可以自己改动，如果两者有冲突无法实现，放弃该任务并报告原因。

2. 对生成的每一个测试文件，都保存在本文件夹下的genration_program文件夹下（你需要自己创建），然后找到测试文件的README文件，学习其测试方法，对每一个代码文件进行测试，并且将结果保存在本文件夹下的output文件夹下（你需要自己创建）。

要求：你不能更改现有的测试代码，如果有错误，请报告并且跳过。

你不能访问，读取，修改我没有提供给你的其他文件以避免污染（环境，库，等基础通用文件除外）