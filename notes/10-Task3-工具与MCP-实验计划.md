# Task3：工具与 MCP 实验计划

> 当前状态：待本人运行。本页不包含助手代跑结果或合成截图。

- [返回 Task3 理论笔记](09-Task3-工具与MCP-学习笔记.md)
- [execution-tools 项目说明](https://github.com/bojieli/ai-agent-book/blob/main/chapter4/execution-tools/README.md)

## 首个实验目的

使用 `execution-tools` 离线 demo 观察文件写入、语法校验、代码执行、Shell 校验、长输出截断与持久化，以及危险操作审批如何构成一个真实执行闭环。

## 核心流程

```text
cli.py 解析命令
  → cmd_demo() 创建临时工作区
  → FileTools 写文件并校验
  → ExecutionTools 调用 LanguageExecutor
  → 执行代码或 Shell 命令
  → 截断长输出并保存完整文件
  → 危险命令触发审批，离线时 fail-safe 拒绝
```

## 建议运行顺序

1. 运行 `execution-tools` 离线 demo，保留原始控制台日志和本人截图。
2. 阅读感知工具 MCP Server，定位 `tools/list`、`tools/call` 与结构化返回。
3. 做一个最小 MCP Client 验证：列出工具、调用一个只读工具、核对返回值。

## 离线 demo 观察表

| 步骤 | 观察点 | 本人结果 |
| ---: | --- | --- |
| 1 | 合法 Python 文件写入，语法校验通过 | 待记录 |
| 2 | 错误语法被 linter 拦截 | 待记录 |
| 3 | 样本数据写入临时工作区 | 待记录 |
| 4 | `code_interpreter` 执行词频统计 | 待记录 |
| 5 | `virtual_terminal` 校验数据 | 待记录 |
| 6 | 长输出被截断，完整内容另存 | 待记录 |
| 7 | 危险命令进入审批并按策略处理 | 待记录 |

## 证据标准

- 控制台完整日志；
- 本人实际运行截图；
- 临时工作区与真实输出文件；
- 长输出的完整落盘文件；
- 失败时保留原始错误，不使用合成图替代。

## 待回答的问题

1. 哪一步由模型或调用者决定，哪一步由 Harness 治理？
2. 语法错误、危险命令和长输出分别由哪段代码处理？
3. 控制台显示成功后，还需要检查哪些真实副作用？
