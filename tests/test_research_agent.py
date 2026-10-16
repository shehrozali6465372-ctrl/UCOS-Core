from unittest.mock import AsyncMock

import pytest

from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest
from ucos_core.agents.research.service import (
    ResearchForbidden,
    ResearchService,
    ResearchUnavailable,
)


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
    service = ResearchService(source, analyzer, auth, repo)
    result = await service.execute(request())
    assert result.status == "SUCCEEDED"
    assert result.evidence == [item]
    assert result.persisted is True
    repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_denies_unauthorized_scope_before_search() -> None:
    source, analyzer, auth, repo = (AsyncMock() for _ in range(4))
    auth.authorize.return_value = False
    service = ResearchService(source, analyzer, auth, repo)
    with pytest.raises(ResearchForbidden):
        await service.execute(request())
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
