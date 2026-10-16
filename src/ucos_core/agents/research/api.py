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


def _authorize_configured_scope(request: ResearchRequest) -> None:
    """Bind this service token to one explicitly configured tenant/workspace/brand scope."""
    names = (
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
    )
    configured = tuple(os.getenv(name, "").strip() for name in names)
    if not all(configured):
        raise HTTPException(
            status_code=503,
            detail="research token scope is not configured",
        )
    requested = (request.tenant_id, request.workspace_id, request.brand_id)
    matches = (
        hmac.compare_digest(actual, expected)
        for actual, expected in zip(requested, configured, strict=True)
    )
    if not all(matches):
        raise HTTPException(status_code=403, detail="request is outside configured token scope")


@router.post("", response_model=ResearchResponse)
async def research(
    request: ResearchRequest,
    authorization: str | None = Header(default=None),
) -> ResearchResponse:
    _authenticate(authorization)
    _authorize_configured_scope(request)
    if _service is None:
        raise HTTPException(status_code=503, detail="research service not configured")
    try:
        return await _service.execute(request)
    except ResearchForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
