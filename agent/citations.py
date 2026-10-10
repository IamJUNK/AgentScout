from __future__ import annotations
import re
from collections import Counter
from models.schemas import CitationMetrics

EVIDENCE_RE = re.compile(r"\[证据\s+(E[a-zA-Z0-9_-]+)\]\(((?:https?|user)://[^\s)]+)\)")
ANY_LINK_RE = re.compile(r"\[([^\]]*)\]\(((?:https?|user)://[^\s)]+)\)")
NOTICE_PREFIXES = ("> 状态：", "> 限制：", "> 研究需求：", "> 未解答：", "> 预算：")


def _table_separator(line):
    return "|" in line and bool(re.fullmatch(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?", line))


def _report_blocks(report):
    """Yield paragraphs, list items and table rows, with their attribution scope."""
    lines = report.splitlines()
    paragraph = []
    bibliography_level = None
    fence = None
    for index, raw in enumerate(lines):
        line = raw.strip()
        delimiter = re.match(r"^(" + chr(96) + r"{3,}|~{3,})", line)
        heading = re.match(r"^(#{1,6})\s+", line)
        list_item = bool(re.match(r"^(?:[-*+] |\d+[.)]\s)", line))
        table_row = "|" in line and (line.startswith("|") or line.endswith("|"))
        notice = line.startswith(NOTICE_PREFIXES)
        if not line or delimiter or heading or list_item or table_row or notice:
            if paragraph:
                yield " ".join(paragraph), bibliography_level is None
                paragraph = []
        if delimiter:
            if fence is None:
                fence = delimiter.group()[0]
            elif delimiter.group()[0] == fence:
                fence = None
            continue
        if fence is not None or not line:
            continue
        if heading:
            level = len(heading.group(1))
            if bibliography_level is not None and level <= bibliography_level:
                bibliography_level = None
            if re.search(r"来源列表|参考资料|参考文献|references|bibliography", line, re.I):
                bibliography_level = level
            continue
        if notice:
            yield line, False
            continue
        if table_row:
            next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if _table_separator(line) or _table_separator(next_line):
                continue
            yield line, bibliography_level is None
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        paragraph.append(line)
    if paragraph:
        yield " ".join(paragraph), bibliography_level is None


def validate_report(report, results=(), documents=(), evidence=None):
    """Paragraph attribution is a structural metric, never proof of truth."""
    allowed = {item["id"]: item for item in (evidence or []) if item.get("text", "").strip()}
    urls = {item["url"] for item in allowed.values()}
    invalid, uncited, cited = set(), [], set()
    claims = attributed = 0
    for block, needs_attribution in _report_blocks(report):
        valid = [(eid, url) for eid, url in EVIDENCE_RE.findall(block) if eid in allowed and allowed[eid]["url"] == url]
        for label, url in ANY_LINK_RE.findall(block):
            label_id = re.fullmatch(r"证据\s+(E[a-zA-Z0-9_-]+)", label.strip())
            if not label_id or (label_id.group(1), url) not in valid:
                invalid.add(f"{label}: {url}")
        if not needs_attribution:
            continue
        text = ANY_LINK_RE.sub("", block).strip(" -*|>")
        if not text or re.fullmatch(r"[:\- |]+", text):
            continue
        claims += 1
        if not valid:
            uncited.append(block)
            continue
        attributed += 1
        cited.update(url for _, url in valid)
        assertions = re.findall(r"\d+(?:\.\d+)?%|绝对安全|完全安全|保证成功|必然成功", text)
        support = " ".join(allowed[eid]["text"] for eid, _ in valid)
        if any(assertion not in support for assertion in assertions):
            uncited.append(block)
    if not report.strip():
        uncited.append("报告为空。")
    elif not cited:
        uncited.append("报告正文没有可追溯的有效证据引用。")
    return CitationMetrics(total_sources=len(urls), cited_sources=len(cited), source_utilization=len(cited)/len(urls) if urls else 0.0, citation_coverage=attributed/claims if claims else 0.0, claim_count=claims, attributed_claim_count=attributed, invalid_citations=sorted(invalid), uncited_claims=list(dict.fromkeys(uncited)))


def duplicate_citations(report):
    return sorted(url for url, count in Counter(url for _, url in EVIDENCE_RE.findall(report)).items() if count > 1)
