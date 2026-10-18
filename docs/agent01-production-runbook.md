# Agent 01 production protection runbook

This runbook is an operator checklist, not authorization to mutate production. Keep PRs draft until review and required checks are complete. Never paste credentials, bearer tokens, database URLs, or provider keys into GitHub issues or chat.

## 0. Change-control gate

- [ ] Obtain explicit approval from the production owner for the deployment window and migration.
- [ ] Confirm PR #4 (audited scope provisioning) and PR #5 (idempotent replay / fencing) have been reviewed and approved.
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

- [ ] Confirm migrations 001–004 match the reviewed commit.
- [ ] Apply migrations through the approved migration process using a migration credential, not the application runtime credential.
- [ ] Verify `ucos_research_runs` contains `max_results`, `claim_expires_at`, and `claim_generation`, and its status constraint permits `IN_PROGRESS`, `SUCCEEDED`, and `NO_RESULTS`.
- [ ] Verify `ucos_research_scope_grants` and `ucos_scope_provisioning_audit` exist.
- [ ] Do not create a scope until the production owner approves the exact tenant/workspace/brand ownership and actor identity.

## 3. Scope provisioning

Run the operator command from an authorized environment only after the preceding approval and migration checks. Supply `UCOS_PROVISIONING_DATABASE_URL` and `UCOS_PROVISIONING_ACTOR` via the approved secret mechanism. Then run:

```sh
python -m ucos_core.provisioning --confirm
```

- [ ] Record the generated tenant/workspace/brand IDs in the approved deployment record (not source control or public issue comments).
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

- [ ] Have a repository administrator configure and verify default-branch protection / rulesets requiring pull-request review and successful CI.
- [ ] Confirm direct pushes and force pushes are restricted as policy requires.
- [ ] The connected GitHub integration may not have administration permission to read or change protection settings; do not treat inability to inspect them as evidence that protection is enabled.
- [ ] Keep PR #4 and PR #5 unmerged until the approvals and production gates above are satisfied.

## Current verified status

As of 2026-10-19, PR #5 CI passed on commit `864224641a7b27a217135642ed84df68d0ab2dfa`, but the production Render service was still on an older branch; production Neon lacked migrations 003/004; the scope grant and provisioning audit table were absent; and a real live smoke test had not been performed. Therefore Agent 01 is not yet production-ready. Re-verify every item above immediately before any deployment.
