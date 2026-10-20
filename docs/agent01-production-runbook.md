# Agent 01 production protection runbook

This runbook is an operator checklist, not authorization to mutate production. The owner selected a single-owner workflow; do not request a third-party reviewer by default. Automated review and CI are required engineering steps, but they do not constitute independent review. Keep PR #12 draft until production gates are complete. Never paste credentials, bearer tokens, database URLs, or provider keys into GitHub issues or chat.

## 0. Change-control gate

- [ ] Obtain explicit approval from the production owner for the deployment window and migration.
- [ ] Verify the canonical integration candidate [PR #12](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/12) is the exact code intended for deployment; perform focused owner-led review and check CI on the exact head. Do not claim an independent review occurred.
- [ ] Confirm all required CI checks pass on the exact commit to deploy.
- [ ] Record the target commit, operator, maintenance window, rollback owner, and recovery procedure.
- [ ] Verify a current database backup / restore point and that rollback steps have been tested or reviewed.
- [ ] Verify the deployed runtime's database role is least-privilege; do not use the schema owner for routine API traffic.

## 1. Pre-deployment verification

- [ ] Verify the Render service is configured to deploy the reviewed commit / approved branch, not an older production branch.
- [ ] Verify required secrets exist in Render's secret manager without printing or exporting values: `DATABASE_URL`, `UCOS_RESEARCH_API_TOKEN`, `UCOS_RESEARCH_SCOPE_TENANT_ID`, `UCOS_RESEARCH_SCOPE_WORKSPACE_ID`, `UCOS_RESEARCH_SCOPE_BRAND_ID`, `TAVILY_API_KEY`, `ANALYSIS_API_KEY`, and valid `ANALYSIS_BASE_URL` / `ANALYSIS_MODEL`.
- [ ] Verify `UCOS_ENV=production` and the correct PostgreSQL / Redis connection settings.
- [ ] Confirm provider budget / rate limits and an approved non-sensitive smoke-test query.
- [ ] Set Render's health-check path to `/health/ready` only when the migration and configuration prerequisites are met. `/health/live` is not a readiness signal.

## 2. Database migration

- [ ] Confirm migrations 001–005 match the reviewed commit.
- [ ] Apply migrations through the approved migration process using a migration credential, not the application runtime credential.
- [ ] Verify `ucos_research_runs` contains `max_results`, `claim_expires_at`, and `claim_generation`, and its status constraint permits `IN_PROGRESS`, `SUCCEEDED`, and `NO_RESULTS`.
- [ ] Verify `ucos_research_scope_grants`, `ucos_scope_provisioning_audit`, and `ucos_scope_provisioning_requests` exist.
- [ ] Do not create a scope until the production owner approves the exact tenant/workspace/brand ownership and actor identity.

## 3. Scope provisioning

Run the operator command from an authorized environment only after the preceding approval and migration checks. Supply `UCOS_PROVISIONING_DATABASE_URL` and `UCOS_PROVISIONING_ACTOR` via the approved secret mechanism. Then run:

```sh
python -m ucos_core.provisioning --idempotency-key INITIAL-SETUP-2026-01 --confirm
```

- [ ] Record the generated tenant/workspace/brand IDs in the approved deployment record (not source control or public issue comments).
- [ ] Reuse the same idempotency key only when retrying this exact provisioning intent; use a new key for a distinct approved operation.
- [ ] Configure those exact IDs in Render and verify the enabled grant is present in PostgreSQL.
- [ ] Confirm the provisioning audit row records the actor and `SCOPE_CREATED`.
- [ ] Ensure the bearer token is scoped only to that exact configured tenant/workspace/brand tuple.

## 4. Deploy and validate

- [ ] Deploy the reviewed commit after approvals and migrations; inspect build and runtime events.
- [ ] Confirm `GET /health/live` returns alive and `GET /health/ready` returns ready with all required components.
- [ ] If readiness is not ready, do not bypass the gate or accept traffic; inspect dependency booleans without disclosing secrets.
- [ ] From an authorized operator environment, run the live verifier with the separate read-only verification DB credential:

```sh
python scripts/verify_agent01_live.py --query "<approved non-sensitive query>" --confirm-live
```

- [ ] Verify two identical requests with the same request ID produce an identical replay and exactly one durable row with the expected provenance.
- [ ] Verify invalid bearer token returns 401; unconfigured scope fails closed; out-of-scope request returns 403; request-ID input mismatch returns 409; active duplicate returns 409 with `Retry-After`; stale claim cannot overwrite the new generation.
- [ ] Verify evidence URLs are validated and the model analyzer rejects insecure remote base URLs / truncated output.
- [ ] Confirm logs and metrics show the expected requests without leaking tokens, provider credentials, or full database URLs.

## 5. Rollback and revocation

- [ ] If validation fails, stop rollout / remove traffic according to the approved incident procedure; do not disable readiness to force traffic.
- [ ] Revert to the previously approved compatible application release only if its schema compatibility has been checked. Do not blindly reverse additive migrations.
- [ ] Disable the specific scope through the audited provisioning command when access must be revoked:

```sh
python -m ucos_core.provisioning --disable <TENANT_ID> <WORKSPACE_ID> <BRAND_ID> --confirm
```

- [ ] Rotate the bearer/provider credentials through the secret manager if compromise is suspected.
- [ ] Record incident findings and rerun the full validation before re-enabling traffic.

## 6. Repository protection

- [ ] Configure and verify GitHub branch rules for `main` using an authorized owner/admin interface before any production rollout. The GitHub branches API currently reports `protected=false` for both `main` and `agent-01/clean-main-integration`; required status checks and force-push/direct-write restrictions are therefore not shown as enabled in that snapshot.
- [ ] The dedicated branch-protection endpoint returns 403 through the connected integration, so exact ruleset settings cannot be inspected there. Re-check them with owner/admin access and do not infer that protections are enabled.
- [ ] Keep PR #12 draft/open/unmerged until the exact code and production change plan are approved, required CI is green, and all production gates above are complete.

## Current verified status

As of 2026-10-20, [PR #12](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/12) remains open/draft/unmerged. The current integration head is `7526bf63b85d5e0d4f5924cb6346e278e6411f3f`; [CI run #128](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39402854729) passed on that exact head: Ruff clean, 68 tests passed against ephemeral PostgreSQL 16 (1 warning), Docker build and cleanup passed. PR #17 provisioning recovery was merged into `agent-01/clean-main-integration`; no changes were merged into `main`.

Read-only Neon checks on 2026-10-20:
- Production/default branch `br-dark-pond-azjzxzmd` contains only `ucos_research_runs` and `ucos_research_scope_grants`; both tables have zero rows. Provisioning audit/ledger tables are absent and the `max_results`, `claim_expires_at`, and `claim_generation` columns are absent.
- Isolated verification branch `br-young-frost-azl3nufg` has the two provisioning audit/ledger tables and all three claim/replay columns; its research scope grant table contains zero rows. Treat this as a schema verification branch, not as production or authorization to provision a real scope.
- Render workspace has an available `ucos-core-cache` Key Value resource (free plan, eviction policy `allkeys_lru`, persistence off) and no Render PostgreSQL instance. UCOS PostgreSQL currently resides in Neon.

Render service `ucos-core-agent01` remains configured to track `agent-01/production-v1`, with auto-deploy on, no health-check path, public ingress `0.0.0.0/0`, and free plan. Latest deploy record remains live at commit `cac576d80761c04866a7e06e11473c71fbaf8aff` from 2026-10-16; prior deploy attempts were marked `update_failed`. Render request logs returned no recorded requests for `/health/live` or `/health/ready` in the queried window; this does not prove the service is unreachable, so endpoint status remains unverified.

Production is NOT READY: the production/default Neon schema is incomplete; no approved enabled scope grant exists; production secret presence/validity is not verified; the Render service still tracks the old branch and has no readiness health-check path; authenticated live persistence/replay verification has not been performed; and main branch protection is reported `protected=false`. Owner-approved migration/deployment window, backup/restore and rollback validation, least-privilege DB roles, approved scope/actor, secret configuration, readiness configuration, live smoke verification, and branch rules remain blockers. No production migration, grant provisioning, secret/configuration edit, or deployment has been performed. Re-verify all items immediately before any approved production change.


## Integration reconciliation follow-up — 2026-10-20

PR #17 (`fix(agent-01): reconcile provisioning recovery into integration`) was merged on 2026-10-20 as integration commit `7526bf63b85d5e0d4f5924cb6346e278e6411f3f`. Its exact-head CI run #128 passed: Ruff passed, 68 tests passed (1 warning) with ephemeral PostgreSQL 16, Docker image build passed, and the CI cleanup completed. This validates the integration branch only; `main` remains at `d770512de3bf7523ff04885a671f82dfa93d952e`.

A separate draft test PR #18 is still open against the integration branch; its repeated candidate runs failed while adjusting fixtures, and it is not required as a merge gate now that the same recovery implementation and core regression cases are present in the merged PR #17. Reconcile/close this redundant PR after its patch has been checked against the merged integration tests; do not merge it blindly.

Production verification above remains blocking. CI green is necessary but does not certify the real database, real provider calls, runtime configuration, or ingress/readiness controls.
