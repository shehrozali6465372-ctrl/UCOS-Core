"""UCOS service entry point with Stage 0 health and fail-closed L02 route."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from ucos_core.dependencies import production_environment, required_dependencies_ready
from ucos_core.layers.l02_research.api import build_research_router
from ucos_core.layers.l02_research.contracts import ResearchRequest
from ucos_core.layers.l02_research.ports import DependencyUnavailable
from ucos_core.layers.l02_research.service import ResearchService
from ucos_core.layers.l11_integrations.tavily import TavilyResearchAdapter


class _UnconfiguredResearchAuthorizer:
    async def authorize(self, authorization: str | None, context: ResearchRequest) -> None:
        del authorization, context
        raise DependencyUnavailable("L17 authorization adapter is not configured")


class _UnconfiguredResearchRepository:
    async def ensure_ready(self) -> None:
        raise DependencyUnavailable("L13 PostgreSQL repository adapter is not configured")

    async def save(self, result) -> None:
        del result
        raise DependencyUnavailable("L13 PostgreSQL repository adapter is not configured")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if production_environment():
        ready, components = required_dependencies_ready()
        if not ready:
            unavailable = ", ".join(name for name, ok in components.items() if not ok)
            raise RuntimeError(
                "production startup blocked: required dependency unavailable: "
                f"{unavailable}"
            )
    yield


app = FastAPI(title="UCOS Core", version="0.1.0", lifespan=lifespan)
_research_service = ResearchService(
    source=TavilyResearchAdapter(),
    repository=_UnconfiguredResearchRepository(),
)
app.include_router(
    build_research_router(
        service=_research_service,
        authorizer=_UnconfiguredResearchAuthorizer(),
    )
)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, object]:
    ready, components = required_dependencies_ready()
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "dependencies": components},
        )
    return {"status": "ready", "dependencies": components}
