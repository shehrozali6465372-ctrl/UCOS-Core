"""Tavily evidence retrieval adapter with strict timeouts and input bounds."""

import os
from datetime import UTC, datetime

import httpx

from ucos_core.agents.research.contracts import EvidenceItem


class TavilyResearchSource:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("TAVILY_API_KEY", "").strip()

    async def search(self, query: str, max_results: int) -> list[EvidenceItem]:
        if not self._api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self._api_key, "query": query,
                      "max_results": max_results, "search_depth": "advanced"},
            )
            response.raise_for_status()
            payload = response.json()
        timestamp = datetime.now(UTC).isoformat()
        items = []
        for item in payload.get("results", []):
            url = item.get("url")
            title = item.get("title")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                continue
            items.append(EvidenceItem(
                source="tavily", title=str(title or url)[:500], url=url,
                excerpt=str(item.get("content", ""))[:8000], retrieved_at=timestamp,
            ))
        return items[:max_results]
