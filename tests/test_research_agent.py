from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ucos_core.layers.l02_research.api import build_research_router
from ucos_core.layers.l02_research.contracts import (
    ResearchRequest,
    ResearchSourceObservation,
    ResearchStatus,
)
from ucos_core.layers.l02_research.ports import (
    AuthenticationRejected,
    DependencyUnavailable,
    ResearchProviderError,
)
from ucos_core.layers.l02_research.service import ResearchService
from ucos_core.layers.l11_integrations.tavily import TavilyResearchAdapter


class FakeSource:
    def __init__(self, observations=None, error=None):
        self.observations = observations or []
        self.error = error
        self.called = False

    async def search(self, query, *, max_results):
        self.called = True
        if self.error:
            raise self.error
        return self.observations[:max_results]


class FakeRepository:
    def __init__(self, ready=True):
        self.ready = ready
        self.saved = []

    async def ensure_ready(self):
        if not self.ready:
            raise DependencyUnavailable("L13 persistence unavailable")

    async def save(self, result):
        self.saved.append(result)


class FakeAuthorizer:
    def __init__(self, rejected=False):
        self.rejected = rejected
        self.called = False

    async def authorize(self, authorization, context):
        self.called = True
        if self.rejected or authorization != "Bearer test-token":
            raise AuthenticationRejected("not authorized")


def request_payload(**overrides):
    values = {
        "workflow_id": "workflow-1",
        "workflow_step_id": "step-research-1",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "brand_id": "brand-1",
        "account_id": "account-1",
        "platform": "youtube",
        "platform_account_id": "youtube-account-1",
        "request_id": "request-1",
        "correlation_id": "correlation-1",
        "query": "How do small creators improve video retention?",
        "max_results": 3,
    }
    values.update(overrides)
    return ResearchRequest(**values)


def observation():
    return ResearchSourceObservation(
        source_id="source-1",
        provider="test-source",
        url="https://example.com/retention",
        title="Video retention guide",
        snippet="A grounded source-provided summary.",
        observed_at=datetime.now(UTC),
        source_timestamp=None,
        confidence=0.8,
    )


def make_client(source=None, repository=None, authorizer=None):
    source = source or FakeSource([observation()])
    repository = repository or FakeRepository()
    authorizer = authorizer or FakeAuthorizer()
    app = FastAPI()
    app.include_router(
        build_research_router(
            service=ResearchService(source=source, repository=repository),
            authorizer=authorizer,
        )
    )
    return TestClient(app), source, repository, authorizer


def test_research_endpoint_returns_provenance_and_persists_result():
    client, source, repository, authorizer = make_client()
    response = client.post(
        "/v1/research",
        headers={"Authorization": "Bearer test-token"},
        json=request_payload().model_dump(mode="json"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ResearchStatus.SUCCEEDED.value
    assert body["schema_version"] == "1.0.0"
    assert body["provenance"][0]["url"] == "https://example.com/retention"
    assert body["tenant_id"] == "tenant-1"
    assert source.called
    assert len(repository.saved) == 1
    assert authorizer.called


def test_empty_search_is_explicit_no_results_not_fabricated_findings():
    client, _, repository, _ = make_client(source=FakeSource([]))
    response = client.post(
        "/v1/research",
        headers={"Authorization": "Bearer test-token"},
        json=request_payload().model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == ResearchStatus.NO_RESULTS.value
    assert response.json()["provenance"] == []
    assert len(repository.saved) == 1


def test_authentication_rejection_prevents_provider_call():
    client, source, _, _ = make_client(authorizer=FakeAuthorizer(rejected=True))
    response = client.post(
        "/v1/research",
        headers={"Authorization": "Bearer wrong-token"},
        json=request_payload().model_dump(mode="json"),
    )
    assert response.status_code == 401
    assert not source.called


def test_missing_l13_persistence_prevents_provider_call():
    client, source, _, _ = make_client(repository=FakeRepository(ready=False))
    response = client.post(
        "/v1/research",
        headers={"Authorization": "Bearer test-token"},
        json=request_payload().model_dump(mode="json"),
    )
    assert response.status_code == 503
    assert not source.called


def test_provider_error_is_recorded_as_explicit_failed_result():
    client, _, repository, _ = make_client(
        source=FakeSource(error=ResearchProviderError("SOURCE_TIMEOUT", retryable=True))
    )
    response = client.post(
        "/v1/research",
        headers={"Authorization": "Bearer test-token"},
        json=request_payload().model_dump(mode="json"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ResearchStatus.FAILED.value
    assert body["error_code"] == "SOURCE_TIMEOUT"
    assert body["retryable"] is True
    assert len(repository.saved) == 1


def test_tavily_adapter_requires_credentials_and_normalizes_provenance():
    adapter = TavilyResearchAdapter(api_key="")
    import asyncio

    try:
        asyncio.run(adapter.search("some query", max_results=1))
    except DependencyUnavailable as error:
        assert "credentials" in str(error)
    else:
        raise AssertionError("expected fail-closed behavior without provider credentials")

    normalized = TavilyResearchAdapter._normalize(
        {
            "url": "https://example.com/story",
            "title": "Example source",
            "content": "Source-provided excerpt.",
            "published_date": "2025-04-01T12:00:00Z",
            "score": 0.7,
        }
    )
    assert normalized.provider == "tavily"
    assert normalized.source_timestamp == datetime(2025, 4, 1, 12, 0, tzinfo=UTC)
    assert len(normalized.source_id) == 64
