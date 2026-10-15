# UCOS-Core

Universal Content Operating System core repository.

Implementation follows the frozen UCOS architecture baseline v1.2. The architecture freezes contracts and target behavior; successful compilation or CI alone does not certify production conformance.

## Stage 0: P0 safety baseline

This initial implementation establishes fail-closed publication guards for offline drafts, staging requests targeting production accounts, and TikTok production visibility. Ambiguous provider outcomes remain `OUTCOME_UNKNOWN` and require reconciliation rather than blind retry.

The service exposes `/health/live` and `/health/ready`. PostgreSQL (`DATABASE_URL`) and Redis (`REDIS_URL`) are required for production startup and readiness. Missing or unavailable dependencies prevent production startup. Development/test use may run without production dependencies, but readiness will remain false.

## Local development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
uvicorn ucos_core.main:app --reload
```

## Production environment

Set `UCOS_ENV=production`, `DATABASE_URL`, and `REDIS_URL`. Do not place credentials in source control. The container preflight and application lifespan both fail closed if required dependencies cannot be reached.

## Evidence status

CI results and production certification are reported only from observed workflow/evidence. This repository is not production-certified merely because these tests pass.
