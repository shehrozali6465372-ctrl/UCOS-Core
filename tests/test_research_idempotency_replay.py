"""Regression tests for durable Agent 01 idempotency replay."""

from unittest.mock import AsyncMock

import pytest

from ucos_core.agents.research.contracts import ResearchRequest, ResearchResponse
from ucos_core.agents.research.service import ResearchConflict, ResearchService


def make_request() -> ResearchRequest:
    return ResearchRequest(
        request_id="retry-1",
        correlation_id="corr-1",
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        brand_id="brand-1",
        workflow_id="workflow-1",
        workflow_step_id="step-1",
        query="market trends",
        max_results=3,
    )


@pytest.mark.asyncio
async def test_completed_retry_replays_persisted_response_without_provider_calls() -> None:
    request = make_request()
    stored = ResearchResponse(
        request_id=request.request_id,
        correlation_id=request.correlation_id,
        status="SUCCEEDED",
        analysis="Stored analysis",
        evidence=[],
        persisted=True,
    )
    source, analyzer, authorizer, repository = (AsyncMock() for _ in range(4))
    authorizer.authorize.return_value = True
    repository.get_existing.return_value = stored

    result = await ResearchService(source, analyzer, authorizer, repository).execute(request)

    assert result == stored
    source.search.assert_not_awaited()
    analyzer.analyze.assert_not_awaited()
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_id_reuse_with_different_inputs_conflicts_before_provider_call() -> None:
    request = make_request()
    source, analyzer, authorizer, repository = (AsyncMock() for _ in range(4))
    authorizer.authorize.return_value = True
    from ucos_core.repositories.research_postgres import ResearchIdempotencyConflict
    repository.get_existing.side_effect = ResearchIdempotencyConflict("input mismatch")

    with pytest.raises(ResearchConflict):
        await ResearchService(source, analyzer, authorizer, repository).execute(request)

    source.search.assert_not_awaited()
    analyzer.analyze.assert_not_awaited()
    repository.save.assert_not_awaited()
