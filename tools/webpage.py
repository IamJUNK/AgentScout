from __future__ import annotations

import copy
import ipaddress
import re
import socket
import time
from collections import OrderedDict
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from models.schemas import SearchResult, SourceDocument, as_utc_iso

_PAGE_CACHE: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
_BLOCKED = re.compile(r"access denied|verify (?:that )?you are human|enable javascript|checking your browser|just a moment|验证码|访问被拒绝|安全验证", re.I)


def clear_page_cache() -> None:
    _PAGE_CACHE.clear()


def _extract_html(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    date_tag = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"})
    published = date_tag.get("content") if date_tag else None
    for tag in soup(["script", "style", "nav", "noscript"]):
        tag.decompose()
    root = soup.body or soup
    # Paragraphs/headings/table rows survive cleaning. No positional body cap.
    for row in root.find_all("tr"):
        row.replace_with("\n" + " | ".join(c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])) + "\n")
    for heading in root.find_all(re.compile(r"^h[1-6]$")):
        heading.replace_with("\n" + "#" * int(heading.name[1]) + " " + heading.get_text(" ", strip=True) + "\n")
    for block in root.find_all(["p", "li", "blockquote", "pre"]):
        block.insert_before("\n")
        block.insert_after("\n")
    text = "\n".join(" ".join(line.split()) for line in root.get_text(" ", strip=False).splitlines() if line.strip())
    return text, published


def _clean_html(html: str) -> str:
    return _extract_html(html)[0]


def _check_public_host(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) pages are supported")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Private or local network pages are not supported")


def _fetch_content(url: str, timeout: float = 10, max_bytes: int = 2_000_000, deadline: float | None = None) -> dict:
    deadline = deadline or time.monotonic() + timeout
    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": "AgentScout/0.2"}) as client:
        for _ in range(5):
            if time.monotonic() >= deadline:
                raise TimeoutError("Page acquisition budget exhausted")
            _check_public_host(url)
            with client.stream("GET", url, timeout=min(timeout, max(.05, deadline - time.monotonic()))) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    raise ValueError("Unsupported content type: " + (content_type or "unknown"))
                payload = bytearray()
                truncated = False
                for chunk in response.iter_bytes(chunk_size=65536):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Page acquisition budget exhausted")
                    room = max_bytes - len(payload)
                    payload.extend(chunk[:room])
                    if len(chunk) > room:
                        truncated = True
                        break
                decoded = payload.decode(response.encoding or "utf-8", errors="replace")
                content, published = _extract_html(decoded) if content_type != "text/plain" else (decoded, None)
                if len(content) < 1500 and _BLOCKED.search(content):
                    raise ValueError("Verification/login/block page is not research evidence")
                return {"content": content, "published_at": published, "retrieved_at": as_utc_iso(), "content_type": content_type, "download_truncated": truncated}
    raise RuntimeError("Too many redirects")


def fetch_page(item: SearchResult, timeout_seconds: float = 10, *, max_bytes: int = 2_000_000, cache_ttl: float = 600, force_refresh: bool = False, deadline: float | None = None) -> SourceDocument:
    base = dict(title=item.title, url=item.url, source_id=item.source_id, question_ids=item.question_ids, snippet=item.snippet, published_at=item.published_at, publication_date_source="search metadata (unverified)" if item.published_at else None)
    key = (item.url, max_bytes)
    try:
        entry = _PAGE_CACHE.get(key)
        hit = bool(not force_refresh and entry and time.monotonic() - entry[0] < cache_ttl)
        if hit:
            data = copy.deepcopy(entry[1])
            _PAGE_CACHE.move_to_end(key)
        else:
            data = _fetch_content(item.url, timeout_seconds, max_bytes, deadline)
            if data["content"] and not data["download_truncated"] and cache_ttl > 0:
                _PAGE_CACHE[key] = (time.monotonic(), copy.deepcopy(data))
                if len(_PAGE_CACHE) > 128:
                    _PAGE_CACHE.popitem(last=False)
        content = data["content"]
        truncated = data["download_truncated"]
        status = ("partial" if truncated else "success") if content else ("snippet_only" if item.snippet else "failed")
        if data.get("published_at"):
            base["published_at"] = data["published_at"]
            base["publication_date_source"] = "page metadata (unverified)"
        return SourceDocument(**base, content=content, retrieved_at=data["retrieved_at"], fetch_status=status, fetch_error="下载达到字节预算，未获取全文。" if truncated else ("未提取到正文。" if not content else None), content_type=data["content_type"], download_truncated=truncated, cache_hit=hit)
    except Exception as exc:
        return SourceDocument(**base, content="", fetch_status="snippet_only" if item.snippet else "failed", fetch_error=f"{type(exc).__name__}: {exc}")


def fetch_pages(items: Iterable[SearchResult], max_pages: int = 8, **kwargs) -> list[SourceDocument]:
    return [fetch_page(item if isinstance(item, SearchResult) else SearchResult.model_validate(item), **kwargs) for item in list(items)[:max_pages]]
