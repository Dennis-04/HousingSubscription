from __future__ import annotations

import asyncio
import random
import re
from typing import Any

import httpx


class UpstreamError(RuntimeError):
    pass


_SECRET_PATTERN = re.compile(
    r"(?i)(serviceKey|authorization|x-admin-token)(?:=|%3D|[\"']?\s*:\s*[\"']?)([^&\s\"']+)"
)


def safe_error(error: BaseException) -> str:
    """Return an operator-useful error without query-string credentials."""
    text = _SECRET_PATTERN.sub(r"\1=<redacted>", str(error))
    return text[:1000]


class ResilientHttpClient:
    def __init__(self, timeout_seconds: float, max_retries: int) -> None:
        self.max_retries = max(1, max_retries)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": "HousingSubscriptionCollector/0.1 (+source-linked-app)"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error = "unknown upstream error"
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise UpstreamError(f"Unexpected payload from {url}")
                self._raise_api_error(payload, url)
                return payload
            except (httpx.HTTPError, ValueError, UpstreamError) as exc:
                last_error = safe_error(exc)
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if retryable and attempt + 1 < self.max_retries:
                    retry_after = None
                    if isinstance(exc, httpx.HTTPStatusError):
                        retry_after = exc.response.headers.get("retry-after")
                    try:
                        delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                    except ValueError:
                        delay = 0.5 * (2**attempt)
                    await asyncio.sleep(delay + random.uniform(0, 0.25))
                    continue
                break
        raise UpstreamError(f"Upstream request failed: {url}: {last_error}")

    @staticmethod
    def _raise_api_error(payload: dict[str, Any], url: str) -> None:
        result = payload.get("result") or payload.get("response", {}).get("header") or {}
        code = str(
            result.get("code") or result.get("resultCode") or result.get("RESULT_CODE") or ""
        )
        if code and code not in {"0", "00", "000", "SUCCESS"}:
            message = (
                result.get("message")
                or result.get("resultMsg")
                or result.get("RESULT_MESSAGE")
                or "unknown API error"
            )
            raise UpstreamError(f"{url}: API error {code}: {message}")
