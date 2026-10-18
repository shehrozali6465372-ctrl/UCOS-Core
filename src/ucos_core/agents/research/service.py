"""Orchestration for Agent 01; fail closed on auth, provider, and persistence errors."""

from ucos_core.agents.research.contracts import ResearchRequest, ResearchResponse
from ucos_core.agents.research.ports import (
    ResearchAnalyzer,
    ResearchAuthorizer,
    ResearchRepository,
    ResearchSource,
)
from ucos_core.repositories.research_postgres import ResearchIdempotencyConflict


class ResearchUnavailable(RuntimeError):
    """A required production dependency failed; no success result is returned."""


class ResearchForbidden(PermissionError):
    """The request is outside the caller's authorized tenant scope."""


class ResearchConflict(RuntimeError):
    """The request ID already belongs to a different request."""


class ResearchService:
    def __init__(
        self,
        source: ResearchSource,
        analyzer: ResearchAnalyzer,
        authorizer: ResearchAuthorizer,
        repository: ResearchRepository,
    ) -> None:
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

        # Check durable state before spending money on providers. The repository
        # compares request-defining fields and raises a conflict on ID reuse.
        try:
            existing = await self._repository.get_existing(request)
        except ResearchIdempotencyConflict as exc:
            raise ResearchConflict(
                "request_id is already used for different request inputs"
            ) from exc
        except Exception as exc:
            raise ResearchUnavailable("idempotency lookup failed") from exc
        if isinstance(existing, ResearchResponse):
            return existing

        try:
            evidence = await self._source.search(request.query, request.max_results)
            analysis = await self._analyzer.analyze(request.query, evidence) if evidence else ""
        except Exception as exc:
            raise ResearchUnavailable("research provider failed") from exc
        status = "SUCCEEDED" if evidence else "NO_RESULTS"
        try:
            await self._repository.save(request, status, analysis, evidence)
        except ResearchIdempotencyConflict as exc:
            # A concurrent request may have won the insert. Re-read and replay
            # if its original input matches; otherwise return a deterministic conflict.
            try:
                existing = await self._repository.get_existing(request)
            except ResearchIdempotencyConflict as conflict:
                raise ResearchConflict(
                    "request_id is already used for different request inputs"
                ) from conflict
            except Exception as lookup_exc:
                raise ResearchUnavailable("idempotency reconciliation failed") from lookup_exc
            if isinstance(existing, ResearchResponse):
                return existing
            raise ResearchConflict("request_id conflict could not be reconciled") from exc
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
