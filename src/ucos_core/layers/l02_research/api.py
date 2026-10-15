"""HTTP boundary for Agent 01 (L02 Research), wired through L17/L13/L11 ports."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from ucos_core.layers.l02_research.contracts import ResearchRequest, ResearchResult
from ucos_core.layers.l02_research.ports import (
    AuthenticationRejected,
    DependencyUnavailable,
    ResearchAuthorizationPort,
)
from ucos_core.layers.l02_research.service import ResearchService


def build_research_router(
    *,
    service: ResearchService,
    authorizer: ResearchAuthorizationPort,
) -> APIRouter:
    router = APIRouter(prefix="/v1/research", tags=["L02 Research"])

    @router.post("", response_model=ResearchResult)
    async def research(
        payload: ResearchRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ResearchResult:
        try:
            await authorizer.authorize(authorization, payload)
            return await service.run(payload)
        except AuthenticationRejected as error:
            raise HTTPException(status_code=401, detail="research authorization rejected") from error
        except DependencyUnavailable as error:
            raise HTTPException(status_code=503, detail="required UCOS adapter unavailable") from error

    return router
