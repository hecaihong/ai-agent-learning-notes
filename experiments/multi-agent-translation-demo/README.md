# 多 Agent 长文翻译与质量评估实验

基于 ai-agent-book 第十章，把教材短样例改为真实英文材料的翻译实验。每次模型调用都保留输入、原始回答、解析结果、usage 和错误，供逐 Agent 检查。

**当前状态：旧版完成过 11 次真实调用；改进版真实重跑在术语返修阶段失败，保留了失败记录。最新 Translation 专项改造完成本地回归，尚未真实复测。此项目作为可复现的学习案例发布，译文尚未通过语义验收。**

## 先看结果

- [各 Agent 改造前后的输出和质量](final_20261029/本轮重跑-质量对比结果.md)
- [32 项准确性逐句证据](final_20261029/accuracy_scorecard.md)
- [中文表达评分与理由](final_20261029/fluency_scorecard.md)
- [审校意见逐项核对](final_20261029/proofreading_scorecard.md)
- [全部角色的输出入口](final_20261029/agent_outputs_comparison.md)

32 项是预先固定的诊断抽查，由助手对照材料标注，不代表全文准确率。旧初稿 29/32、新初稿 30/32；中文表达均值分别为 2.94/5、3.25/5。旧修订稿为 27/32、3.50/5。没有新版修订稿或终审结果，不能据此声称完整流程质量提升。

## 架构与关键代码

技术为 Python、OpenAI 兼容 SDK（连接 DeepSeek）、JSON/Markdown 文件以及 unittest。角色间通过 Python 参数传递数据，同时把产物落盘；没有实现四个独立进程靠共享目录自行协作。

| 角色/模块 | 读取什么 | 生成什么 | 核心代码 |
|---|---|---|---|
| Glossary | 全章、候选及其特征 | 收录/排除决定、术语译法 | `task5_translation/run_afdp_chapter2.py` |
| Translation | 本块原文、相关术语、修订意见 | 编号译段、疑点或精确补丁 | `task5_translation/translation_agent.py` |
| Proofreading | 英文、当前译文、术语 | 带双语引文的问题 | `task5_translation/run_afdp_quality.py` |
| Manager | 审校摘要 | 返修块、是否返修术语库 | 同上 |
| Harness | 请求及角色输出 | 证据、格式检查、交付门禁 | `task5_translation/translation_evidence.py` |

最新 Translation 在输入端拆出已核对的侧栏和脚注，将正文整理为 85 个编号段；初译、返修均检查结构、部分英文残留和数字单位。程序检查无法代替含义及表达质量的评估。术语数量没有业务上限；13 次请求、8192 输出 token 是单轮资源边界。

## 本地运行

Python 3.10+。在此 README 所在目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -X utf8 task5_translation/run_afdp_quality.py
.venv\Scripts\python.exe -X utf8 -m unittest discover -s task5_translation -p "test_*.py"
```

默认入口只检查随包文本及哈希，不需要密钥、不调用模型。原 PDF 不打包，默认不会声称已重新核对 PDF；需要时另传 `--source-pdf "你自己的文件.pdf"`，哈希不符会停止。教材旧版入口是 `run_afdp_chapter2.py`；教材四章小样例入口是 `run_translation.py`。

tiktoken 相关测试和教材旧版在首次使用时可能下载分词表，不是模型请求。离线使用前应准备好分词缓存，并通过进程变量 `TIKTOKEN_CACHE_DIR` 指定其目录。

## 真实模型运行

将 `task5_translation/.env.example` 复制为同目录 `.env`，仅在本地填入 `DEEPSEEK_API_KEY`，或使用同名进程环境变量。然后执行：

```powershell
.venv\Scripts\python.exe -X utf8 task5_translation/run_afdp_quality.py --run
```

仅 `--run` 会开始此翻译工作流的收费模型调用。失败不自动重试；每次使用新目录，未解决缺陷只输出候选稿。历史续行器只处理指定旧故障，请求不同会拒绝缓存，不适用于把最新版提示词套在旧回答上。

新运行记录、`.env`、虚拟环境和缓存已被忽略；发布的 6 轮脱敏历史记录被明确保留。上传新记录前须重新脱敏，不能只依赖忽略规则。不要把真实密钥写进代码、命令截图或提交记录。

## 证据与许可证

完整四块原文、候选术语、各次请求/回答、初译/修订、错误、人工辅助标注与指标脚本均在包内。评估重算：`python -X utf8 final_20261029/build_quality_comparison.py`。脚本不调用模型，读取现存输出核对引文并计算分数。

[来源与发布改动](NOTICE.md) · [Apache-2.0](LICENSE) · [历史说明](task5_translation/HISTORY.md)。原始 PDF、私人配置、未脱敏截图和虚拟环境不打包。
