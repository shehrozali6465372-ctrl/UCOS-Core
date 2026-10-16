"""UCOS service entry point: Stage 0 guards and Agent 01 research API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from ucos_core.agents.research.api import configure_research_service, router
from ucos_core.agents.research.service import ResearchService
from ucos_core.dependencies import production_environment, required_dependencies_ready
from ucos_core.integrations.model_analysis import OpenAICompatibleAnalyzer
from ucos_core.integrations.tavily_research import TavilyResearchSource
from ucos_core.repositories.research_postgres import PostgresResearchRepository
from ucos_core.security.research_auth import PostgresResearchAuthorizer

configure_research_service(ResearchService(
    source=TavilyResearchSource(),
    analyzer=OpenAICompatibleAnalyzer(),
    authorizer=PostgresResearchAuthorizer(),
    repository=PostgresResearchRepository(),
))


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
app.include_router(router)


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
