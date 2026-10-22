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

As of 2026-10-20, [PR #12](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/12) remains open/draft/unmerged. The current integration head is `820cc2f4be325fc2a59040b130225c9bf49e05e3`; [CI run #129](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39403863709) passed on that exact head: Ruff clean, 68 tests passed against ephemeral PostgreSQL 16 (1 warning), Docker build and cleanup passed. PR #17 provisioning recovery was merged into `agent-01/clean-main-integration`; no changes were merged into `main`.

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


## Latest production-readiness checkpoint — 2026-10-20 12:40 UTC

This section supersedes the older point-in-time snapshot above where it differs.

- Runtime hardening PR #19 was merged into `agent-01/clean-main-integration` only at `6ce224e06c9464637cf1080f6316bf9059935b16`. It adds non-root UID/GID 10001, excludes environment/key/secret paths from the Docker context, verifies non-root runtime in CI, and adds a manual opt-in live verifier workflow. PR #19's exact pre-merge head `3c5b7fcd5756c151070d130e93ebd7efd67baf78` passed CI run #131. Main was not changed.
- After that merge, CI run `39423955481` for the integration head was observed in progress. Do not claim post-merge validation passed until it completes on the exact deployed SHA.
- A prepared migration using the SQL represented by migrations 001–005 was exercised on a temporary Neon branch. It produced all four expected tables and `ucos_research_runs.max_results`, `claim_expires_at`, and `claim_generation`; the status constraint allows `IN_PROGRESS`, `SUCCEEDED`, and `NO_RESULTS`. No research rows or scope grants were created during this check. The temporary branch was deleted afterward. This is a disposable schema test, not a production migration.
- Current read-only production/default Neon verification still shows only `ucos_research_runs` and `ucos_research_scope_grants`; the three claim/replay columns and both provisioning audit/ledger tables remain absent. No approved scope grant exists.
- Current Render service readback is still `agent-01/production-v1`, auto-deploy enabled, health-check path blank, ingress `0.0.0.0/0`, free plan. Do not point it at the integration branch or deploy the new image until the production schema, secrets, scope and rollback gates are complete.
- PR #12 is still open/draft/unmerged and its head now tracks integration commit `6ce224e06c9464637cf1080f6316bf9059935b16`. Main remains at `d770512de3bf7523ff04885a671f82dfa93d952e` as last verified.
- No production migration was applied, no scope was provisioned, no secrets or Render settings were changed, no deployment occurred, and no real provider-backed smoke test was run.

### Immediate blockers

1. Obtain explicit operator approval for the production migration/deployment window, confirm the exact production project/default branch and approved migration role, and verify a current restore point plus rollback plan. The migration connector requires an explicit go-ahead before applying the prepared migration to production.
2. Identify and approve the exact tenant/workspace/brand scope and actor for initial provisioning; do not invent or silently create a production scope.
3. Set and verify Render's production secrets through its secret manager; never print or paste their values.
4. After migration and configuration are approved, set the correct Render branch and `/health/ready`; restrict ingress to the intended access model.
5. Run the approved live persistence/idempotent-replay smoke test using an approved non-sensitive query, and separately verify with a read-only DB credential.
6. Enable and verify owner/admin branch protection for `main`; branch metadata currently reports `protected=false`.


### Backup and database-role recheck — 2026-10-20

- Neon snapshot inventory returned no snapshots, and the production/default branch snapshot schedule is empty. A usable pre-migration restore point is **not verified**; do not apply schema migrations until a backup/restore point is explicitly created and its recovery path reviewed.
- Production Neon lists only the `ucos_core_owner` PostgreSQL role. No dedicated migration/runtime role was found. The table grants inspected show the owner role has broad privileges; this does not prove which role Render currently uses because Render secret values are intentionally not read. Create and verify least-privilege migration and runtime roles through an approved change before rollout.


### Pre-migration snapshot created — 2026-10-20 12:42 UTC

- Manual Neon snapshot `snap-falling-snow-azcy9onf` (`ucos-core-pre-production-migration-2026-10-20`) was created from production/default branch `br-dark-pond-azjzxzmd`; it expires at `2026-11-03T00:00:00Z`.
- Snapshot existence is verified. A restore drill has **not** been performed; do not mark the restore/rollback checklist complete until recovery instructions and restore behaviour have been reviewed.


### Automated backup scheduling limitation — 2026-10-20

- Attempted to configure daily snapshots with 14-day retention on the production/default Neon branch. Neon rejected schedule creation because automated backup scheduling is not enabled for this project. The schedule remains unconfigured.
- The manual pre-migration snapshot above exists, but automatic backup coverage is still a blocker. Owner must enable an available backup policy in Neon or establish an approved recurring manual snapshot process; verify a restore drill before production migration.


### Least-privilege permission dry-run — 2026-10-20

- The full migrations 001–005 plus a candidate grant set were exercised on a separate temporary Neon branch, then that branch was deleted without applying changes to production.
- Candidate `ucos_core_runtime` role: `SELECT/INSERT/UPDATE` on `ucos_research_runs`, `SELECT` on `ucos_research_scope_grants`, and no `DELETE` on research runs or `INSERT` on scope grants.
- Candidate `ucos_core_provisioner` role: `SELECT/INSERT/UPDATE` on scope grants, `SELECT/INSERT` on provisioning requests, and `INSERT` on provisioning audit. Required schema/tables and these privilege checks passed on the temporary branch.
- These are tested candidate NOLOGIN group roles only. Neither role nor any production privilege was created by this dry run; owner approval, actual login credentials/secret delivery, and a production grant verification remain outstanding.


### Production schema migration applied and verified — 2026-10-20 13:00 UTC

- After operator approval, applied the exact SQL corresponding to migrations 001–005 to Neon production/default branch `br-dark-pond-azjzxzmd` in project `billowing-meadow-65083232`. The exact same SQL had passed a temporary-branch dry run immediately beforehand.
- Post-apply read-only verification confirms all four expected tables exist: `ucos_research_runs`, `ucos_research_scope_grants`, `ucos_scope_provisioning_audit`, and `ucos_scope_provisioning_requests`.
- `ucos_research_runs` has `max_results` (nullable, constrained 1–10), `claim_expires_at`, and `claim_generation` (NOT NULL DEFAULT 0); status constraint permits `IN_PROGRESS`, `SUCCEEDED`, `NO_RESULTS`.
- Row counts after migration: research runs 0; scope grants 0; provisioning audit 0; provisioning requests 0. No scope has been provisioned and no research data was inserted.
- Pre-migration manual snapshot `snap-falling-snow-azcy9onf` was confirmed present immediately after migration. Restore drill remains unverified; automated snapshot scheduling remains unavailable for this Neon project.
- This was a schema-only migration. No production login roles or grants were changed, no secrets or Render settings were changed, no deployment occurred, and no live provider-backed smoke test was run.
- Next gates remain: configure/verify least-privilege runtime and provisioning credentials through approved secret management; approve and provision the exact scope with an audit record; configure Render branch/health-check/ingress; verify health endpoints and run authenticated persistence/replay smoke; configure/verify GitHub branch protection. Do not declare full production readiness until those checks pass.

## Latest re-verified Agent 01 checkpoint — 2026-10-21 (Asia/Karachi)

This checkpoint records fresh read-only checks and the current isolated PR #20 branch. It does not authorize or prove a production release.

### Exact-head code/CI state
- Agent 01 hardening PR #20 is open, draft, and unmerged.
- Exact head at this checkpoint: `ea1d4d5f1235e4434127ac8c0097eb429748fec4`.
- CI run #150 passed on that exact head: [run #150](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39500145342). Ruff, PostgreSQL-backed tests, Docker build, and non-root container verification passed.
- Code changes in this branch align API token minimum-length enforcement with readiness checks and add regression coverage. The API's minimum-length gate does not prove entropy; service operators must generate tokens with a cryptographically secure random generator.

### Fresh production read-only checks
- Render service `ucos-core-agent01` remains configured for branch `agent-01/production-v1`, auto-deploy is enabled, `healthCheckPath` is unset, and ingress remains `0.0.0.0/0`.
- Last observed live deploy is `cac576d80761c04866a7e06e11473c71fbaf8aff`, marked live on 2026-10-16. No new production deployment was triggered.
- Production Neon branch `br-dark-pond-azjzxzmd` contains the four expected tables: `ucos_research_runs`, `ucos_research_scope_grants`, `ucos_scope_provisioning_audit`, and `ucos_scope_provisioning_requests`.
- Fresh read-only counts: enabled scope grants = 0; research runs = 0; provisioning audit rows = 0; provisioning request rows = 0.
- The only production PostgreSQL role returned by the connected role inventory is `ucos_core_owner`. A dedicated least-privilege runtime role was not found.
- Secret values/presence and live runtime connectivity have not been verified. No authenticated live persistence/replay smoke test has run.

### Remaining release gates
1. Owner/operator must approve the exact initial tenant/workspace/brand identifiers and provisioning actor. The CLI creates fresh UUID scope identifiers on a new idempotency key; do not run it before the owner approves the real project scope and actor.
2. Provision a dedicated least-privilege runtime role and validate its exact table/column privileges with the approved migration/operator process. Do not use `ucos_core_owner` as the application runtime credential.
3. Configure and verify Render secrets directly in the Render secret manager. Never print or paste secret values into issues, logs, or this file.
4. Set the service branch, readiness health-check path, and ingress policy only under an approved change plan with a known rollback/recovery path.
5. Run the manual live verifier only after its production GitHub Environment secrets/approval are configured. It makes real provider calls and verifies durable persistence plus identical replay using a separate read-only verification DB credential.
6. Keep PR #20 and integration PR #12 unmerged until exact-head CI, owner-approved scope, runtime permissions, secrets, readiness, and live end-to-end verification are all resolved.

### Production changes made in this checkpoint
None. No production migration, scope/grant write, role creation, secret update, Render configuration change, deployment, or provider-backed live request occurred.

### Backup recheck — 2026-10-21 (read-only)

- Neon snapshot inventory currently returns `snap-falling-snow-azcy9onf`, named `ucos-core-pre-production-migration-2026-10-20`, for production branch `br-dark-pond-azjzxzmd`. Recorded expiry: 2026-11-03 00:00 UTC.
- This establishes that a snapshot record exists; **a restore/rollback drill has not been performed or verified**. Before production migrations or deployment, recheck snapshot status/expiry, verify that it is restorable, and document the exact restore/rollback steps.


## Current continuation checkpoint — 2026-10-22  (live repository checks)

This checkpoint is supplemental and supersedes earlier statements in this file only where they explicitly conflict. No production infrastructure, credentials, tables, grants, roles, or deployments were changed while preparing this checkpoint.

### Isolated code hardening PRs

The following stacked changes are open, draft, unmerged, and are not present on `main`:

- PR #30 [Evidence URL syntax validation](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/30), exact head `827c32c8512d0ceee26bd4c8782f2fef6bf7aa5c`, CI run #169 passed: [run](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39761542949).
- PR #31 [Provider URL filtering aligned with evidence contract](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/31), exact head `fe9e7f8d57552bbffa88bf3a337992f4075b6382`, CI run #171 passed: [run](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39762151030). It is stacked on PR #30.
- PR #32 [Require HTTPS model endpoint in production](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/32), exact head `cd96127381cc7e2d9bbf88d452e59fd0e08f0bf9`, CI run #174 passed: [run](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39762968068). It is stacked on PR #31. Loopback HTTP remains available in non-production development, while production mode rejects it; readiness uses the corresponding policy.
- All three exact-head runs passed Ruff, the P0 safety/PostgreSQL-backed test suite, Docker build, non-root container verification, and cleanup. These are ephemeral CI checks, not live production verification.

### Fresh GitHub branch protections

Read-only GitHub branch records returned:
- `main`: `d770512de3bf7523ff04885a671f82dfa93d952e`, `protected=false`, required status-check enforcement `off`, no required checks.
- `agent-01/clean-main-integration`: `a59ddc16a0e1aacefa2661863bdc65645c69018d`, `protected=false`, required status-check enforcement `off`, no required checks.

Treat this as an active repository release-control blocker.

### Production state and remaining blockers

Existing read-only verification recorded for production Neon:
- The four expected research/provisioning schema tables and claim/replay columns are present following the 2026-10-20 migration.
- Enabled scope grants: 0; research runs: 0; provisioning audit rows: 0; provisioning request rows: 0.
- The connected role inventory found only `ucos_core_owner`; a dedicated least-privilege runtime login role has not been verified.
- Manual snapshot `snap-falling-snow-azcy9onf` was recorded to expire 2026-11-03T00:00:00Z. A restore drill remains unverified and automated snapshot scheduling was reported unavailable.
- Render's last readback showed service `ucos-core-agent01` tracking `agent-01/production-v1`, auto-deploy enabled, readiness health-check unset, ingress `0.0.0.0/0`, and last known live commit `cac576d80761c04866a7e06e11473c71fbaf8aff`. These Render values have not been freshly re-read in this continuation and must be reconfirmed immediately before any release.
- Required secret values must not be printed; actual presence and validity remain unverified. Live authenticated persistence/replay verification has not been performed.

### Next engineering steps

1. Finish code-level SSRF policy review at any actual URL-dereferencing boundary. Current changes validate candidate citation syntax; they do not by themselves defend against DNS rebinding, private/reserved IP resolution, redirect chains, or unsafe outbound network routes. Where evidence URLs are never fetched by UCOS, document the boundary rather than claiming a complete SSRF fix.
2. Review existing open PRs and the combined release candidate for duplicate/stacked diffs before merging. Keep PRs #30–#32 draft until their combined behavior and target integration diff are reviewed; do not merge blindly.
3. Configure/verify required branch protections via authorized repository owner/admin controls.
4. Under an approved change plan, provision and verify dedicated least-privilege database roles, approve the exact scope and actor, verify secret configuration, correct Render branch/health readiness/ingress, recheck backup/recovery and run the authenticated end-to-end persistence/replay smoke test.
5. Do not deploy production solely because CI is green.

Production readiness status: **NOT READY**. No production changes were made as part of this checkpoint.


## Continuation checkpoint — 2026-10-22 (PR #33 model prompt fix)

- PR #33: [preserve real newlines in model evidence prompt](https://github.com/shehrozali6465372-ctrl/UCOS-Core/pull/33), branch `agent-01/model-prompt-newlines`, stacked on PR #32. Code change fixes the separators in the outgoing analysis prompt and adds a transport-level regression test.
- First CI attempt #176 ([run](https://github.com/shehrozali6465372-ctrl/UCOS-Core/actions/runs/39763900136)) failed at Ruff only: one assertion exceeded the configured 100-character line limit. Tests, Docker build, and non-root verification were skipped by the workflow after lint failed.
- Corrected the assertion formatting in commit `95769e59c9c63725a7e8b732888056a63297e4f2`. As of this checkpoint, GitHub has not returned a workflow run or commit status for that corrected exact head; CI remains pending/unverified. Do not merge until exact-head CI passes.
- PR #33 remains draft/open/unmerged. No production resource, secret, database, Render setting or deployment was modified. This prompt serialization fix does not certify production readiness.
