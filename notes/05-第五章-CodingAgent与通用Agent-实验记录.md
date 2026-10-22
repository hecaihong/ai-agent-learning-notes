# 第五章：Coding Agent 与通用 Agent 实验记录

理论：[05-第五章-CodingAgent与通用Agent-理论笔记](<05-第五章-CodingAgent与通用Agent-理论笔记.md>)
项目：[code-for-logic](https://github.com/bojieli/ai-agent-book/tree/main/chapter5/code-for-logic)

## 实验一：用代码辅助逻辑推理

> 2026-10-22，助手真实运行，调用 DeepSeek API；本人复跑待完成。本次是小样本机制实验，不是官方 84 题完整复现。

### 要验证什么

让模型把“骑士说真话、无赖说假话”的条件写成约束代码，交给 Python 求解，再与不调用工具的直接推理比较。

### 实际过程

1. 补齐课程锁文件指定的 `python-constraint2==2.6.0`。
2. 运行离线 `solver`，检查内置 12 题的结构化条件和答案。
3. 用同一个 DeepSeek Flash，对 `kk08`～`kk11` 四题分别运行 `pure`、`code`。
4. 核对模型工具调用、Python 实际输出、结果回传和最终答案，原实验源码未修改。

### 首次报错与处理

原脚本的代码组首轮设置 `tool_choice="required"`，DeepSeek 默认思考模式返回 HTTP 400：`Thinking mode does not support this tool_choice`。请求未进入解题流程，不能算作逻辑答错。

核对[DeepSeek 官方接口说明](https://api-docs.deepseek.com/api/create-chat-completion/)后，在本次运行器里给两组所有请求统一加入：

```python
extra_body={"thinking": {"type": "disabled"}}
```

然后重新运行两组，首次失败记录保留，不与重跑结果混算。

### 这次学习的参数与功能

| 设置 | 本次含义 |
|---|---|
| `--mode solver` | 执行现成的结构化约束，不调用模型 |
| `--mode both` | 比较直接推理与代码辅助 |
| `--provider openai` | 使用 OpenAI 兼容客户端；实际端点是 `https://api.deepseek.com` |
| `--model deepseek-flash` | 两组使用相同模型 |
| `--min-people 4 --limit 4` | 筛选至少 4 人的题，再取前 4 题：`kk08`～`kk11` |
| `thinking=disabled`、`temperature=0` | 重跑时两组采用一致设置；直接推理组仍可用文字分析，只是不调用工具 |
| `tool_choice=required/auto` | 代码组第一次必须调用工具，后续由模型决定继续调用还是回答 |

程序最多运行 8 轮；本次代码组每题实际运行 2 轮：先请求执行代码，再根据结果回答。

### 核心代码与调用流程

`demo.py` 的 `call_model()` 负责循环，`sandbox.py` 的 `run_python()` 负责执行：

```text
题面 + 系统规则 + run_python 工具说明
→ 模型返回 tool_calls，参数中包含 Python 代码
→ Harness 执行 run_python(code)
→ stdout/stderr 作为 role=tool 消息回传
→ 模型生成最终答案
```

下面是本次模型为 `kk08` 实际生成的建模代码节选。`True` 表示骑士；每条约束都要把“说话者身份”和“他说的话是否为真”联系起来。

```python
from constraint import Problem
p = Problem()
for n in ['A','B','C','D']:
    p.addVariable(n, [True, False])
p.addConstraint(lambda a,b,d: a == (b == d), ['A','B','D'])
p.addConstraint(lambda b,c: b == (not c), ['B','C'])
p.addConstraint(lambda c,d: c == d, ['C','D'])
p.addConstraint(lambda d,b,c: d == (b != c), ['D','B','C'])
sols = p.getSolutions()
```

例如 B 说“C 是无赖”，应写成 `B == (not C)`；不能直接认定 C 是无赖，因为 B 也可能在说假话。

### 实际结果

离线基线：12/12 答对，每题都得到唯一解。它直接使用预写的结构化条件，没有验证模型翻译自然语言的能力。

重跑后的真实模型对照：

| 题号 | 人数 | 直接推理 | 代码辅助 | Python 实际执行 |
|---|---:|---|---|---:|
| kk08 | 4 | 正确 | 正确 | 1 次 |
| kk09 | 4 | 正确 | 正确 | 1 次 |
| kk10 | 4 | 正确 | 正确 | 1 次 |
| kk11 | 5 | 正确 | 正确 | 1 次 |
| 合计 | — | 4/4 | 4/4 | 4 次 |

共 12 次成功的模型请求：直接推理组 4 次、代码组 8 次，API 错误为 0。4 次执行均使用了 `python-constraint`，工具输出确实进入下一轮模型请求，并与最终答案、题目标准答案一致。

`kk11` 的真实 Python 输出摘录（文字记录，非截图）：

```text
1
{'B': 'knight', 'C': 'knave', 'D': 'knave', 'A': 'knight', 'E': 'knight'}
```

### 结果分析

- 本次验证了模型生成代码、程序实际执行、结果回传和模型作答的完整链路。
- 两组都答对，没有观察到代码辅助提升准确率；样本只有 4 题，不能推广为整体能力结论。
- 代码组的约束和执行结果可以检查，但求解器不会自动纠正错误的题意翻译。
- 接口兼容错误应单独处理，不能混进算法准确率；拿到 HTTP 200 后也仍要核对工具执行和答案。

### 实验结论

Coding Agent 的价值是能把任务转成可执行、可检查的程序；能执行和能答对是两道检查。本次验证了这一机制，尚未覆盖完整的读文件、改代码、测试失败再修复流程。
