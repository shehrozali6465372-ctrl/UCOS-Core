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

- [ ] Use an authorized GitHub admin view/API to configure and verify main branch rules consistent with the single-owner policy. Recommended minimums: required CI checks and restrictions on force pushes/direct writes; the owner decides whether a separate-review requirement matches project policy.
- [ ] Confirm direct pushes and force pushes are restricted as policy requires.
- [ ] Main branch protection/ruleset status is currently UNKNOWN: a previous attempt to read the endpoint through the connected integration returned 403. Do not infer protection is enabled or disabled from that error.
- [ ] Keep PR #12 draft/open/unmerged until the exact production change plan is owner-approved and all production gates above are satisfied.

## Current verified status

As of 2026-10-20, [PR #12](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/12) remains open/draft/unmerged. Its integration head `8868d07a6368d454712bb44a1eb273dc6a8917b9` passed [CI run #109](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39344562975): lint clean, 66 tests passed against ephemeral PostgreSQL 16 (1 warning), Docker build and cleanup passed. PR #13 credential transport hardening and PR #14 Node 24-compatible CI action upgrades were merged to the integration branch only, not `main`.

Production is not certified: the Neon production/default branch still lacks the complete migration schema and no approved scope grant exists; Render still points at `agent-01/production-v1` and its health-check path is unset; an authenticated live persistence/replay verification has not been performed. Main branch protection status is UNKNOWN. No production migrations, grant provisioning, secret/configuration edits, or deployments have occurred. Re-verify all items immediately before any production change.


## Provisioning idempotency recovery note — 2026-10-20

A focused code review identified that the retry path originally used an inner join between the provisioning idempotency ledger and the scope-grant table. If a ledger record exists without its grant row, the join hides the record and returns an unhelpful “record missing” failure. The recovery fix now reads the ledger first and fails closed with an explicit operator-reconciliation error if the grant is absent; it never silently recreates or enables a grant on retry. A retry against a disabled grant remains rejected. See draft PR #16: https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/16.

PR #16 is not merged and its exact-head CI is not yet available. Treat this as an unvalidated draft fix until CI passes and the change is reconciled with the canonical Agent 01 stack.
