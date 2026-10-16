from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ucos_core.agents.research.api import configure_research_service
from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest
from ucos_core.agents.research.service import (
    ResearchForbidden,
    ResearchService,
    ResearchUnavailable,
)
from ucos_core.main import app


def request() -> ResearchRequest:
    return ResearchRequest(
        request_id="req-1", correlation_id="corr-1", tenant_id="tenant-1",
        workspace_id="workspace-1", brand_id="brand-1", workflow_id="wf-1",
        workflow_step_id="step-1", query="market trends", max_results=3,
    )


@pytest.mark.asyncio
async def test_research_persists_provenance_before_success() -> None:
    item = EvidenceItem(source="tavily", title="Report", url="https://example.com",
                       excerpt="Evidence", retrieved_at="2026-01-01T00:00:00+00:00")
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    source.search.return_value = [item]
    analyzer.analyze.return_value = "Finding [1]"
    result = await ResearchService(source, analyzer, auth, repo).execute(request())
    assert result.status == "SUCCEEDED"
    assert result.evidence == [item]
    assert result.persisted is True
    repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_denies_unauthorized_scope_before_search() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = False
    with pytest.raises(ResearchForbidden):
        await ResearchService(source, analyzer, auth, repo).execute(request())
    source.search.assert_not_awaited()
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_failure_never_returns_success() -> None:
    item = EvidenceItem(source="tavily", title="Report", url="https://example.com",
                       excerpt="Evidence", retrieved_at="2026-01-01T00:00:00+00:00")
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    source.search.return_value = [item]
    analyzer.analyze.return_value = "Finding [1]"
    repo.save.side_effect = RuntimeError("db down")
    with pytest.raises(ResearchUnavailable):
        await ResearchService(source, analyzer, auth, repo).execute(request())


@pytest.mark.asyncio
async def test_provider_failure_fails_closed() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    source.search.side_effect = RuntimeError("provider down")
    with pytest.raises(ResearchUnavailable):
        await ResearchService(source, analyzer, auth, repo).execute(request())
    repo.save.assert_not_awaited()


def test_api_rejects_missing_token_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UCOS_RESEARCH_API_TOKEN", raising=False)
    response = TestClient(app).post("/v1/agents/01/research", json=request().model_dump())
    assert response.status_code == 503


def test_api_rejects_invalid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer incorrect-secret"},
    )
    assert response.status_code == 401
