"""Tavily evidence retrieval adapter with strict timeouts and input bounds."""

import os
from datetime import UTC, datetime

import httpx

from ucos_core.agents.research.contracts import EvidenceItem
from ucos_core.agents.research.evidence_url import is_valid_evidence_url


def _candidate_evidence_url(value: object) -> str | None:
    """Preserve only citations that satisfy the shared evidence URL contract."""
    if not isinstance(value, str):
        return None
    return value if is_valid_evidence_url(value) else None


class TavilyResearchSource:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("TAVILY_API_KEY", "").strip()

    async def search(self, query: str, max_results: int) -> list[EvidenceItem]:
        if not self._api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                },
            )
            response.raise_for_status()
            payload = response.json()
        timestamp = datetime.now(UTC).isoformat()
        items = []
        for item in payload.get("results", []):
            url = _candidate_evidence_url(item.get("url"))
            if url is None:
                continue
            title = item.get("title")
            try:
                items.append(
                    EvidenceItem(
                        source="tavily",
                        title=str(title or url)[:500],
                        url=url,
                        excerpt=str(item.get("content", ""))[:8000],
                        retrieved_at=timestamp,
                    )
                )
            except ValueError:
                # A provider result that violates the shared evidence contract is
                # omitted rather than converted to fabricated/invalid evidence.
                continue
        return items[:max_results]
