"""Regression tests for strict bearer token formatting."""

from fastapi.testclient import TestClient

from ucos_core.main import app


def _payload() -> dict[str, str | int]:
    return {
        "request_id": "auth-format-1",
        "correlation_id": "auth-format-corr",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "brand_id": "brand-1",
        "workflow_id": "workflow-1",
        "workflow_step_id": "step-1",
        "query": "safe research query",
        "max_results": 3,
    }


def test_api_rejects_whitespace_padded_bearer_token(monkeypatch):
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=_payload(),
        headers={"Authorization": "Bearer  correct-secret"},
    )
    assert response.status_code == 401


def test_api_rejects_tab_separated_bearer_scheme(monkeypatch):
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=_payload(),
        headers={"Authorization": "Bearer\tcorrect-secret"},
    )
    assert response.status_code == 401


def test_api_rejects_token_with_trailing_whitespace(monkeypatch):
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "correct-secret")
    response = TestClient(app).post(
        "/v1/agents/01/research",
        json=_payload(),
        headers={"Authorization": "Bearer correct-secret "},
    )
    assert response.status_code == 401
