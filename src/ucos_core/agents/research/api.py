"""HTTP boundary for Research Agent 01."""

import hmac
import os
import secrets

from fastapi import APIRouter, Header, HTTPException, Path

from ucos_core.agents.research.contracts import (
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

router = APIRouter(prefix="/v1/agents/01/research", tags=["agent-01"])
_service: ResearchService | None = None


def _constant_time_equal(actual: str, expected: str) -> bool:
    """Compare UTF-8 bytes so arbitrary Unicode input fails closed, not with TypeError."""
    return hmac.compare_digest(actual.encode("utf-8"), expected.encode("utf-8"))


def configure_research_service(service: ResearchService) -> None:
    global _service
    _service = service


def _authenticate(authorization: str | None) -> None:
    expected = os.getenv("UCOS_RESEARCH_API_TOKEN", "").strip()
    # Enforce a minimum configured token length. Length alone does not prove
    # entropy; operators must generate the value with a cryptographic RNG.
    if len(expected) < 32:
        raise HTTPException(
            status_code=503,
            detail="research authentication is not configured safely",
        )
    scheme, separator, token = (authorization or "").partition(" ")
    # HTTP authentication uses one scheme/token separator; reject empty or
    # whitespace-padded credentials instead of accepting accidental formatting.
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not token
        or token != token.strip()
        or not secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise HTTPException(status_code=401, detail="invalid bearer token")


def _configured_scope() -> tuple[str, str, str]:
    names = (
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
    )
    configured = tuple(os.getenv(name, "").strip() for name in names)
    if not all(configured):
        raise HTTPException(status_code=503, detail="research token scope is not configured")
    return configured  # type: ignore[return-value]


def _authorize_configured_scope(request: ResearchRequest) -> None:
    """Bind this service token to one explicitly configured project scope."""
    requested = (request.tenant_id, request.workspace_id, request.brand_id)
    configured = _configured_scope()
    matches = (
        _constant_time_equal(actual, expected)
        for actual, expected in zip(requested, configured, strict=True)
    )
    if not all(matches):
        raise HTTPException(status_code=403, detail="request is outside configured project scope")


@router.get("/{request_id}", response_model=ResearchTaskResponse)
async def get_research_result(
    request_id: str = Path(min_length=1, max_length=128),
    authorization: str | None = Header(default=None),
) -> ResearchTaskResponse:
    """Poll/read a durable result, restricted to the configured single-project scope."""
    _authenticate(authorization)
    tenant_id, workspace_id, brand_id = _configured_scope()
    if _service is None:
        raise HTTPException(status_code=503, detail="research service not configured")
    try:
        result = await _service.get_result(
            request_id, tenant_id, workspace_id, brand_id
        )
    except ResearchForbidden as exc:
        raise HTTPException(status_code=403, detail="project scope is not authorized") from exc
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        # Do not reveal whether another scope owns this request ID.
        raise HTTPException(status_code=404, detail="research request not found")
    return result


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
    except ResearchConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResearchBusy as exc:
        raise HTTPException(
            status_code=409, detail=str(exc), headers={"Retry-After": "5"}
        ) from exc
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
