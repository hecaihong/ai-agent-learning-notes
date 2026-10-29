# 第二章真实材料翻译实验

> 本页是脱敏后的历史说明。当前发布版的相对路径、密钥配置、可选 PDF 核验和运行命令以[项目首页](../README.md)为准；下方旧命令保留实验过程，不作为当前启动方式。

本次使用用户选定的 AFDP 3-0.1《Command and Control》文本镜像转换版第二章。完整原文已分为四块，来源页码、清理记录与文件哈希保存在 `afdp_c2_chapter2_20261026/source_manifest.json`。

## 2026-10-29 改进版（真实质量复测待完成）

`run_afdp_quality.py` 是改进版入口；本页后续保留旧版 `run_afdp_chapter2.py` 的说明和历史边界。改进版默认仅做输入检查，传入 `--run` 才真实调用 DeepSeek。旧运行目录不覆盖。

- 候选补充低频独立缩写，排除部分缺少领域名词词尾的高频片段。候选仍需语义筛选，不宣称已解决全部误收漏收。
- Glossary 结合全文语境筛选，要求区分 command/control、排除重复概念，无法确认的译法保留待领域审核状态。
- 审校同时读取英文原文和当前中文，确认缺陷必须有可定位的双语引文；定位无效会显式失败。
- Manager 返回明确的 `repair_glossary` 动作；请求术语返修时实际生成 `glossary_v2.json` 并重查所有受影响译块。
- 修订读取旧稿，只输出精确匹配且不重叠的 JSON 补丁。旧稿与每份补丁单独保存。
- 修订后再做一次双语审校，并检查脚注定义、待审标记和修订新增的小写英文。后者是需要确认的阻断线索，不自动等同误译。
- 有未解决缺陷时质量状态为 `blocked_by_quality_checks`，仅生成 `chapter2_candidate_zh.md`。通过自动检查时仍是 `automatic_checks_passed_pending_human_review`。

预算最多 13 次模型请求：1 次术语筛选、4 次初译、1 次初审、1 次调度、最多 1 次术语返修、最多 4 次补丁修订和 1 次终审。失败不自动重试，达到预算停止。离线测试使用服务替身，只证明调用、校验和拦截行为，真实质量提升必须另看新旧模型输出。

### Translation 专项改造：真实复测待运行

`translation_agent.py` 负责翻译前后的约束，模型仍为原来的 `deepseek-flash`，请求预算不增加。

- 翻译前：按已核对边界拆出两处侧栏和四条脚注，接回被打断的正文。原始文件保留；每块的来源哈希、重排依据和全部编号段写入 `translation_plan_01.json` 等文件。程序核对非空白字符保全；这不等同于自动认证阅读顺序正确。
- 翻译时：只提供本块相关术语的译法、概念释义和待审核状态，移除频次、位置等筛选记录。要求每个编号返回一个译段，疑点独立报告。
- 返回后：检查编号缺失、重复、空段，拦截已知普通英文残留，并核对部分阿拉伯数字及任务数、架次、吨数、人数。检查失败保留原始回答并停止，不自动替换、不自动重试。
- 返修时：补丁必须位于一个译段内，修改后执行同一套检查，防止把正确数字和单位改坏。逐段初稿、返修稿保存在 `translation_alignment_01_draft.json`、`translation_alignment_01_revision.json` 等文件中。
- 疑点：`translation_uncertainties.json` 中未解决的疑点会阻断交付；补丁不会自行清除这些记录，须进一步核实。

编号齐全只能证明结构覆盖，段内漏译、逻辑关系误译和中文表达质量仍须英中对照评估。下一轮沿用已冻结的 32 项准确性检查和表达评分标准，分别比较旧初稿、旧终稿、新初稿、新终稿，不把局部抽查分数称为全文准确率。旧版缓存与新请求不一致时禁止复用，须新建实验运行。

## 为什么做这个实验

观察同一个模型在不同职责、输入范围与输出要求下，能否完成术语提取、逐块翻译、审校和修订决策。重点是能查看每个角色收到什么、实际返回什么，再对照原文判断质量，而不是只观察程序是否结束。

## 启动方式

配置与输入检查，不调用模型：

```powershell
& '<PRIVATE_COURSE>\.venv\Scripts\python.exe' -X utf8 'task5_translation\run_afdp_chapter2.py'
```

真实运行，产生 DeepSeek API 费用：

```powershell
& '<PRIVATE_COURSE>\.venv\Scripts\python.exe' -X utf8 'task5_translation\run_afdp_chapter2.py' --run
```

使用原课程本地配置中的 DeepSeek 密钥，不在代码中填写密钥。每轮采用新输出目录，终端会打印具体位置。

运行配置是 `deepseek-flash`、关闭 thinking、单次输出最多 8192 token、单次请求超时 120 秒、全轮最多 11 次请求。失败会停止，不自动重试或重新运行整轮。调用次数上限不是金额上限，费用按服务返回的实际用量结算。

## 怎样获取每个 Agent 的数据

先打开本轮目录里的 `review_guide.md`，按调用顺序进入每个角色的记录。

```text
runs/run-时间/
  inputs/                         本轮原文快照
  source_manifest.json            原文来源与分块依据
  agents/
    001_glossary_extraction/
      request.json                实际发送的任务、资料和生成参数
      response.json               模型服务原始响应正文
      output.txt                  模型原始回答文字
      parsed.json                 JSON 角色的解析结果
      receipt.json                角色、阶段、响应 ID、usage、耗时和格式检查状态
    002_translation_draft_01/     第一块初译；其余调用同样单独保存
    ...
  term_candidates.json            Python 按频次、章节分布和结构信号生成的高召回候选
  glossary.json                   传给翻译角色的术语列表
  proofreading_report.json        审校 Agent 对初稿的报告
  manager_decision.json           Manager 的原始决策
  translations/
    draft/                        四块初稿
    revision/                     实际要求修订的块
    final/                        本轮最终版本
  chapter2_zh.md                  四块译文的有序汇总
  bilingual/                     每块原文与最终译文的对照文件
  quality_checks.json            自动检查线索，不是语义质量评分
  agent_calls.json                调用索引
  review_guide.md                 每个角色的原始输出、输入和复核问题
  run_manifest.json               源码哈希、运行状态和人工质量状态
```

`parsed.json` 只用于 JSON 输出角色。网络连接失败、尚未收到响应时，不会有 `response.json` 或 `output.txt`；服务已返回 HTTP 错误时，会在 `error_response.json` 保存状态码、请求 ID 和错误正文（如正文包含密钥则脱敏），不保存响应 Cookie 或认证头。失败发生在解析、字段验证或截断检查时，已经收到的响应与原始回答仍然保留。手动中断会把调用状态标为 `interrupted`。不要把文件不存在误认为该角色返回了空报告。

## 每个角色怎样分析

| 角色 | 要对照的输入 | 重点判断 | 应保留的结论 |
|---|---|---|---|
| Glossary | `term_candidates.json` 中的候选、频次、章节分布、结构信号和原文依据 | 候选特征是否支持收录；是否排除普通词和噪声；译法是否符合语境；是否漏掉低频关键概念 | 候选编号、具体术语、原文依据、接受或修改建议 |
| Translation | 本块原文、术语表、翻译指南、修订意见 | 漏译、增译、数字、否定、限定条件、术语和中文表达 | 原文片段、对应译文、问题及理由 |
| Proofreading | 全部初稿译文、术语表 | 问题是否真实且可定位；建议是否可执行；是否漏掉人工发现的问题 | 正确发现、误报、漏报分别记录 |
| Manager | 任务、文件索引、审校报告 | 修订对象是否合理；理由是否有依据；是否要求无必要的重译 | 决策、依据及人工判断 |

我们会先查看一个角色的 `output.txt`，再回看它的 `request.json`，判断它是否完成了收到的任务。响应 ID、usage 和格式检查只证明调用及输出结构，不能证明翻译正确。

## 实现与边界

- `terminology_candidates.py` 在本地按出现次数、章节分布、标题、定义句、缩写、正式框架和概念对等特征生成高召回候选，不调用模型。候选中允许存在噪声，不能直接视为正式术语。
- `run_afdp_chapter2.py` 复用教材的翻译、审校和 Manager 角色函数，独立组织本次第二章流程；Glossary 角色只对带证据的候选做术语性判断。
- `translation_evidence.py` 明确替换教材的 `llm_chat()`，负责模型收发、严格格式检查和逐次证据保存。
- 不调用教材的 `run_orchestration()`，所以不会强行加入 `token→词元` 等计算机术语。本轮术语来自术语 Agent 的提取，不代表官方标准译名。
- Glossary 角色不设置正式术语数量上限，数量由概念及证据决定。频次只是候选特征之一；显式定义、标题、缩写、概念对和跨章节分布也是特征。Agent 只返回候选编号、译法、类别、简短定义和采用的特征，Python 再合并原文依据，避免模型重复抄写证据耗尽输出 token。模型仍受单次输出 token 上限约束。
- 每个翻译调用重新构造上下文。术语表和译文主要通过 Python 参数传递，文件负责保存和供人复核。
- 审校角色只有译文和术语表，不能据此验证原文忠实性；最终必须对照原文判断。
- 每块最多修订一次，修订方式是附意见重新翻译原文。修订后不再自动调用审校模型，最终状态始终是待人工复核。
- 数字未按原样出现、指定译法未命中等，仅列为待核查线索。中文数字或合理译法变体可能触发线索，不能直接认定为错误。
- 源 PDF 是文本镜像，原文存在断行与拆开的单词，且没有内嵌图片。本轮不恢复原版图表，也不把这些源材料问题记成模型翻译错误。

## 本地验证

```powershell
& '<PRIVATE_COURSE>\.venv\Scripts\python.exe' -B -X utf8 -m unittest discover -s 'task5_translation' -v
```

这些检查使用模拟的模型服务响应，验证保存、错误处理、初稿/修订稿分离和 Manager 输入边界，不代表实际翻译效果。旧的 `run_translation.py` 仍是教材四章样例入口，本次真实材料使用 `run_afdp_chapter2.py`。
