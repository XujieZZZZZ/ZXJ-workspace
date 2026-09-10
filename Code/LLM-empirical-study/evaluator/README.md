本文件夹用于测试LLM生成相关工作和solution的能力，具体的测试方案为/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/evaluator/evaluation-guide.md

需要处理的数据放在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/data，其中数据的组织由该文件夹下的README文件说明。

需要完成的测评任务在/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/README.md路径中。

请你严格按照evaluation-guide.md的内容撰写测试代码，完成所有的测试，并以清晰明了的方式输出测试结果。
如果有需要使用编码模型，请从国内镜像站hf.mirror下载相应的模型参数保存在本地，进行测试。单开一个名为model的文件夹保存。

如果需要使用大模型，请使用GLM模型，其具体应用方式如下：

from zai import ZhipuAiClient

# 初始化客户端
client = ZhipuAiClient(api_key="YOUR_API_KEY")

# 创建聊天完成请求
response = client.chat.completions.create(
    model="glm-5.3",
    messages=[
        {
            "role": "system",
            "content": "您是一个有用的AI助手。"
        },
        {
            "role": "user",
            "content": "您好，请介绍一下自己。"
        }
    ],
    temperature=0.6
)

# 获取回复
print(response.choices[0].message.content)

其APIkey 如下：653c63813b434d8592e86ce3119b3a5a.OmXkZCphP0iQsGij

所有的works为了能够进行标准话，都要在semantic scholar上进行检索并且获得唯一的标识保存在本地，为后续测试做基础，semantic schorlar的api-key为s2k-47rvmMbF6pmi4CLwEfi75iZb9JTCLssKiZOIl8TS

测试时请注意，对于LLM带检索的和不带检索的结果，要分别进行测评，sollution也一样分别进行测评


生成评估代码要求如下：
1.模块化，函数话，清晰合理的安排各个部分，尽可能不要重新写代码，复用以后的共同可以使用的函数。但要保证所有的实现要符合evaluation-guide.md的要求，不能自己更改。你可以自己决定生成几个文件，如何组织。

2.附带简洁，明确的注释。

3.要保证代码风格的一致性。确保不会存在问题，中间结果都要保存。最终结果既要输出，也要保存为文件，便于检查。

4.合理安排最终输出和保存为文件的格式，使得其清晰美观。