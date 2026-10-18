from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ucos_core.agents.research import api as research_api
from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest, ResearchResponse
from ucos_core.agents.research.service import (
    ResearchBusy,
    ResearchConflict,
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
    repo.claim.return_value = 1
    source.search.return_value = [item]
    analyzer.analyze.return_value = "Finding [1]"
    result = await ResearchService(source, analyzer, auth, repo).execute(request())
    assert result.status == "SUCCEEDED"
    assert result.evidence == [item]
    assert result.persisted is True
    repo.claim.assert_awaited_once_with(request())
    repo.save.assert_awaited_once_with(request(), 1, "SUCCEEDED", "Finding [1]", [item])


@pytest.mark.asyncio
async def test_research_denies_unauthorized_scope_before_search() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = False
    with pytest.raises(ResearchForbidden):
        await ResearchService(source, analyzer, auth, repo).execute(request())
    source.search.assert_not_awaited()
    repo.claim.assert_not_awaited()
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_failure_never_returns_success() -> None:
    item = EvidenceItem(source="tavily", title="Report", url="https://example.com",
                       excerpt="Evidence", retrieved_at="2026-01-01T00:00:00+00:00")
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    repo.claim.return_value = 1
    source.search.return_value = [item]
    analyzer.analyze.return_value = "Finding [1]"
    repo.save.side_effect = RuntimeError("db down")
    with pytest.raises(ResearchUnavailable):
        await ResearchService(source, analyzer, auth, repo).execute(request())


@pytest.mark.asyncio
async def test_provider_failure_fails_closed() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    repo.claim.return_value = 1
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


def test_api_fails_closed_when_token_scope_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_TENANT_ID", raising=False)
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_BRAND_ID", raising=False)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "research token scope is not configured"


def test_api_rejects_scope_mismatch_before_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-allowed")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert response.status_code == 403
    service.execute.assert_not_awaited()


def test_api_accepts_only_configured_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.execute.return_value = ResearchResponse(
        request_id="req-1", correlation_id="corr-1", status="NO_RESULTS",
        analysis="", evidence=[], persisted=True,
    )
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert response.status_code == 200
    service.execute.assert_awaited_once()


def test_api_returns_conflict_when_request_is_already_in_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.execute.side_effect = ResearchBusy("already processing")
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert response.status_code == 409


def test_api_returns_conflict_for_request_id_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.execute.side_effect = ResearchConflict("request ID reused")
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert response.status_code == 409
