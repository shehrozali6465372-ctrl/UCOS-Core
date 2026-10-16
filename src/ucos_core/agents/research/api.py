"""HTTP boundary for Research Agent 01."""

from fastapi import APIRouter, HTTPException

from ucos_core.agents.research.contracts import ResearchRequest, ResearchResponse
from ucos_core.agents.research.service import (
    ResearchForbidden,
    ResearchService,
    ResearchUnavailable,
)

router = APIRouter(prefix="/v1/agents/01/research", tags=["agent-01"])
_service: ResearchService | None = None


def configure_research_service(service: ResearchService) -> None:
    global _service
    _service = service


@router.post("", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    if _service is None:
        raise HTTPException(status_code=503, detail="research service not configured")
    try:
        return await _service.execute(request)
    except ResearchForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
