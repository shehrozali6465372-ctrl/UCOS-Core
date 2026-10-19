# UCOS-Core

Universal Content Operating System core repository. Implementation follows the frozen UCOS architecture baseline v1.2; CI passing is necessary but does not certify production conformance.

## Stage 0 safety baseline

Fail-closed publication guards cover offline drafts, staging requests targeting production accounts, and TikTok production visibility. Ambiguous provider outcomes remain `OUTCOME_UNKNOWN` and require reconciliation rather than blind retry.

## Agent 01 — Research and Analysis

Agent 01 accepts a scoped research request, retrieves source evidence through Tavily, produces evidence-grounded analysis through an OpenAI-compatible chat-completions endpoint, and durably stores the result and provenance in PostgreSQL before returning success. It does not publish content or mutate platform accounts. Authorization and persistence failures fail closed. Responses distinguish `SUCCEEDED` from `NO_RESULTS`; provider/persistence failures return HTTP 503, unauthorized scopes return HTTP 403, and reuse of a request ID with different request metadata returns HTTP 409.

### Required configuration

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: required by existing production readiness gate
- `UCOS_RESEARCH_API_TOKEN`: bearer token for this Agent 01 service instance
- `UCOS_RESEARCH_SCOPE_TENANT_ID`, `UCOS_RESEARCH_SCOPE_WORKSPACE_ID`, `UCOS_RESEARCH_SCOPE_BRAND_ID`: the one tenant/workspace/brand scope permitted for that token
- `TAVILY_API_KEY`: Tavily search credential
- `ANALYSIS_API_KEY`: key for the configured OpenAI-compatible model endpoint
- `ANALYSIS_BASE_URL`: defaults to `https://api.openai.com/v1`; production endpoints must use HTTPS and must not embed credentials, query strings, or fragments (HTTP is permitted only for loopback development endpoints)
- `ANALYSIS_MODEL`: defaults to `gpt-4.1-mini`
- `UCOS_ENV=production` for production startup checks

Production startup and `/health/ready` now fail closed unless PostgreSQL and Redis are reachable, the bearer token and provider credentials are configured, the single scope is fully configured, and that exact scope has an enabled row in `ucos_research_scope_grants`. The scope probe is read-only; it never provisions or modifies grants. Configure Render's health-check path as `/health/ready` after all required settings and the enabled scope grant exist; readiness intentionally returns HTTP 503 until every gate passes.

The three `UCOS_RESEARCH_SCOPE_*` values must be sourced from the approved tenant/workspace/brand authority; do not invent them. The API fails closed with HTTP 503 if any are missing and returns HTTP 403 if a request asks for a different scope. This is a single configured scope per service token, not multi-tenant identity federation. Never commit secrets. See `.env.example` for variable names only.

### Database setup

Apply `migrations/001_agent01_research.sql`, `migrations/002_scope_provisioning_audit.sql`, `migrations/003_research_idempotency_replay.sql`, `migrations/004_research_idempotency_claims.sql`, and `migrations/005_scope_provisioning_idempotency.sql` in numeric order to the configured PostgreSQL database before enabling the endpoint. Migration 003 adds the persisted `max_results` field used to validate retries. Migration 004 adds fenced, expiring in-progress claims so simultaneous duplicate requests do not both invoke providers; active duplicates receive HTTP 409, and expired workers cannot overwrite a newer claim. Seed `ucos_research_scope_grants` only through your approved identity/tenant administration workflow; this table is an authorization grant boundary, not an automatic grant. The configured scope must also have an enabled row in that table. In a production deployment, migrations should be applied by a controlled migration job, not silently by app startup.

### Controlled initial scope provisioning

For a single-owner initial deployment with no existing identity/admin system, an operator can create one UUID-based scope using the explicit provisioning command. This is not a public admin API and does not enable multi-tenant self-service.

1. Confirm migrations `001_agent01_research.sql`, `002_scope_provisioning_audit.sql`, and `005_scope_provisioning_idempotency.sql` have been applied through the controlled migration process described above.
2. Use a dedicated, least-privilege provisioning database role and set its connection string in `UCOS_PROVISIONING_DATABASE_URL`. Do not reuse the application database credential if you can avoid it.
3. Set `UCOS_PROVISIONING_ACTOR` to an operator identity suitable for the audit record (do not put a password or token there).
4. Run `python -m ucos_core.provisioning --idempotency-key INITIAL-SETUP-2026-01 --confirm` in a controlled operator environment. Choose a unique non-secret key for this provisioning intent and reuse exactly the same key after an uncertain outcome. Without `--confirm`, the command makes no changes. It prints the three generated IDs only after the database transaction succeeds.
5. Store the returned IDs in the approved deployment record and configure the matching `UCOS_RESEARCH_SCOPE_TENANT_ID`, `UCOS_RESEARCH_SCOPE_WORKSPACE_ID`, and `UCOS_RESEARCH_SCOPE_BRAND_ID` values in Render. Never paste secrets into source control or chat.
6. To revoke a scope, run `python -m ucos_core.provisioning --disable TENANT_ID WORKSPACE_ID BRAND_ID --confirm` with the same operator environment. This disables the grant and records an audit event in one transaction; it does not delete research history. Remove or rotate the matching Render scope configuration as part of the operator's revocation procedure.
7. Verify the grant with a read-only query before enabling traffic:

```sql
SELECT tenant_id, workspace_id, brand_id, enabled
FROM public.ucos_research_scope_grants;
```

The initial scope IDs are generated by this operator-run workflow because no external identity authority is configured. They are opaque identifiers, not credentials. This first increment creates the scope grant record and audit entry; it does not implement a full tenant/workspace/brand entity catalog, a browser admin panel, or multi-tenant identity federation. Do not run the provisioning command against production until the migration, database role, and deployment plan have been reviewed. This workflow is intended for a single owner-controlled scope; onboarding multiple tenants requires a dedicated identity and admin authorization design.

### API

`POST /v1/agents/01/research`

The request requires request/correlation IDs, tenant/workspace/brand scope, workflow and workflow-step IDs, a query, and an optional result limit. The HTTP boundary first authenticates the bearer token and restricts the request to that token's configured single scope; the database authorizer then checks the exact enabled grant. The service preserves source URL, title, excerpt, provider and retrieval timestamp. Model calls are capped at 3,000 output tokens and responses above 20,000 characters or explicitly truncated completions fail closed. A completed request with matching metadata is replayed from PostgreSQL without calling providers again. Reusing a request ID with different metadata is rejected with HTTP 409. An atomic five-minute database claim prevents ordinary concurrent duplicate requests from invoking providers simultaneously; live duplicates receive HTTP 409, and expired claims may be taken over with a new fencing generation so stale workers cannot overwrite the winner. Success is never returned unless the result has been persisted.



### Explicit live smoke test

After the real endpoint, migrations, provider credentials, and approved scope are configured, run a non-sensitive end-to-end verification from an authorized operator environment. Use a **read-only** database credential for `UCOS_AGENT01_VERIFY_DATABASE_URL`; never use this script to print or export secrets.

Set `UCOS_AGENT01_BASE_URL`, `UCOS_RESEARCH_API_TOKEN`, the three `UCOS_RESEARCH_SCOPE_*` values, and `UCOS_AGENT01_VERIFY_DATABASE_URL`, then run:

```bash
python scripts/verify_agent01_live.py --query "a non-sensitive test query" --confirm-live
```

The command makes two real API calls using the same generated request ID, checks the replay payload matches the first response, and verifies the stored result/provenance in PostgreSQL. It does not run without `--confirm-live`, and it prints no credentials. The request may incur provider charges. A successful smoke test is required before production traffic is enabled.

### Local verification

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
python -m ucos_core.preflight
```

The CI workflow additionally builds the container. Actual production readiness still requires real database/cache/provider credentials, a migrated database, valid tenant grants, deployment configuration, and live end-to-end verification.
