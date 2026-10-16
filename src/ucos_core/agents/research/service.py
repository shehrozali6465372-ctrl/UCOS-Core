"""Orchestration for Agent 01; fail closed on auth, provider, and persistence errors."""

from ucos_core.agents.research.contracts import ResearchRequest, ResearchResponse
from ucos_core.agents.research.ports import (
    ResearchAnalyzer,
    ResearchAuthorizer,
    ResearchRepository,
    ResearchSource,
)


class ResearchUnavailable(RuntimeError):
    """A required production dependency failed; no success result is returned."""


class ResearchForbidden(PermissionError):
    """The request is outside the caller's authorized tenant scope."""


class ResearchService:
    def __init__(self, source: ResearchSource, analyzer: ResearchAnalyzer,
                 authorizer: ResearchAuthorizer, repository: ResearchRepository) -> None:
        self._source = source
        self._analyzer = analyzer
        self._authorizer = authorizer
        self._repository = repository

    async def execute(self, request: ResearchRequest) -> ResearchResponse:
        try:
            allowed = await self._authorizer.authorize(
                request.tenant_id, request.workspace_id, request.brand_id
            )
        except Exception as exc:
            raise ResearchUnavailable("authorization service unavailable") from exc
        if not allowed:
            raise ResearchForbidden("request is outside authorized tenant scope")
        try:
            evidence = await self._source.search(request.query, request.max_results)
            analysis = await self._analyzer.analyze(request.query, evidence) if evidence else ""
        except Exception as exc:
            raise ResearchUnavailable("research provider failed") from exc
        status = "SUCCEEDED" if evidence else "NO_RESULTS"
        try:
            await self._repository.save(request, status, analysis, evidence)
        except Exception as exc:
            raise ResearchUnavailable("durable persistence failed") from exc
        return ResearchResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            status=status,
            analysis=analysis,
            evidence=evidence,
            persisted=True,
        )
