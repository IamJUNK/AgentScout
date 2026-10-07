from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from models.schemas import SearchResult, SourceDocument


def _clean_html(html: str, max_chars: int = 8000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:min(max_chars, 8000)]


def _check_public_host(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) pages are supported")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Private or local network pages are not supported")


@lru_cache(maxsize=128)
def _fetch_content(url: str, timeout: float, max_chars: int) -> str:
    with httpx.Client(timeout=min(timeout, 10), follow_redirects=False, headers={"User-Agent": "AgentScout/0.1"}) as client:
        for _ in range(4):
            _check_public_host(url)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk[:max(0, 1_000_000 - len(payload))])
                    if len(payload) >= 1_000_000:
                        break
                html = payload.decode(response.encoding or "utf-8", errors="replace")
                return _clean_html(html, min(max_chars, 8000))
    raise RuntimeError("Too many redirects")


def fetch_page(item: SearchResult, timeout_seconds: float = 10.0, max_chars: int = 8000) -> SourceDocument:
    try:
        content = _fetch_content(item.url, min(timeout_seconds, 10), min(max_chars, 8000))
        return SourceDocument(title=item.title, url=item.url, content=content or item.snippet, fetch_status="success" if content else "snippet_only")
    except Exception as exc:
        return SourceDocument(title=item.title, url=item.url, content=item.snippet[:min(max_chars, 8000)], fetch_status="snippet_only" if item.snippet else "failed", fetch_error=f"{type(exc).__name__}: {exc}")


def fetch_pages(items: Iterable[SearchResult], max_pages: int = 5, timeout_seconds: float = 10.0, max_chars: int = 8000) -> list[SourceDocument]:
    bounded = list(items)[:min(max_pages, 5)]
    return [fetch_page(item if isinstance(item, SearchResult) else SearchResult.model_validate(item), timeout_seconds, max_chars) for item in bounded]
