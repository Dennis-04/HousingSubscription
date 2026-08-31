from __future__ import annotations

import ipaddress
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from housing_backend.domain.entities import DocumentCandidate


class HttpDocumentFetcher:
    def __init__(self, client: httpx.AsyncClient, max_bytes: int) -> None:
        self.client = client
        self.max_bytes = max_bytes

    async def fetch(self, candidate: DocumentCandidate) -> tuple[bytes, str]:
        content, content_type, headers = await self._download(candidate.source_url)

        if "html" not in content_type.lower() and not content.lstrip().startswith(b"<"):
            self._copy_cache_headers(candidate, headers)
            return content, content_type

        target = self._discover_attachment(candidate.source_url, content.decode("utf-8", "ignore"))
        if not target:
            raise RuntimeError(f"No downloadable attachment found at {candidate.source_url}")
        body, mime, attachment_headers = await self._download(target)
        self._copy_cache_headers(candidate, attachment_headers)
        return body, mime

    async def _download(self, url: str) -> tuple[bytes, str, httpx.Headers]:
        self._validate_url(url)
        chunks: list[bytes] = []
        size = 0
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            self._validate_url(str(response.url))
            declared_size = response.headers.get("content-length")
            if declared_size and int(declared_size) > self.max_bytes:
                raise RuntimeError(f"Document exceeds {self.max_bytes} bytes")
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise RuntimeError(f"Document exceeds {self.max_bytes} bytes")
                chunks.append(chunk)
            mime = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return b"".join(chunks), mime, response.headers

    @staticmethod
    def _copy_cache_headers(candidate: DocumentCandidate, headers: httpx.Headers) -> None:
        candidate.etag = headers.get("etag")
        candidate.last_modified = headers.get("last-modified")

    def _discover_attachment(self, base_url: str, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        ranked: list[tuple[int, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            text = anchor.get_text(" ", strip=True)
            haystack = f"{href} {text}".lower()
            score = 0
            if ".pdf" in haystack:
                score += 100
            if any(word in haystack for word in ("모집공고", "공고문", "첨부파일", "download")):
                score += 30
            if any(ext in haystack for ext in (".hwp", ".hwpx", ".docx")):
                score += 10
            if score and not href.lower().startswith("javascript:"):
                ranked.append((score, urljoin(base_url, href)))

        if ranked:
            return max(ranked, key=lambda item: item[0])[1]

        absolute = re.findall(r"https?://[^\"'<>\s]+", html)
        for url in absolute:
            if any(ext in url.lower() for ext in (".pdf", ".hwp", ".hwpx")):
                return url.replace("&amp;", "&")
        return None

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("Only public HTTP(S) document URLs are allowed")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return
        if address.is_private or address.is_loopback or address.is_link_local:
            raise RuntimeError("Private network document URLs are blocked")
