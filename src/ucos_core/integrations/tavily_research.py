"""Tavily evidence retrieval adapter with strict timeouts and input bounds."""

import json
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
        max_response_bytes = 1_048_576
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            async with client.stream(
                "POST",
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                },
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > max_response_bytes:
                        raise RuntimeError("Tavily response exceeded the 1 MiB size limit")
                    body.extend(chunk)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Tavily returned an invalid JSON response") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise RuntimeError("Tavily returned an invalid response shape")

        timestamp = datetime.now(UTC).isoformat()
        items = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            url = _candidate_evidence_url(item.get("url"))
            excerpt = item.get("content")
            if url is None or not isinstance(excerpt, str) or not excerpt.strip():
                continue
            raw_title = item.get("title")
            title = (
                raw_title.strip()
                if isinstance(raw_title, str) and raw_title.strip()
                else url
            )
            try:
                items.append(
                    EvidenceItem(
                        source="tavily",
                        title=title[:500],
                        url=url,
                        excerpt=excerpt.strip()[:8000],
                        retrieved_at=timestamp,
                    )
                )
            except ValueError:
                # A provider result that violates the shared evidence contract is
                # omitted rather than converted to fabricated/invalid evidence.
                continue
        return items[:max_results]
