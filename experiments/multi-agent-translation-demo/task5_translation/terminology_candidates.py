"""从章节原文提取带客观特征的候选术语，不调用模型。"""

from collections import defaultdict
import re


ACRONYM_STOPWORDS = {"a", "an", "and", "for", "of", "the", "to"}
EDGE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "conduct", "during", "example", "examples", "is", "of", "on", "or", "see",
    "that", "the", "their", "this", "to", "with",
}
DOMAIN_MARKERS = {
    "air", "assessment", "battle", "c2", "command", "commander", "control",
    "decision", "design", "echelon", "execution", "force", "framework",
    "intent", "mission", "operation", "operational", "planning", "process",
    "tasking", "tactical", "theater",
}
GENERIC_HEADINGS = {"background", "history", "example", "examples"}
SIGNAL_WEIGHTS = {
    "section_heading": 3,
    "explicit_definition": 3,
    "acronym_full_form": 3,
    "contrast_pair": 3,
    "named_framework": 3,
    "named_level": 3,
    "quoted_label": 3,
    "repeated_phrase": 2,
    "cross_section": 2,
}


def _normalize_text(text):
    text = re.sub(r"\bexecut\s+ing\b", "executing", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgenerati\s+on\b", "generation", text, flags=re.IGNORECASE)
    text = re.sub(r"\brefinin\s+g\b", "refining", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-\s*", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def _canonical(phrase):
    return _normalize_text(phrase).casefold()


def _term_tokens(text):
    return [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", text)]


def _count_occurrences(text, phrase):
    source = _term_tokens(text)
    target = _term_tokens(phrase)
    if not target or len(target) > len(source):
        return 0
    width = len(target)
    return sum(source[index:index + width] == target for index in range(len(source) - width + 1))


def _definition_subject(value):
    words = re.findall(r"[A-Za-z0-9’'-]+", value)
    while words and words[0].casefold() in {"a", "an", "the"}:
        words = words[1:]
    lowered = [word.casefold() for word in words]
    if not words or len(words) > 6:
        return None
    if lowered[:2] in (["another", "commonly"], ["history", "shows"], ["most", "relevant"], ["single", "most"]):
        return None
    if any(word in {"shows", "that"} for word in lowered):
        return None
    return " ".join(words)


def _derive_full_form(left_text, acronym):
    """从括号前最多十二个词中寻找与缩写首字母匹配的最长短语。"""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9’'-]*", left_text)[-12:]
    target = re.sub(r"[^A-Z0-9]", "", acronym.upper())
    for start in range(len(tokens)):
        segment = tokens[start:]
        all_initials = "".join(token[0].upper() for token in segment)
        content_initials = "".join(
            token[0].upper()
            for token in segment
            if token.casefold() not in ACRONYM_STOPWORDS
        )
        if all_initials == target or content_initials == target:
            while segment and segment[0].casefold() in {"a", "an", "the"}:
                segment = segment[1:]
            return " ".join(segment)
    return None


def _short_evidence(text, phrase, limit=220):
    normalized = _normalize_text(text)
    source_matches = list(re.finditer(r"[A-Za-z0-9]+", normalized))
    source_tokens = [match.group(0).casefold() for match in source_matches]
    target_tokens = _term_tokens(phrase)
    span = None
    if target_tokens:
        width = len(target_tokens)
        for offset in range(len(source_tokens) - width + 1):
            if source_tokens[offset:offset + width] == target_tokens:
                span = (source_matches[offset].start(), source_matches[offset + width - 1].end())
                break
    if span is None:
        return normalized[:limit]
    start = max(0, span[0] - 70)
    end = min(len(normalized), span[1] + 120)
    excerpt = normalized[start:end].strip()
    if start:
        excerpt = "…" + excerpt
    if end < len(normalized):
        excerpt += "…"
    return excerpt[:limit]


def extract_term_candidates(units):
    """返回带频次、章节分布、结构信号和原文证据的高召回候选。"""
    records = {}
    unit_texts = {unit["title"]: _normalize_text(unit["text"]) for unit in units}

    def add(phrase, signal, evidence, location):
        phrase = _normalize_text(phrase).strip(" .,:;\"“”")
        if not phrase or len(phrase) > 120:
            return
        key = _canonical(phrase)
        record = records.setdefault(
            key,
            {"en": phrase, "signals": set(), "evidence": "", "locations": set()},
        )
        record["signals"].add(signal)
        record["locations"].add(location)
        if not record["evidence"]:
            record["evidence"] = _short_evidence(evidence, phrase)

    for unit in units:
        title = unit["title"]
        raw = unit["text"]
        normalized = unit_texts[title]

        raw_lines = raw.splitlines()
        heading_lines = set()
        for line in raw_lines:
            heading = _normalize_text(line).strip().strip(" .:")
            words = re.findall(r"[A-Za-z0-9]+", heading)
            if (
                heading
                and heading.isupper()
                and 1 <= len(words) <= 8
                and not heading.startswith("CHAPTER ")
                and heading.casefold() not in GENERIC_HEADINGS
            ):
                add(heading.title(), "section_heading", line, title)
                heading_lines.add(line)

        for match in re.finditer(r"(?m)^([A-Z][A-Za-z0-9’' -]{1,60})\.\s+", raw):
            label_words = re.findall(r"[A-Za-z0-9’'-]+", match.group(1))
            if (
                1 <= len(label_words) <= 6
                and "as" not in {word.casefold() for word in label_words}
                and not (len(label_words[-1]) == 1 and label_words[-1].isupper())
            ):
                add(_normalize_text(match.group(1)), "section_heading", raw, title)

        definition_source = _normalize_text("\n".join(line for line in raw_lines if line not in heading_lines))
        definition_pattern = re.compile(
            r"(?:^|[.!?]\s+)(?:The\s+)?([A-Z][A-Za-z0-9’' -]{1,80}?)\s+"
            r"(?:is|are)\s+(?:defined as|a\s|an\s|the\s|putting\s|used\s)",
        )
        for match in definition_pattern.finditer(definition_source):
            subject = _definition_subject(match.group(1))
            if subject:
                add(subject, "explicit_definition", definition_source, title)

        for match in re.finditer(r"\(\s*([A-Z][A-Z0-9-]{1,15})\s*\)", normalized):
            full_form = _derive_full_form(normalized[:match.start()], match.group(1))
            if full_form:
                add(f"{full_form} ({match.group(1)})", "acronym_full_form", normalized, title)

        for match in re.finditer(r"\((measures?\s+of\s+[A-Za-z -]{2,50})\)", normalized, re.IGNORECASE):
            add(match.group(1), "contrast_pair", normalized, title)

        for match in re.finditer(r"\b[A-Z]{2,}(?:\s*-\s*[A-Z]{2,})+\b", raw):
            add(match.group(0), "named_framework", raw, title)

        for match in re.finditer(r"[“\"]([^”\"]{1,60})[”\"]", normalized):
            phrase = match.group(1).strip(" .")
            phrase_tokens = _term_tokens(phrase)
            if 1 <= len(phrase_tokens) <= 6 and any(token in DOMAIN_MARKERS or token == "echelon" for token in phrase_tokens):
                add(phrase, "quoted_label", normalized, title)

        for match in re.finditer(r"\b\d+(?:st|nd|rd|th)\s+echelon\b", normalized, re.IGNORECASE):
            add(match.group(0), "named_level", normalized, title)

    phrase_sections = defaultdict(set)
    phrase_counts = defaultdict(int)
    phrase_evidence = {}
    for unit in units:
        title = unit["title"]
        text = unit_texts[title]
        for segment in re.split(r"[.!?;,:()\[\]“”\"]+", text):
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9’'-]*|C2", segment)
            lowered = [token.casefold() for token in tokens]
            for size in range(2, 5):
                for index in range(len(tokens) - size + 1):
                    parts = lowered[index:index + size]
                    if parts[0] in EDGE_STOPWORDS or parts[-1] in EDGE_STOPWORDS:
                        continue
                    if not any(part in DOMAIN_MARKERS for part in parts):
                        continue
                    phrase = " ".join(parts)
                    phrase_counts[phrase] += 1
                    phrase_sections[phrase].add(title)
                    phrase_evidence.setdefault(phrase, segment)

    for phrase, count in phrase_counts.items():
        if count >= 3 or (count >= 2 and len(phrase_sections[phrase]) >= 2):
            first_location = sorted(phrase_sections[phrase])[0]
            add(phrase, "repeated_phrase", phrase_evidence[phrase], first_location)
            records[_canonical(phrase)]["locations"].update(phrase_sections[phrase])

    candidates = []
    for record in records.values():
        present_locations = [
            title for title, text in unit_texts.items() if _count_occurrences(text, record["en"]) > 0
        ]
        exact_count = sum(_count_occurrences(text, record["en"]) for text in unit_texts.values())
        if exact_count == 0:
            continue
        signals = set(record["signals"])
        if len(present_locations) >= 2:
            signals.add("cross_section")
        candidates.append({
            "en": record["en"],
            "exact_count": exact_count,
            "section_count": len(present_locations),
            "signals": sorted(signals),
            "feature_score": sum(SIGNAL_WEIGHTS.get(signal, 0) for signal in signals),
            "evidence": record["evidence"],
            "locations": present_locations or sorted(record["locations"]),
        })

    candidates.sort(key=lambda item: (-item["feature_score"], -item["exact_count"], item["en"].casefold()))
    for index, candidate in enumerate(candidates, 1):
        candidate["candidate_id"] = f"T{index:03d}"
    return candidates
