# UCOS-Core

Universal Content Operating System core repository. Implementation follows the frozen UCOS architecture baseline v1.2; CI passing is necessary but does not certify production conformance.

## Stage 0 safety baseline

Fail-closed publication guards cover offline drafts, staging requests targeting production accounts, and TikTok production visibility. Ambiguous provider outcomes remain `OUTCOME_UNKNOWN` and require reconciliation rather than blind retry.

## Agent 01 — Research and Analysis

Agent 01 accepts a scoped research request, retrieves source evidence through Tavily, produces evidence-grounded analysis through an OpenAI-compatible chat-completions endpoint, and durably stores the result and provenance in PostgreSQL before returning success. It does not publish content or mutate platform accounts. Authorization and persistence failures fail closed. Responses distinguish `SUCCEEDED` from `NO_RESULTS`; provider/persistence failures return HTTP 503, and unauthorized scopes return HTTP 403.

### Required configuration

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: required by existing production readiness gate
- `UCOS_RESEARCH_API_TOKEN`: bearer token for this Agent 01 service instance
- `UCOS_RESEARCH_SCOPE_TENANT_ID`, `UCOS_RESEARCH_SCOPE_WORKSPACE_ID`, `UCOS_RESEARCH_SCOPE_BRAND_ID`: the one tenant/workspace/brand scope permitted for that token
- `TAVILY_API_KEY`: Tavily search credential
- `ANALYSIS_API_KEY`: key for the configured OpenAI-compatible model endpoint
- `ANALYSIS_BASE_URL`: defaults to `https://api.openai.com/v1`
- `ANALYSIS_MODEL`: defaults to `gpt-4.1-mini`
- `UCOS_ENV=production` for production startup checks

The three `UCOS_RESEARCH_SCOPE_*` values must be sourced from the approved tenant/workspace/brand authority; do not invent them. The API fails closed with HTTP 503 if any are missing and returns HTTP 403 if a request asks for a different scope. This is a single configured scope per service token, not multi-tenant identity federation. Never commit secrets. See `.env.example` for variable names only.

### Database setup

Apply `migrations/001_agent01_research.sql` to the configured PostgreSQL database before enabling the endpoint. Seed `ucos_research_scope_grants` only through your approved identity/tenant administration workflow; this table is an authorization grant boundary, not an automatic grant. The configured scope must also have an enabled row in that table. In a production deployment, migrations should be applied by a controlled migration job, not silently by app startup.

### API

`POST /v1/agents/01/research`

The request requires request/correlation IDs, tenant/workspace/brand scope, workflow and workflow-step IDs, a query, and an optional result limit. The HTTP boundary first authenticates the bearer token and restricts the request to that token's configured single scope; the database authorizer then checks the exact enabled grant. The service preserves source URL, title, excerpt, provider and retrieval timestamp. Success is never returned unless the result has been persisted.

### Local verification

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
python -m ucos_core.preflight
```

The CI workflow additionally builds the container. Actual production readiness still requires real database/cache/provider credentials, a migrated database, valid tenant grants, deployment configuration, and live end-to-end verification.
