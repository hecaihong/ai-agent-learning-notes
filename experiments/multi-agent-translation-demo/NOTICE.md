# 来源与发布说明

代码沿用 Apache License 2.0，完整条款见 [LICENSE](LICENSE)。

`third_party/ai-agent-book/` 来自 [bojieli/ai-agent-book](https://github.com/bojieli/ai-agent-book) 的 `chapter10/book-translation`。保留原作者 Bojie Li 的版权和许可证。该副本包含实验用的教材角色代码，不代表发布上游的最新版本。

本项目在教材基础上新增真实材料输入、逐次证据记录、候选术语筛选、双语审校、可执行调度、精确修订、质量门禁及 Translation 的逐段约束。发布版另作以下修改：课程依赖改成包内相对路径；密钥改从进程环境或项目本地 `.env` 读取；源 PDF 核验改为显式可选项；测试缓存目录改为可配置的临时目录。私有工作区中的原始实验文件未修改。

历史运行记录是脱敏副本。个人目录、密钥所在路径和可能出现的凭据均作替换，因此不得拿发布副本的字节哈希冒充原始回答哈希。`PUBLICATION_MANIFEST.json` 保留原始文件哈希及发布后哈希；历史记录中的模型、usage、错误和评审结论不据此改分。

实验文本摘自 AFDP 3-0.1《Command and Control》第二章，原 PDF 的 SHA-256、页码和文本清理记录见数据清单。原 PDF 不在此包中；代码许可不改变第三方资料的使用条件。译文和助手评估属于实验材料，仍需人工核对。
