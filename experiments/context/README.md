# Context 自定义工具学习副本

来源：bojieli/ai-agent-book 的 `chapter1/context`，上游基线 `dbc046eb896ac4e39aa19c7774c8bf49583b89a6`，本地源码快照日期 2026-10-14。保留上游 [LICENSE](../../licenses/ai-agent-book-LICENSE)。

## 本次改动

在 `agent.py` 增加 `summarize_revenue` 函数、工具 Schema 和 `_execute_tool()` 的执行映射；新增 `tests/test_revenue_tool.py`。保留原来的 PDF、换汇、计算和 Python 执行工具。该副本用于学习，其他脚本是课程运行配套源码，不代表本次全部重新实现。

根目录 `agentbook/` 是原课程共享的提供商配置模块，`config.py` 会引用它。`calc_sandbox.py`、`grounding.py` 等为本项目依赖模块。此处不包含 API 密钥、`.env` 或虚拟环境。

## 本地验证

在已安装依赖的 Python 环境中进入本目录执行：

```powershell
python -m unittest discover -s tests -p test_revenue_tool.py -v
```

本次使用原课程已有虚拟环境验证复制后的代码。3 个测试通过，覆盖工具暴露、映射执行、非法数值和溢出。没有调用模型 API。

## 用户执行真实模型验证

如在新环境中使用，按 `requirements.txt` 准备依赖，并在此目录自行配置本地 `.env` 中的 `DEEPSEEK_API_KEY`。环境文件已由仓库忽略规则排除，不要提交。

在本目录执行（模型名称应与实际可用接口一致）：

```powershell
python -X utf8 main.py --mode single --provider deepseek --model deepseek-flash --context-mode full --task "四个季度营收均为美元：Q1=2500000，Q2=2282608.70，Q3=2278481.01，Q4=2541806.02。请调用 summarize_revenue 计算总额和平均值，并根据工具结果回答。" --output "custom-revenue-result.json"
```

本次并未执行上述真实 API 命令。验证时检查实际 `tool_calls` 中是否出现 `summarize_revenue`、参数是否正确、工具输出和最终答案是否一致。仅答案正确不足以证明工具被调用。

## 与原实验记录的关系

`run_experiment_1_1.py` 是配套消融运行脚本；已保存的五组 evidence 是新增工具前的四工具版本产生的。当前增加了第五个工具，重新运行会改变工具集合，应作为新实验记录。旧 JSON 保持原始字节和校验文件，不重新生成或覆盖。

学习解释见 [工具注册与上下文补充](<../../notes/05-20261014-工具注册与上下文补充.md>)。
