"""Ports for source retrieval, analysis, authorization, and durable storage."""

from typing import Protocol

from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest, ResearchResponse


class ResearchSource(Protocol):
    async def search(self, query: str, max_results: int) -> list[EvidenceItem]: ...


class ResearchAnalyzer(Protocol):
    async def analyze(self, query: str, evidence: list[EvidenceItem]) -> str: ...


class ResearchAuthorizer(Protocol):
    async def authorize(self, tenant_id: str, workspace_id: str, brand_id: str) -> bool: ...


class ResearchRepository(Protocol):
    async def get_existing(self, request: ResearchRequest) -> ResearchResponse | None: ...

    async def save(self, request: ResearchRequest, status: str, analysis: str,
                   evidence: list[EvidenceItem]) -> None: ...
