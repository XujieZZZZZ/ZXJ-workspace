我现在有以下的任务，请你严格按照我的要求完成对应的任务。
任务一：结果可视化。
在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study中我已经运行了实验，并且获得了实验结果，其中含有LLM生成的相关工作内容（包括claims和works），我现在需要整体评估这些工作的时间分布和空间分布。还有claims和observation的表示分布。

具体如下，检查works现存的编码是不是利用其摘要等信息编码的，如果是则将human works的表示和LLM生成的works（with search）的表示放在一个空间内（二维空间或者三维都可，选择你认为最合适的），，每一个论文画一张图，然后再画一个八张论文的总体图，人类的用一个颜色的点，LLM用另一个颜色的点。

此外，统计claims的分布，具体和上述一样，将human-claim和LLM-claim放在一张图里，每个论文一张图，总共再画一张总图。

再画一下works的时间分布图，在一张图里画一下人类和LLM工作的时间分布（归一化，因为人类的works比LLM的多很多）

/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data
和
/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/evaluator/outputs
中


将结果放在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/evaluator/outputs中

请尽可能将图画的直观，清晰，好看。


任务二：方法测试。
在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data 中有根据论文提取出的人类Observation，related works（claims和works），solution。还有根据人类observation，LLM生成的related works和solution。（包含有search的和没有search的）我现在需要根据LLM生成的结果将其转为代码，然后进行测试。每一个json对应一个论文的结果。其测试内容在/home/zhangxujie/ai4research/skydiscover/benchmarks/ADRS中。使用evaluator进行测试。
原始测试是针对迭代优化代码，每迭代一次要进行一次评估然后保存一次结果。我现在不用迭代优化，只需要用一次完整测试，测试一次我的代码并给出结果（测试必须完整。
我希望的输入是/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/LLM_data/merged_llm_re_withsearch中的8个json文件（对应8个论文的结果）。
中间输出放在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data/initial-code中，分别代表8篇论文的执行代码（参考/home/zhangxujie/ai4research/skydiscover/benchmarks/ADRS中各个任务的初始代码文件，例如/home/zhangxujie/ai4research/skydiscover/benchmarks/ADRS/prism/initial_program.py，注意实现逻辑使用LLMjson文件中的idea和implement部分，但是整体接口保证和原始文件相同，确保可以正确测试。

结果放在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/output中（测评结果）

将/home/zhangxujie/ai4research/skydiscover/benchmarks/ADRS中必要的部分放置在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADR-evaluator中。整理测试代码，保证后续可以在有中间输出文件夹地址的时候，可以直接进行各个论文的代码测试。（你不能改变现有代码位置的实现，但复制过来的部分可以随意改动，确保实现正确，不要忘记复制测试要用到的数据集。