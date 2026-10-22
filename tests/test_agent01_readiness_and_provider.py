"""Boundary tests for readiness gates and provider response validation."""

import json
from unittest.mock import patch

import httpx
import pytest

from ucos_core.dependencies import ProbeResult, required_dependencies_ready
from ucos_core.integrations.tavily_research import TavilyResearchSource


def test_readiness_requires_provider_credentials_and_granted_scope(monkeypatch):
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "agent01-test-token-0123456789-abcdef-0123456789",
    )
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test")
    monkeypatch.setenv("ANALYSIS_API_KEY", "model-test")
    monkeypatch.setenv("ANALYSIS_MODEL", "test-model")
    with (
        patch("ucos_core.dependencies.probe_postgres", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_redis", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_scope", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_schema", return_value=ProbeResult(True, True)),
    ):
        ready, components = required_dependencies_ready()
    assert ready is True
    assert all(components.values())


def test_readiness_fails_when_scope_grant_is_missing(monkeypatch):
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "agent01-test-token-0123456789-abcdef-0123456789",
    )
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test")
    monkeypatch.setenv("ANALYSIS_API_KEY", "model-test")
    with (
        patch("ucos_core.dependencies.probe_postgres", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_redis", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_scope", return_value=ProbeResult(True, False)),
        patch("ucos_core.dependencies.probe_research_schema", return_value=ProbeResult(True, True)),
    ):
        ready, components = required_dependencies_ready()
    assert ready is False
    assert components["research_scope"] is False


@pytest.mark.asyncio
async def test_tavily_adapter_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY is not configured"):
        await TavilyResearchSource().search("a research query", 3)


def test_model_adapter_rejects_insecure_remote_endpoint(monkeypatch):
    from ucos_core.integrations.model_analysis import OpenAICompatibleAnalyzer

    monkeypatch.setenv("ANALYSIS_BASE_URL", "http://external.example/v1")
    with pytest.raises(RuntimeError, match="must be HTTPS"):
        OpenAICompatibleAnalyzer()


def test_model_adapter_rejects_endpoint_with_embedded_credentials(monkeypatch):
    from ucos_core.integrations.model_analysis import OpenAICompatibleAnalyzer

    monkeypatch.setenv("ANALYSIS_BASE_URL", "https://user:pass@example.com/v1")
    with pytest.raises(RuntimeError, match="must be HTTPS"):
        OpenAICompatibleAnalyzer()


@pytest.mark.asyncio
async def test_tavily_filters_malformed_and_credential_bearing_urls(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "ftp://example.com/path", "title": "bad", "content": "x"},
                    {"url": "https://user:pass@example.com/path", "title": "bad", "content": "x"},
                    {"url": "https://example.com/good", "title": "good", "content": "safe"},
                ]
            },
        )

    original_client = httpx.AsyncClient
    with patch(
        "ucos_core.integrations.tavily_research.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    ):
        evidence = await TavilyResearchSource().search("query", 5)

    assert len(evidence) == 1
    assert evidence[0].url == "https://example.com/good"


@pytest.mark.asyncio
async def test_model_adapter_bounds_completion_and_requests_token_limit(monkeypatch):
    from ucos_core.agents.research.contracts import EvidenceItem
    from ucos_core.integrations.model_analysis import OpenAICompatibleAnalyzer

    monkeypatch.setenv("ANALYSIS_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("ANALYSIS_API_KEY", "test-key")
    monkeypatch.setenv("ANALYSIS_MODEL", "test-model")
    captured = {}

    async def handler(request):
        captured["payload"] = await request.aread()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "x" * 20_001}}]},
        )

    original_client = httpx.AsyncClient
    with patch(
        "ucos_core.integrations.model_analysis.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    ):
        item = EvidenceItem(
            source="tavily",
            title="Source",
            url="https://example.com/source",
            excerpt="Evidence",
            retrieved_at="2026-01-01T00:00:00+00:00",
        )
        with pytest.raises(RuntimeError, match="response size limit"):
            await OpenAICompatibleAnalyzer().analyze("question", [item])

    assert json.loads(captured["payload"])["max_tokens"] == 3000



@pytest.mark.parametrize(
    "analysis_url",
    [
        "http://external.example/v1",
        "https://user:password@example.com/v1",
        "https://example.com/v1?token=unsafe",
        "https://example.com/v1#fragment",
    ],
)
def test_readiness_fails_closed_for_unsafe_analysis_endpoint(
    monkeypatch, analysis_url
):
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "agent01-test-token-0123456789-abcdef-0123456789",
    )
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test")
    monkeypatch.setenv("ANALYSIS_API_KEY", "model-test")
    monkeypatch.setenv("ANALYSIS_MODEL", "test-model")
    monkeypatch.setenv("ANALYSIS_BASE_URL", analysis_url)
    with (
        patch("ucos_core.dependencies.probe_postgres", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_redis", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_scope", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_schema", return_value=ProbeResult(True, True)),
    ):
        ready, components = required_dependencies_ready()
    assert ready is False
    assert components["analysis_model"] is False


def test_readiness_accepts_https_analysis_endpoint(monkeypatch):
    monkeypatch.setenv(
        "UCOS_RESEARCH_API_TOKEN",
        "agent01-test-token-0123456789-abcdef-0123456789",
    )
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test")
    monkeypatch.setenv("ANALYSIS_API_KEY", "model-test")
    monkeypatch.setenv("ANALYSIS_MODEL", "test-model")
    monkeypatch.setenv("ANALYSIS_BASE_URL", "https://analysis.example/v1")
    with (
        patch("ucos_core.dependencies.probe_postgres", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_redis", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_scope", return_value=ProbeResult(True, True)),
        patch("ucos_core.dependencies.probe_research_schema", return_value=ProbeResult(True, True)),
    ):
        ready, components = required_dependencies_ready()
    assert ready is True
    assert components["analysis_model"] is True
