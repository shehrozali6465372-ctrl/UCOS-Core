"""HTTP boundary for Research Agent 01."""

import hmac
import os

from fastapi import APIRouter, Header, HTTPException

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


def _authenticate(authorization: str | None) -> None:
    expected = os.getenv("UCOS_RESEARCH_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="research authentication is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid bearer token")


@router.post("", response_model=ResearchResponse)
async def research(
    request: ResearchRequest,
    authorization: str | None = Header(default=None),
) -> ResearchResponse:
    _authenticate(authorization)
    if _service is None:
        raise HTTPException(status_code=503, detail="research service not configured")
    try:
        return await _service.execute(request)
    except ResearchForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
