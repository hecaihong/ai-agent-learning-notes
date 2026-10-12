# ai-agent-book 共学笔记

AI Agent 学习笔记与真实实验记录。教材来源：[bojieli/ai-agent-book](https://github.com/bojieli/ai-agent-book)。

本仓库是 Obsidian 中本课程笔记的发布副本，整理时间为 2026 年 10 月 12 日。图片与内部链接已转换为 GitHub 可以阅读的 Markdown 格式。

## 笔记入口

- [第一章：我的学习笔记](<notes/01-第一章-我的学习笔记.md>)
- [实验 1-1：我的实验记录与待填写对照](<notes/02-实验1-1-我的实验记录.md>)
- [第一章教材](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter1.md)
- [第一章项目目录与推荐阅读顺序](https://github.com/bojieli/ai-agent-book/blob/main/chapter1/README.md)

## 已核对的学习进度

| 内容 | 状态与证据 |
| --- | --- |
| Agent、Model、Harness、上下文与工具的关系 | 已学习，见第一章笔记 |
| Python 独立环境与 DeepSeek API 配置 | 已准备，密钥仅保存在本地 |
| 原项目离线搜索演示 | 已观察，演示结果是预先编写的，见笔记截图 |
| 完整上下文下的单独计算例子 | 已实际运行，结果 4000，2 轮模型请求、1 次工具调用；见下方运行截图，这不是完整消融对照 |
| DeepSeek 独立搜索接口验证 | 已取得真实结果，见下方 JSON；未接入原版 WebSearchAgent |
| 原版 Kimi/Moonshot 真实搜索 | 尚未运行 |
| 实验 1-1 上下文消融对照 | 尚未完成，不能把单独计算或搜索成功记为完成 |

单独计算例子的原始 JSON 后来被另一道普通问答覆盖，因此这里不把它当作现存计算轨迹证据。该覆盖问题与每次运行使用独立文件名的经验一并保留。

## Task 0 环境运行截图

原 Context 项目使用 DeepSeek 完成 `(125 + 375) * 8` 的计算任务，终端记录 2 轮模型请求、1 次工具调用，最终答案为 4000。

![Context 基础工具调用运行结果](assets/task0-context-calculation.png)

独立 DeepSeek 搜索适配脚本的实际运行结果，作为 API 与联网搜索验证的补充；它不是原版 Kimi 搜索项目的运行结果。

![DeepSeek 搜索适配脚本运行结果](<assets/Pasted image 20261012103853.png>)

## 搜索接入验证

实验脚本：[deepseek_search_adapter.py](experiments/web-search-agent/deepseek_search_adapter.py)。这是本人实验时使用的独立 DeepSeek 搜索适配器的原始源码副本，未改动代码，也未接入原版 WebSearchAgent。脚本在原课程目录中读取相邻 `context/.env` 的本地密钥；本笔记仓库不包含该环境文件、API 密钥或虚拟环境。

任务：搜索 DeepSeek 官方目前支持哪些模型，并提供官方来源链接。

- [上限为 3 时的原始记录](evidence/deepseek-search-20261012-101755.json)：前三次返回搜索结果，第四次请求返回 max_uses_exceeded。模型文字已经返回，但适配脚本检查工具错误后停止展示。
- [上限为 5 时的原始记录](evidence/deepseek-search-20261012-103546.json)：实际进行了 4 次搜索，4 个结果块、40 条结果、37 个不同 URL，没有工具错误。

这些记录证明搜索工具返回了结果，不自动证明最终答案中的每一句都正确。已对照官方文档核查主要模型信息；仍需区分搜索摘要、网页原文与模型归纳。

## 本阶段学习心得

学习第一章后，我理解了 Agent 由模型、上下文和工具构成：模型负责推理和提出行动，Harness 负责组织上下文、执行工具及管理循环。我完成了本地环境配置、计算工具调用的小例子，并用 DeepSeek 独立适配脚本进行了真实联网搜索。检查轨迹后发现，搜索次数上限是程序预算，模型给出答案不等于任务正确完成，还需要核对工具结果和官方来源。下一步开展实验 1-1 的上下文对照，观察隐藏工具结果等条件对行为的影响。

## 共学 Task 0 要求与当前进度

依据本人于 2026 年 10 月 12 日提供的班级通知，Task 0 为“Agent 基础与环境准备”，北京时间 10 月 12 日 24:00 截止（即 10 月 13 日 00:00）。

- 学习 Chapter 1，理解 AI Agent 及 `Agent = LLM + Context + Tools`：已学习核心概念，见第一章笔记。
- 配置 Python、依赖和 LLM API：已配置并实际运行。
- 跑通 Chapter 1 基础实验：已跑通原 Context 项目的单次工具调用；完整实验 1-1 消融对照仍待完成，不能据此声明全部第一章实验完成。
- 打卡材料为环境运行截图与 100 字以上 Agent 理解/学习笔记：见本页截图和学习心得。
- 扩展项为分析一个熟悉 Agent 产品的 LLM、Context、Tools：尚未单独整理。

本仓库记录实际学习过程；打卡是否通过以课程组织方审核为准。

## 来源与记录说明

- 原教材与代码由上游项目提供，笔记中的教材截图用于记录学习内容；上游许可见 [ai-agent-book LICENSE](licenses/ai-agent-book-LICENSE)。
- JSON 为本人的实际调用记录，复制时保持原始内容，不记录 API 密钥或认证请求头。
- 实验 1-1 的汇率工具使用固定测试汇率，用于上下文实验。
- Obsidian 原笔记保留；本发布副本对已有进度描述作了核对，未完成事项明确标为待完成。
