"""Regression tests for durable Agent 01 idempotency replay."""

from unittest.mock import AsyncMock

import pytest

from ucos_core.agents.research.contracts import ResearchRequest, ResearchResponse
from ucos_core.agents.research.service import ResearchConflict, ResearchService
from ucos_core.repositories.research_postgres import ResearchIdempotencyConflict


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
    repository.get_existing.side_effect = ResearchIdempotencyConflict("input mismatch")

    with pytest.raises(ResearchConflict):
        await ResearchService(source, analyzer, authorizer, repository).execute(request)

    source.search.assert_not_awaited()
    analyzer.analyze.assert_not_awaited()
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_postgres_repository_replays_matching_row_and_compares_max_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from ucos_core.repositories import research_postgres

    request = make_request()
    row = (
        request.correlation_id,
        request.tenant_id,
        request.workspace_id,
        request.brand_id,
        request.workflow_id,
        request.workflow_step_id,
        request.query,
        request.max_results,
        "SUCCEEDED",
        "Persisted analysis",
        json.dumps([]),
    )

    class Cursor:
        async def fetchone(self):
            return row

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args):
            return Cursor()

    async def connect(*_args, **_kwargs):
        return Connection()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(research_postgres.psycopg.AsyncConnection, "connect", connect)
    repository = research_postgres.PostgresResearchRepository()

    replay = await repository.get_existing(request)
    assert replay is not None
    assert replay.analysis == "Persisted analysis"
    assert replay.persisted is True

    with pytest.raises(research_postgres.ResearchIdempotencyConflict):
        await repository.get_existing(request.model_copy(update={"max_results": 4}))


@pytest.mark.asyncio
async def test_postgres_repository_reports_concurrent_duplicate_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ucos_core.repositories import research_postgres

    class Cursor:
        async def fetchone(self):
            return None

    class Connection:
        committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args):
            return Cursor()

        async def commit(self):
            self.committed = True

    connection = Connection()

    async def connect(*_args, **_kwargs):
        return connection

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(research_postgres.psycopg.AsyncConnection, "connect", connect)
    repository = research_postgres.PostgresResearchRepository()

    with pytest.raises(research_postgres.ResearchIdempotencyConflict):
        await repository.save(make_request(), "NO_RESULTS", "", [])

    assert connection.committed is True
