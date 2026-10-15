"""UCOS Stage 0 service: startup guard plus liveness/readiness endpoints."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from ucos_core.dependencies import production_environment, required_dependencies_ready


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
