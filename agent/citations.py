from __future__ import annotations
import re
from typing import Iterable
from models.schemas import CitationMetrics, SearchResult

LINK_RE = re.compile(r"\[来源\s*\d+\]\((https?://[^\s)]+)\)")
ANY_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")

def validate_report(report: str, results: Iterable[SearchResult | dict], documents: Iterable[dict] = ()) -> CitationMetrics:
    allowed = {item.url if isinstance(item, SearchResult) else item["url"] for item in results}
    links = LINK_RE.findall(report)
    valid = set(links) & allowed
    invalid = sorted(set(ANY_LINK_RE.findall(report)) - allowed)
    content_by_url = {document["url"]: document.get("content", "") for document in documents}
    claims, findings = [], False
    if report.strip() and not valid:
        claims.append("报告没有有效规范引用。")
    for line in report.splitlines():
        if line.startswith("## "):
            findings = "关键发现" in line or "分点分析" in line
        elif findings and re.match(r"\s*(?:[-*]|\d+[.)])\s", line):
            cited = LINK_RE.findall(line)
            if not cited:
                claims.append(line.strip())
            else:
                assertions = re.findall(r"\d+(?:\.\d+)?%|绝对安全|完全安全|保证成功|必然成功", line)
                evidence = " ".join(content_by_url.get(url, "") for url in cited)
                if content_by_url and any(assertion not in evidence for assertion in assertions):
                    claims.append(line.strip())
    return CitationMetrics(total_sources=len(allowed), cited_sources=len(valid), citation_coverage=len(valid) / len(allowed) if allowed else 0.0, invalid_citations=invalid, uncited_claims=claims)

def duplicate_citations(report: str) -> list[str]:
    links = LINK_RE.findall(report)
    return sorted({url for url in links if links.count(url) > 1})
