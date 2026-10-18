"""PostgreSQL integration tests for durable Agent 01 idempotency.

CI supplies TEST_DATABASE_URL pointing at an ephemeral PostgreSQL service.
These tests never target the application's DATABASE_URL.
"""

import os
import pathlib
import uuid

import psycopg
import pytest


DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not configured")


@pytest.fixture(scope="module", autouse=True)
def migrated_database():
    assert DATABASE_URL
    root = pathlib.Path(__file__).resolve().parents[1]
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        for migration in sorted((root / "migrations").glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
    yield
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS ucos_scope_provisioning_audit CASCADE")
        conn.execute("DROP TABLE IF EXISTS ucos_research_runs CASCADE")
        conn.execute("DROP TABLE IF EXISTS ucos_research_scope_grants CASCADE")


@pytest.fixture
def repository(monkeypatch):
    from ucos_core.repositories.research_postgres import PostgresResearchRepository

    assert DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    return PostgresResearchRepository()


def request(request_id=None):
    from ucos_core.agents.research.contracts import ResearchRequest

    return ResearchRequest(
        request_id=request_id or str(uuid.uuid4()),
        correlation_id="integration-correlation",
        tenant_id="integration-tenant",
        workspace_id="integration-workspace",
        brand_id="integration-brand",
        workflow_id="integration-workflow",
        workflow_step_id="integration-step",
        query="integration test query",
        max_results=3,
    )


@pytest.mark.asyncio
async def test_claim_persists_then_replays_completed_result(repository):
    req = request()
    generation = await repository.claim(req)
    assert isinstance(generation, int)
    await repository.save(req, generation, "SUCCEEDED", "persisted analysis", [])

    replay = await repository.claim(req)
    assert replay.status == "SUCCEEDED"
    assert replay.analysis == "persisted analysis"
    assert replay.persisted is True


@pytest.mark.asyncio
async def test_request_id_metadata_mismatch_is_rejected(repository):
    from ucos_core.repositories.research_postgres import ResearchIdempotencyConflict

    req = request()
    await repository.claim(req)
    changed = req.model_copy(update={"query": "different query"})
    with pytest.raises(ResearchIdempotencyConflict):
        await repository.claim(changed)


@pytest.mark.asyncio
async def test_live_duplicate_is_rejected_and_expired_claim_is_fenced(repository):
    from ucos_core.repositories.research_postgres import (
        ResearchIdempotencyConflict,
        ResearchRequestInProgress,
    )

    req = request()
    first_generation = await repository.claim(req)
    with pytest.raises(ResearchRequestInProgress):
        await repository.claim(req)

    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        await conn.execute(
            "UPDATE ucos_research_runs SET claim_expires_at = now() - interval '1 second' "
            "WHERE request_id = %s",
            (req.request_id,),
        )

    second_generation = await repository.claim(req)
    assert second_generation > first_generation
    with pytest.raises(ResearchIdempotencyConflict):
        await repository.save(req, first_generation, "SUCCEEDED", "stale", [])
    await repository.save(req, second_generation, "NO_RESULTS", "", [])
    replay = await repository.claim(req)
    assert replay.status == "NO_RESULTS"
