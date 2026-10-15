"""Tavily transport adapter owned by L11; L02 consumes only the ResearchSourcePort."""

from datetime import UTC, datetime
from hashlib import sha256
import os
from typing import Any

import httpx

from ucos_core.layers.l02_research.contracts import ResearchSourceObservation
from ucos_core.layers.l02_research.ports import DependencyUnavailable, ResearchProviderError


class TavilyResearchAdapter:
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, *, api_key: str | None = None, timeout_seconds: float = 10.0) -> None:
        configured_key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")
        self._api_key = configured_key.strip()
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str, *, max_results: int) -> list[ResearchSourceObservation]:
        if not self._api_key:
            raise DependencyUnavailable("L11 Tavily credentials are not configured")
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self.ENDPOINT, json=payload)
        except httpx.TimeoutException as error:
            raise ResearchProviderError("SOURCE_TIMEOUT", retryable=True) from error
        except httpx.HTTPError as error:
            raise ResearchProviderError("SOURCE_TRANSPORT_ERROR", retryable=True) from error
        if response.status_code >= 500 or response.status_code == 429:
            raise ResearchProviderError("SOURCE_PROVIDER_UNAVAILABLE", retryable=True)
        if response.is_error:
            raise ResearchProviderError("SOURCE_PROVIDER_REJECTED", retryable=False)
        try:
            document: dict[str, Any] = response.json()
            rows = document.get("results", [])
            if not isinstance(rows, list):
                raise ValueError("results is not a list")
            return [self._normalize(row) for row in rows[:max_results] if isinstance(row, dict)]
        except (TypeError, ValueError, KeyError) as error:
            raise ResearchProviderError("SOURCE_RESPONSE_INVALID", retryable=False) from error

    @staticmethod
    def _normalize(row: dict[str, Any]) -> ResearchSourceObservation:
        url = str(row.get("url", "")).strip()
        if not url.startswith(("https://", "http://")):
            raise ValueError("source URL is missing or unsupported")
        title = str(row.get("title", "")).strip() or url
        snippet = str(row.get("content", ""))[:12000] or title
        source_timestamp = TavilyResearchAdapter._timestamp(row.get("published_date"))
        score = row.get("score")
        confidence = float(score) if isinstance(score, (int, float)) else None
        if confidence is not None:
            confidence = min(1.0, max(0.0, confidence))
        return ResearchSourceObservation(
            source_id=sha256(url.encode("utf-8")).hexdigest(),
            provider="tavily",
            url=url,
            title=title,
            snippet=snippet,
            observed_at=datetime.now(UTC),
            source_timestamp=source_timestamp,
            confidence=confidence,
        )

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
