from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ucos_core.agents.research import api as research_api
from ucos_core.agents.research.contracts import (
    EvidenceItem,
    ResearchRequest,
    ResearchResponse,
    ResearchTaskResponse,
)
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
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer inagent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 401


def test_api_fails_closed_when_token_scope_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_TENANT_ID", raising=False)
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("UCOS_RESEARCH_SCOPE_BRAND_ID", raising=False)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "research token scope is not configured"


def test_api_rejects_scope_mismatch_before_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-allowed")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 403
    service.execute.assert_not_awaited()


def test_api_accepts_only_configured_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
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
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 200
    service.execute.assert_awaited_once()


def test_api_returns_conflict_when_request_is_already_in_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.execute.side_effect = ResearchBusy("already processing")
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 409
    assert response.headers["retry-after"] == "5"


def test_api_returns_conflict_for_request_id_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.execute.side_effect = ResearchConflict("request ID reused")
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 409


def test_api_rejects_non_ascii_bearer_token_without_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers=[(b"Authorization", b"Bearer \xff")],
    )
    assert response.status_code == 401


def test_api_unicode_scope_mismatch_returns_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "agent01-test-token-0123456789-abcdef-0123456789")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-allowed")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    payload = request().model_dump()
    payload["tenant_id"] = "tenant-☃"
    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/agents/01/research",
        json=payload,
        headers={"Authorization": "Bearer agent01-test-token-0123456789-abcdef-0123456789"},
    )
    assert response.status_code == 403



@pytest.mark.asyncio
async def test_provider_failure_releases_claim_for_safe_retry() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    repo.claim.return_value = 17
    source.search.side_effect = RuntimeError("provider temporarily unavailable")

    with pytest.raises(ResearchUnavailable):
        await ResearchService(source, analyzer, auth, repo).execute(request())

    repo.release.assert_awaited_once_with(request(), 17)
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_failure_releases_only_current_claim() -> None:
    item = EvidenceItem(
        source="tavily", title="Report", url="https://example.com",
        excerpt="Evidence", retrieved_at="2026-01-01T00:00:00+00:00",
    )
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    repo.claim.return_value = 23
    source.search.return_value = [item]
    analyzer.analyze.return_value = "Finding [1]"
    repo.save.side_effect = RuntimeError("database temporarily unavailable")

    with pytest.raises(ResearchUnavailable):
        await ResearchService(source, analyzer, auth, repo).execute(request())

    repo.release.assert_awaited_once_with(request(), 23)


def test_api_rejects_low_entropy_token_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "short")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=request().model_dump(),
        headers={"Authorization": "Bearer short"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "research authentication is not configured safely"


def test_api_accepts_sufficient_length_token_and_exact_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "research-test-secret-value-with-more-than-32-characters"
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", token)
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
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200



@pytest.mark.asyncio
async def test_result_lookup_checks_authorization_before_reading() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = False
    service = ResearchService(source, analyzer, auth, repo)
    with pytest.raises(ResearchForbidden):
        await service.get_result("private-request", "t", "w", "b")
    repo.get_result.assert_not_awaited()


@pytest.mark.asyncio
async def test_result_lookup_fails_closed_when_repository_unavailable() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = True
    repo.get_result.side_effect = RuntimeError("database unavailable")
    service = ResearchService(source, analyzer, auth, repo)
    with pytest.raises(ResearchUnavailable):
        await service.get_result("request-1", "tenant-1", "workspace-1", "brand-1")


def test_api_get_result_returns_durable_task_status_for_configured_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "research-test-secret-value-with-more-than-32-characters"
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", token)
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.get_result.return_value = ResearchTaskResponse(
        request_id="req-1",
        correlation_id="corr-1",
        status="SUCCEEDED",
        analysis="Supported finding [1]",
        evidence=[
            EvidenceItem(
                source="tavily",
                title="Source",
                url="https://example.com",
                excerpt="Evidence",
                retrieved_at="2026-10-22T00:00:00Z",
            )
        ],
        created_at="2026-10-22T00:00:00Z",
    )
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).get(
        "/v1/agents/01/research/req-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCEEDED"
    assert payload["evidence"][0]["url"] == "https://example.com"
    service.get_result.assert_awaited_once_with(
        "req-1", "tenant-1", "workspace-1", "brand-1"
    )


def test_api_get_result_hides_missing_or_out_of_scope_request_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "research-test-secret-value-with-more-than-32-characters"
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", token)
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand-1")
    service = AsyncMock()
    service.get_result.return_value = None
    monkeypatch.setattr(research_api, "_service", service)
    response = TestClient(app).get(
        "/v1/agents/01/research/other-scope-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "research request not found"


def test_api_get_result_rejects_unauthenticated_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "research-test-secret-value-with-more-than-32-characters",
    )
    response = TestClient(app).get("/v1/agents/01/research/req-1")
    assert response.status_code == 401


def test_evidence_provenance_defaults_are_explicit_not_inferred() -> None:
    item = EvidenceItem(
        source="tavily",
        title="Research result",
        url="https://example.com/research",
        excerpt="Observed evidence",
        retrieved_at="2026-10-22T08:00:00+05:00",
    )
    assert item.published_at is None
    assert item.updated_at is None
    assert item.metric_value is None
    assert item.evidence_kind == "unknown"
    assert item.reliability == "unverified"
    assert item.freshness == "unknown"
    assert item.corroboration == "unknown"
    assert item.retrieved_at.isoformat() == "2026-10-22T03:00:00+00:00"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:password@example.com/report",
        "https://example.com/\nheader",
    ],
)
def test_evidence_rejects_non_http_or_credential_bearing_urls(url: str) -> None:
    with pytest.raises(ValueError):
        EvidenceItem(
            source="test",
            title="Unsafe source",
            url=url,
            excerpt="source text",
            retrieved_at="2026-10-22T00:00:00Z",
        )


def test_evidence_rejects_timezone_naive_timestamps() -> None:
    with pytest.raises(ValueError):
        EvidenceItem(
            source="test",
            title="Missing timezone",
            url="https://example.com",
            excerpt="source text",
            retrieved_at="2026-10-22T00:00:00",
        )


def test_evidence_accepts_known_metadata_without_claiming_sales() -> None:
    item = EvidenceItem(
        source="approved-provider",
        title="Trend report",
        url="https://example.com/trends",
        excerpt="The source reports 120 mentions.",
        retrieved_at="2026-10-22T00:00:00Z",
        published_at="2026-10-20T00:00:00Z",
        platform="youtube",
        region="US",
        metric_name="mentions",
        metric_value=120,
        metric_unit="count",
        evidence_kind="reported",
        reliability="medium",
        freshness="fresh",
        corroboration="single_source",
        limitations=["Provider metric definition has not been independently validated."],
    )
    assert item.metric_name == "mentions"
    assert item.metric_value == 120
    assert item.evidence_kind == "reported"
    assert any("not been independently validated" in note for note in item.limitations)


def test_capability_endpoint_requires_bearer_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "research-test-secret-value-with-more-than-32-characters",
    )
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "owner-project")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "private-workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "owner-brand")
    response = TestClient(app).get("/v1/agents/01/research/capabilities")
    assert response.status_code == 401


def test_capability_endpoint_reports_unintegrated_platforms_honestly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "research-test-secret-value-with-more-than-32-characters"
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", token)
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "owner-project")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "private-workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "owner-brand")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("ANALYSIS_API_KEY", "")
    response = TestClient(app).get(
        "/v1/agents/01/research/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    providers = {item["provider"]: item for item in payload["providers"]}
    assert payload["deployment_model"] == "single_owner"
    assert providers["tavily_general_web_search"]["status"] == "implemented"
    assert providers["tavily_general_web_search"]["credential_status"] == "missing"
    for platform in ("pinterest", "youtube", "facebook", "tiktok", "instagram"):
        assert providers[platform]["status"] == "not_integrated"
        assert providers[platform]["capabilities"] == []
    assert providers["product_affiliate_programs"]["status"] == "not_integrated"
