"tests for Tavily API credential transport and failure handling."

from unittest.mock import patch

import httpx
import pytest

from ucos_core.integrations.tavily_research import TavilyResearchSource


@pytest.mark.asyncio
async def test_tavily_api_key_is_sent_in_authorization_header_not_json(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-secret-key")
    observed = {}

    async def handler(request):
        observed["authorization"] = request.headers.get("authorization")
        observed["json"] = await request.aread()
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/source",
                        "title": "Example",
                        "content": "Evidence",
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient
    with patch(
        "ucos_core.integrations.tavily_research.httpx.AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    ):
        results = await TavilyResearchSource().search("safe query", 3)

    assert observed["authorization"] == "Bearer test-secret-key"
    assert b"test-secret-key" not in observed["json"]
    assert len(results) == 1
    assert results[0].source == "tavily"


@pytest.mark.asyncio
async def test_tavily_api_error_raises_without_returning_provider_body(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-secret-key")

    async def handler(_request):
        return httpx.Response(
            401,
            json={"error": "invalid api key", "token": "do-not-echo"},
        )

    original_client = httpx.AsyncClient
    with patch(
        "ucos_core.integrations.tavily_research.httpx.AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await TavilyResearchSource().search("safe query", 3)
