"""汇总已保存输出及助手逐项标注；不调用模型、不改原始证据。"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / "task5_translation" / "afdp_c2_chapter2_20261026"
RUNS = DATASET / "runs"
OLD = RUNS / "run-20261026T153700605628Z"
NEW = RUNS / "continued-20261029T131708095244Z"
VERSIONS = {"old_draft": (OLD, "draft"), "old_final": (OLD, "final"), "new_draft": (NEW, "draft")}
LABELS = {"old_draft": "旧版初稿", "old_final": "旧版修订稿（参考）", "new_draft": "新版初稿"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def link(path, label="原始输出"):
    relative = Path(path).relative_to(HERE.parent).as_posix()
    return f"[{label}](../{relative})"


def main():
    checklist = read_json(HERE / "accuracy_checkpoints.json")["checks"]
    annotations = read_json(HERE / "accuracy_annotations.json")["rows"]
    fluency = read_json(HERE / "fluency_annotations.json")["rows"]
    proofreading = read_json(HERE / "proofreading_annotations.json")
    manifest = read_json(DATASET / "source_manifest.json")
    units = {Path(item["file"]).name[:2]: item for item in manifest["units"]}
    sources = {uid: (DATASET / item["file"]).read_text(encoding="utf-8").split("\n\n", 1)[1] for uid, item in units.items()}
    texts = {v: {uid: (run / "translations" / stage / (uid + ".md")).read_text(encoding="utf-8") for uid in units} for v, (run, stage) in VERSIONS.items()}
    assert len(checklist) == len(annotations) == 32
    by_id = {item["id"]: item for item in checklist}
    assert {item["id"] for item in annotations} == set(by_id)
    for row in annotations:
        check = by_id[row["id"]]
        assert check["source_anchor"] in re.sub(r"\s+", " ", sources[check["unit_id"]]), row["id"]
        for version in VERSIONS:
            assert row["scores"][version] in (0, 1)
            assert row["target_quotes"][version] in texts[version][check["unit_id"]], (row["id"], version)
    for row in fluency:
        assert len(row["scores"]) == len(row["explanations"]) == 4
        assert all(1 <= score <= 5 for score in row["scores"])
    old_calls, new_calls = read_json(OLD / "agent_calls.json"), read_json(NEW / "agent_calls.json")
    assert len(new_calls) == len({call["response_id"] for call in new_calls}) == 8
    assert sum(not call.get("reused_response", False) for call in new_calls) == 2
    assert not any(call["stage"] in {"revision", "final_review"} for call in new_calls)
    old_g, new_g = read_json(OLD / "glossary.json"), read_json(NEW / "glossary_v1.json")
    glossary_refinement = read_json(NEW / "agents/008_glossary_refinement/parsed.json")
    candidate_ids = {x["candidate_id"] for x in read_json(NEW / "term_candidates.json")}
    returned_ids = {x["candidate_id"] for key in ("glossary", "excluded") for x in glossary_refinement[key]}
    assert returned_ids - candidate_ids == {"T116"}
    critical = ["DIRLAUTH", "OPCON", "CCMD", "JFC", "MTO", "OE"]
    coverage = {"old": [x for x in critical if any(x.casefold() == g["en"].casefold() for g in old_g)], "new": [x for x in critical if any(x.casefold() == g["en"].casefold() for g in new_g)]}
    metrics = {"scope": "32项固定检查点，助手辅助单人评审，非全文准确率或专家验收", "accuracy": {}, "fluency": {}, "glossary": {"old_entries": len(old_g), "new_initial_entries": len(new_g), "critical_acronym_coverage": coverage, "invalid_refinement_ids": sorted(returned_ids - candidate_ids)}, "proofreading": {}, "runtime": {"old_calls": len(old_calls), "new_unique_calls": len(new_calls), "replayed_in_continuation": 6, "new_requests_in_continuation": 2, "old_total_tokens": sum(c["usage"]["total_tokens"] for c in old_calls), "new_total_tokens": sum(c["usage"]["total_tokens"] for c in new_calls), "new_workflow_status": read_json(NEW / "run_manifest.json")["workflow_status"], "new_revision_available": False, "new_final_review_available": False}}
    for version in VERSIONS:
        correct = sum(row["scores"][version] for row in annotations)
        metrics["accuracy"][version] = {"correct": correct, "total": 32, "percent": correct / 32 * 100, "failed_checkpoints": [row["id"] for row in annotations if not row["scores"][version]]}
        scores = [sum(row["scores"]) / 4 for row in fluency if row["variant"] == version]
        metrics["fluency"][version] = {"unit_means": scores, "mean": sum(scores) / len(scores), "scale": 5, "reviewer": "助手按预先固定量表评分"}
    for variant in ("old", "new"):
        report_path = OLD / "proofreading_report.json" if variant == "old" else NEW / "proofreading_report.json"
        report = read_json(report_path)
        rows = proofreading[variant]
        assert [r["issue_number"] for r in rows] == list(range(1, len(report["issues"]) + 1))
        counts = Counter(r["label"] for r in rows)
        denominator = counts["T"] + counts["N"] + counts["F"]
        metrics["proofreading"][variant] = {"counts": dict(counts), "adjudicated": denominator, "total": len(rows), "confirmed_ratio_among_adjudicated": counts["T"] / denominator}
    metrics["annotation_sha256"] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("accuracy_checkpoints.json", "accuracy_annotations.json", "fluency_annotations.json", "proofreading_annotations.json")}
    write_json(HERE / "comparison_metrics.json", metrics)

    accuracy_lines = ["# 32项准确性逐项评分", "", "同阶段主对照为旧初稿与新初稿。旧修订稿只作参考；新版修订稿未生成。0/1由助手对照原文标注，脚本只检查引用并做算术，不自动判断语义。", "", "| 编号 | 块 | 检查点 | 旧初稿 | 旧修订稿 | 新初稿 |", "|---|---|---|---:|---:|---:|"]
    for row in annotations:
        item = by_id[row["id"]]
        accuracy_lines.append("| " + " | ".join(map(cell, [row["id"], item["unit_id"], item["criterion"], *[row["scores"][v] for v in VERSIONS]])) + " |")
    for row in annotations:
        item = by_id[row["id"]]
        accuracy_lines += ["", "## " + row["id"] + "：" + item["criterion"], "", "原文定位：`" + item["source_anchor"] + "`。"]
        for version in VERSIONS:
            accuracy_lines += ["", f"{LABELS[version]}，{row['scores'][version]}分：", "", "> " + row["target_quotes"][version]]
        accuracy_lines += ["", row["note"]]
    (HERE / "accuracy_scorecard.md").write_text("\n".join(accuracy_lines) + "\n", encoding="utf-8")

    fluent_lines = ["# 中文表达四维评分", "", "四维依次为语法、搭配、连贯、用语；每维1至5分。均值是单次助手评审的算术汇总，不是客观自动测量或专家定论。量表见固定口径文件。", "", "| 版本 | 块 | 语法 | 搭配 | 连贯 | 用语 | 均值 |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in fluency:
        fluent_lines.append("| " + " | ".join(map(cell, [LABELS[row["variant"]], row["unit_id"], *row["scores"], f"{sum(row['scores']) / 4:.2f}"])) + " |")
    for row in fluency:
        fluent_lines += ["", "## " + LABELS[row["variant"]] + " / " + row["unit_id"], ""]
        fluent_lines += [f"- {dimension} {score}/5：{reason}" for dimension, score, reason in zip(row["dimensions"], row["scores"], row["explanations"])]
    (HERE / "fluency_scorecard.md").write_text("\n".join(fluent_lines) + "\n", encoding="utf-8")

    proof_lines = ["# 审校报告逐条复核", "", "T=可确认缺陷；N=中性或偏好；F=与现稿事实矛盾；P=部分有效；U=待核定。确证率=T/(T+N+F)，P/U另列；不是总体精确率，也不是独立专家实验。", ""]
    for variant in ("old", "new"):
        report = read_json(OLD / "proofreading_report.json" if variant == "old" else NEW / "proofreading_report.json")
        proof_lines += ["## " + ("旧版" if variant == "old" else "新版"), "", "| 条号 | 标注 | Agent原意见 | 复核依据 |", "|---:|---|---|---|"]
        for row in proofreading[variant]:
            issue = report["issues"][row["issue_number"] - 1]
            proof_lines.append("| " + " | ".join(map(cell, [row["issue_number"], row["label"], issue["detail"], row["reason"]])) + " |")
    (HERE / "proofreading_scorecard.md").write_text("\n".join(proof_lines) + "\n", encoding="utf-8")

    output_lines = ["# 每个 Agent 的改造前后输出", "", "新版止于术语返修协议错误；本页只展示真实存在的输出，不补造新版修订稿或终审。", "", "## Glossary 全量条目并排", "", "左侧旧版81条，右侧新版初次筛选72条。以英文词面匹配，缩写、全称和词形变体可能另行成行；这张表不是概念归一结果。", "", "| 英文条目 | 旧版中文 | 新版初筛中文 | 新版状态 |", "|---|---|---|---|"]
    old_index = {g["en"].casefold(): g for g in old_g}
    new_index = {g["en"].casefold(): g for g in new_g}
    for key in sorted(set(old_index) | set(new_index)):
        a, b = old_index.get(key), new_index.get(key)
        output_lines.append("| " + " | ".join(map(cell, [(a or b)["en"], a["zh"] if a else "未收录", b["zh"] if b else "未收录", b["review_status"] if b else "—"])) + " |")
    output_lines += ["", "旧版全量数据：" + link(OLD / "glossary.json"), "", "新版初筛全量数据：" + link(NEW / "glossary_v1.json"), "", "新版返修原始回答（未通过）：" + link(NEW / "agents/008_glossary_refinement/output.txt"), "", "其额外排除项为：", "", '```json\n{"candidate_id":"T116","reason":"候选表外，不处理。"}\n```', "", "候选只有T001～T115，不能把该回答视为已生效的新版词表。", "", "## Translation：完整原文与三种现有译稿"]
    for uid, item in units.items():
        pair_path = HERE / ("translation_comparison_" + uid + ".md")
        pair = ["# " + item["title"] + "：原文与译稿对照", "", "新版未进入修订，本文件中的新版本仅为初稿。", "", "## 英文原文", "", sources[uid]]
        for version in VERSIONS:
            pair += ["", "## " + LABELS[version], "", texts[version][uid]]
        pair += ["", "## 新版修订稿", "", "未生成：流程在术语返修处中断。"]
        pair_path.write_text("\n".join(pair) + "\n", encoding="utf-8")
        output_lines += ["", f"- [{item['title']} 完整对照](translation_comparison_{uid}.md)"]
    output_lines += ["", "## Proofreading", "", "旧版：" + link(OLD / "proofreading_report.json"), "", "新版：" + link(NEW / "proofreading_report.json"), "", "逐条质量复核：[57条意见的复核表](proofreading_scorecard.md)。", "", "## Manager"]
    for root, label in ((OLD, "旧版"), (NEW, "新版")):
        output_lines += ["", "### " + label, "", "```json", json.dumps(read_json(root / "manager_decision.json"), ensure_ascii=False, indent=2), "```"]
    output_lines += ["", "旧版实际生成4块修订稿，但未执行补术语。新版明确repair_glossary=true并发起返修；该词表未通过，故没有下游4次修订和终审。计划可执行性有所改善，执行闭环仍失败。", "", "## Revision / 最终复查", "", "旧版4块修订稿见上面的完整对照。新版无修订稿、无终审、无交付稿，此阶段的质量改进率不可计算。"]
    (HERE / "agent_outputs_comparison.md").write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    report = ["# 本轮重跑结果：质量前后对照（待用户审阅）", "", "结论：本轮仍不能交付。新版初稿有局部改善，但术语返修返回候选外编号T116，工作流失败。未生成新版修订稿或终审结果，没有提交或推送Git。", "", "## 1. 比较了什么", "", "改造前运行：`run-20261026T153700605628Z`。本轮原始运行：`quality-20261029T130949984518Z`。离线修正可核验的引文对齐后，续行证据：`continued-20261029T131708095244Z`。前6次响应的请求完全一致才复用，原始失败记录保留；续行只新增2次真实请求。本轮合计8次真实请求、8个不同响应ID，不能把6份复用副本再算成新增调用。", "", "同一模型名、同一PDF、同一章四块原文。提示词和流程改变；这里只有一次比较，不证明长期稳定性或单一改动的因果效果。", "", "## 2. 译得对不对，与读起来好不好，分别评分", "", "借鉴[MQM-Core](https://www.themqm.org/mqm-pillars/the-mqm-core-typology/)对准确性、术语与语言表达的区分。本实验的32项检查点和1～5分量表为自定义，均由助手对照材料标注，脚本仅核对引文与计算。不是标准MQM认证分、不是全文准确率，也未经过独立领域专家验收。", "", "| 版本 | 固定32项正确数 | 抽检准确率 | 中文表达均值/5 |", "|---|---:|---:|---:|"]
    for version in VERSIONS:
        score, language = metrics["accuracy"][version], metrics["fluency"][version]
        report.append(f"| {LABELS[version]} | {score['correct']}/32 | {score['percent']:.1f}% | {language['mean']:.2f} |")
    report += ["| 新版修订稿 | 未生成 | 不可计算 | 不可计算 |", "", "可比的同阶段是旧初稿对新初稿：32项中多正确1项，增加约3.1个百分点；表达均值从2.94到3.25，只能说本次辅助评审观察到小幅改善。不能把旧修订稿与新初稿直接当成完整流程优劣比较。", "", "检查点在本轮新模型调用开始前固定；每块8项，含否定、条件、主体、数字单位、关键概念及脚注。它们是分层定向诊断样本，未作随机抽样，不能代表全文。中文表达每块按语法、搭配、连贯、用语四维给1～5分，保留逐项理由。合法缩写、人名和英文参考书名不因含字母就算错。", "", "- [准确性32项逐句证据](accuracy_scorecard.md)", "- [中文表达四维分数与理由](fluency_scorecard.md)", "- [预先固定的指标口径](rerun_evaluation_protocol.md)", "", "A16的判定较严格：原文600多项missions被旧修订稿和新初稿收窄为600多架次任务。若该语境允许按架次翻译，需要三份稿一起重标；不能只调新稿分数。", "", "## 3. 各 Agent 的实际质量与输出", "", "| 角色 | 改造前 | 本轮改造后 | 判断 |", "|---|---|---|---|", "| Glossary初筛 | 81条；指定6个关键缩写收录0/6 | 72条；收录6/6，MTO仍标需领域审核 | 关键项覆盖改善，不等于整体精确率100% |", "| Glossary片段误收 | theater air、major c2、below the theater air均误收，3/3 | 三项均未收录，0/3 | 这组三项旧问题已避开，不代表全部噪声清零 |", "| Glossary概念归一 | Assessment/Assessing与Coordination/Coordinating两组重复 | 两组仍重复；另有全称与缩写分列 | 两组已知重复的修复率0/2 |", "| Glossary返修 | 未实际返修 | 已调用，但多返回T116，被拒绝 | 没有可用v2词表；结构契约仍失败 |", "| Translation初稿 | 29/32；表达2.94/5 | 30/32；表达3.25/5 | 同阶段局部改善，仍有断句与英文残留 |", "| Proofreading | 36条，含无问题说明与偏好 | 21条，仍有误报；逐条裁定见下 | 拿到原文后仍不能直接信任报告 |", "| Manager | 计划补术语，却没执行；4块重译已执行 | repair_glossary=true并实际发起，4块返修尚未开始 | 返修动作可执行，但被子任务失败阻断，不能称闭环完成 |", "| Revision及终审 | 有4份旧修订稿，无终审 | 本轮均未生成 | 没有证据判定其改造后的真实质量 |", "", "[每个Agent的全量输出入口、词表并排及逐块译稿](agent_outputs_comparison.md)。", "", "## 4. 审校意见本身的确证率", "", "为避免把数量当质量，对旧36条、新21条意见逐条标注。T=可确认缺陷；N=中性/偏好；F=与现稿事实矛盾；P=部分有效；U=需领域或规范核定。已裁定项确证率=T/(T+N+F)，P/U数量必须同时展示。该比值是助手判定的参考指标，不是总体精确率。", "", "| 报告 | T | N | F | P | U | 已裁定项确证率 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for variant, label in (("old", "旧版"), ("new", "新版")):
        m = metrics["proofreading"][variant]
        c = m["counts"]
        report.append(f"| {label} | {c['T']} | {c['N']} | {c['F']} | {c['P']} | {c['U']} | {c['T']}/{m['adjudicated']} = {m['confirmed_ratio_among_adjudicated'] * 100:.1f}% |")
    report += ["", "例：新版第8条说缺“第”字，但实际译文已有“第618空中作战中心”，属于明确误报。第16条把英文参考书名当未译，不符合本轮口径。第9条发现节点段有问题，但能力文字实际仍在侧栏后，诊断为全局漏译不准确，标P。", "", "[全部57条原意见与逐条裁定](proofreading_scorecard.md)。准确率32项中的旧初稿错误有A14/A15/A32，旧审校明确发现其中A15；新初稿错误有A15/A16，新审校对A15仅部分有效，对A16未指出任务/架次区别。这个检查点子集不能代替审校在全文中的总体召回率。", "", "## 5. 原问题有没有修好，有没有新问题", "", "| 问题 | 本轮新初稿/新输出 | 状态 |", "|---|---|---|", "| MTO被替换成任务式指挥 | 任务型命令（MTO） | 该概念对应关系已改善；英文含义另核对AFDP 1 |", "| 脚注9只有上标 | 已出现独立中文说明正文 | 已修复；脚注10也保留 |", "| refining译精炼、transitioning译转换 | 细化、过渡 | 表达更贴近本段语境，仍非官方中文认证 |", "| 节点句被侧栏切开 | 节点可能跨越多个层级；侧栏后作战并具有不同层级的能力 | 未修复 |", "| 旧修订稿accompanying残留 | 新初稿未出现 | 新初稿避开该回归；不能说新版修订已修复，因为未生成 |", "| 评做错字 | 新初稿未出现 | 保持旧修订已有的修复，不是全新能力证明 |", "| commander英文残留 | 它通常是 commander 及其参谋开展的第一项C2活动 | 新增：旧稿此处是指挥官 |", "| Gulf War正文未译 | 两处正文只有Gulf War，未配中文 | 相对旧初稿已配中文的表达发生回退 |", "| AFPP条目 | 新版把全称候选及AFPP缩写都排除了 | 新增覆盖回退；旧条目虽带多余and，仍保留该概念 |", "| 第三梯队 | 新版按一次性描述排除 | 原文专门解释层级名称，应重新核定，不应只因低频排除 |", "| 术语返修候选外编号 | T116，理由候选表外不处理 | 新协议错误导致流程中断 |", "", "## 6. 运行消耗与失败边界", "", f"旧完整流程11次调用累计{metrics['runtime']['old_total_tokens']:,} token；本轮仅完成到第8次就已累计{metrics['runtime']['new_total_tokens']:,} token（约{metrics['runtime']['new_total_tokens'] / metrics['runtime']['old_total_tokens']:.2f}倍）。这是逻辑token总量，不能直接当成费用倍数；两轮完成步骤也不同。新版把带完整元数据的词表反复传给下游，是需要进一步压缩的输入负担。", "", "第一次因空白断行/侧栏引文对齐停止后，进行了可追溯的本地校验修复；续行复用的6份请求必须逐项完全一致，未重发API。第8次术语返修未通过后没有重试、删掉越界项或用旧表假装返修成功。原始失败目录与响应均保留。", "", "本轮暂不提交。下一次改造应先补齐术语候选去留与别名归一、阻止审校偏好被当成确认缺陷，以及在进入模型前恢复侧栏打断的原文句子；之后才有条件继续验证精确修订与终审的实际质量。"]
    report += ["", "## 参考与复核说明", "", "MTO英文含义参考美国空军[AFDP 1《The Air Force》](https://www.doctrine.af.mil/Portals/61/documents/AFDP_1/AFDP-1.pdf)中mission-type orders的说明。此依据用于区别MTO与mission command，不能据此宣称某一中文译名具有官方标准地位。专业术语中文惯译与语境判断仍需要用户或领域人员复核。", "", "本报告和全量对照只保存在本地评审目录。此前Final总结仍是草稿，本轮不据局部改善发布新的质量合格结论。"]
    (HERE / "本轮重跑-质量对比结果.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
