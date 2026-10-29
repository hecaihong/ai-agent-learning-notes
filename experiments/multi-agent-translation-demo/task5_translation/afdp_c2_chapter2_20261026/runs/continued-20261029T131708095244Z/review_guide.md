# 每个 Agent 的输出与复核入口

格式检查通过不等于内容正确；所有人工质量判断目前为待复核。

| 调用 | 角色/阶段 | 原始输出 | 输入 | 调用信息 |
|---|---|---|---|---|
| 1 | Glossary / extraction | [查看](agents/001_glossary_extraction/output.txt) | [查看](agents/001_glossary_extraction/request.json) | [查看](agents/001_glossary_extraction/receipt.json) |
| 2 | Translation / draft | [查看](agents/002_translation_draft_01/output.txt) | [查看](agents/002_translation_draft_01/request.json) | [查看](agents/002_translation_draft_01/receipt.json) |
| 3 | Translation / draft | [查看](agents/003_translation_draft_02/output.txt) | [查看](agents/003_translation_draft_02/request.json) | [查看](agents/003_translation_draft_02/receipt.json) |
| 4 | Translation / draft | [查看](agents/004_translation_draft_03/output.txt) | [查看](agents/004_translation_draft_03/request.json) | [查看](agents/004_translation_draft_03/receipt.json) |
| 5 | Translation / draft | [查看](agents/005_translation_draft_04/output.txt) | [查看](agents/005_translation_draft_04/request.json) | [查看](agents/005_translation_draft_04/receipt.json) |
| 6 | Proofreading / initial_review | [查看](agents/006_proofreading_initial_review/output.txt) | [查看](agents/006_proofreading_initial_review/request.json) | [查看](agents/006_proofreading_initial_review/receipt.json) |
| 7 | Manager / decision | [查看](agents/007_manager_decision/output.txt) | [查看](agents/007_manager_decision/request.json) | [查看](agents/007_manager_decision/receipt.json) |
| 8 | Glossary / refinement | [查看](agents/008_glossary_refinement/output.txt) | [查看](agents/008_glossary_refinement/request.json) | [查看](agents/008_glossary_refinement/receipt.json) |

## Glossary
- [ ] 候选特征是否足以支持收录？
- [ ] Agent 是否排除了普通词和候选噪声？
- [ ] 译法是否符合本章语境？
- [ ] 是否遗漏低频但关键的概念或缩写？

## Translation
- [ ] 是否漏译、增译或改变原文含义？
- [ ] 数字、否定和条件是否保留？
- [ ] 术语是否统一，中文是否自然？

## Proofreading
- [ ] 是否逐项对照英文和当前译文？
- [ ] 确认缺陷是否有有效的双语引文？
- [ ] 旧问题是否修复，是否出现新增错误？

## Manager
- [ ] 修订对象是否对应审校意见？
- [ ] 修订理由是否有报告依据？
- [ ] 是否忽略问题或要求无依据的重译？

修订稿需要另行对照原文复核；原版审校角色检查的是初稿译文，不是原文忠实性或修订后的验收。
