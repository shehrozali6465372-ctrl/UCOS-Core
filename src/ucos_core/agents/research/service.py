"""Orchestration for Agent 01; fail closed on auth, provider, and persistence errors."""

import logging

from ucos_core.agents.research.contracts import (
    ResearchRequest,
    ResearchResponse,
    ResearchTaskResponse,
)
from ucos_core.agents.research.ports import (
    ResearchAnalyzer,
    ResearchAuthorizer,
    ResearchRepository,
    ResearchSource,
)
from ucos_core.repositories.research_postgres import (
    ResearchIdempotencyConflict,
    ResearchRequestInProgress,
)


logger = logging.getLogger(__name__)


class ResearchUnavailable(RuntimeError):
    """A required production dependency failed; no success result is returned."""


class ResearchForbidden(PermissionError):
    """The request is outside the caller's authorized tenant scope."""


class ResearchConflict(RuntimeError):
    """The request ID already belongs to a different request."""


class ResearchBusy(RuntimeError):
    """The same request is already being processed by another worker."""


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

        try:
            claim = await self._repository.claim(request)
        except ResearchIdempotencyConflict as exc:
            raise ResearchConflict(
                "request_id is already used for different request inputs"
            ) from exc
        except ResearchRequestInProgress as exc:
            raise ResearchBusy("request_id is already being processed; retry shortly") from exc
        except Exception as exc:
            raise ResearchUnavailable("idempotency claim failed") from exc
        if isinstance(claim, ResearchResponse):
            return claim
        generation = claim

        stage = "tavily_search"
        try:
            evidence = await self._source.search(request.query, request.max_results)
            stage = "model_analysis"
            analysis = await self._analyzer.analyze(request.query, evidence) if evidence else ""
            status = "SUCCEEDED" if evidence else "NO_RESULTS"
            stage = "postgres_persist"
            await self._repository.save(request, generation, status, analysis, evidence)
        except ResearchIdempotencyConflict as exc:
            # A stale worker cannot release or overwrite the newer generation.
            logger.warning("agent01_failure stage=idempotency_fence error_type=%s", type(exc).__name__)
            raise ResearchConflict("request claim was superseded or conflicted") from exc
        except Exception as exc:
            # Log only an allowlisted stage and exception class. Provider exception
            # strings may contain request URLs, credentials, or sensitive payloads.
            logger.error(
                "agent01_failure stage=%s error_type=%s",
                stage,
                type(exc).__name__,
            )
            try:
                await self._repository.release(request, generation)
            except Exception as release_exc:
                logger.warning(
                    "agent01_failure stage=claim_release error_type=%s",
                    type(release_exc).__name__,
                )
            raise ResearchUnavailable("research provider or durable persistence failed") from exc

        return ResearchResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            status=status,
            analysis=analysis,
            evidence=evidence,
            persisted=True,
        )


    async def get_result(
        self,
        request_id: str,
        tenant_id: str,
        workspace_id: str,
        brand_id: str,
    ) -> ResearchTaskResponse | None:
        """Read a stored task only after the configured project scope is authorized."""
        try:
            allowed = await self._authorizer.authorize(
                tenant_id, workspace_id, brand_id
            )
        except Exception as exc:
            raise ResearchUnavailable("authorization service unavailable") from exc
        if not allowed:
            raise ResearchForbidden("request is outside authorized project scope")
        try:
            return await self._repository.get_result(
                request_id, tenant_id, workspace_id, brand_id
            )
        except Exception as exc:
            raise ResearchUnavailable("research result lookup failed") from exc
