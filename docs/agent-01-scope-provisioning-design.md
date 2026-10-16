# Agent 01 scope provisioning — design proposal

## Status

Design-only proposal. This document does not create tenant identities, database grants, API credentials, or production configuration. The existing Agent 01 endpoint currently supports one explicitly configured tenant/workspace/brand scope per service token and separately requires an enabled row in `public.ucos_research_scope_grants`.

## Current blocker

The repository currently documents that grants must come from an approved tenant/identity administration workflow, but the project owner has no such admin panel or system. Therefore, there is no approved source of canonical `tenant_id`, `workspace_id`, or `brand_id` values, and no supported way to grant a scope. Do not seed placeholder IDs or enable the production endpoint until the authority and provisioning process are selected.

## Recommended first increment (no public admin API)

Use a controlled, operator-run provisioning command/job as the first admin surface, rather than exposing a new internet-facing admin endpoint.

1. **Identity and authority decision:** define who is allowed to create a tenant, workspace, and brand, and where canonical IDs originate. For a single-owner initial deployment, the owner is the operator; this must not silently become open self-service.
2. **ID format:** generate opaque IDs using a standard UUID generator if no external identity provider is chosen. Store them as strings in the existing text columns. IDs are identifiers, not authentication credentials.
3. **Provisioning operation:** create the tenant/workspace/brand record or manifest in a controlled source of truth, then create or enable the matching row in `ucos_research_scope_grants` through an explicitly invoked administrative command/job. The operation should be idempotent and validate that the hierarchy is consistent.
4. **Scope configuration:** configure the exact same IDs in `UCOS_RESEARCH_SCOPE_TENANT_ID`, `UCOS_RESEARCH_SCOPE_WORKSPACE_ID`, and `UCOS_RESEARCH_SCOPE_BRAND_ID` for the Render service. Keep `UCOS_RESEARCH_API_TOKEN` and provider credentials in Render secret environment variables only; never print or commit their values.
5. **Fail closed:** refuse service enablement if migration is missing, scope settings are incomplete, the grant row is absent/disabled, or Postgres/Redis/provider configuration is unavailable.
6. **Audit:** record who invoked provisioning, when, which scope was created/changed, and whether it succeeded. Never log bearer tokens or provider credentials.
7. **Revocation:** provide a documented operator procedure to disable the grant and rotate the service token if it may be compromised. Scope removal must not delete research history by default.

## Security requirements before implementation

- Do not add a public unauthenticated endpoint for tenant or grant creation.
- Do not hard-code or insert sample tenant/workspace/brand IDs into production.
- Keep the existing bearer-token-to-one-scope check and exact database grant check.
- Protect provisioning by an out-of-band operator credential or an approved platform identity; store it as a secret, apply least privilege, and do not reuse the Agent 01 research token as an admin credential.
- Use parameterized SQL and explicit transactions. Validate IDs and hierarchy before enabling a grant.
- Add tests for unauthorized provisioning, malformed input, duplicate/idempotent requests, grant disablement, missing configuration, and no secrets in logs.
- No real external end-to-end test or production certification is implied by unit/CI success.

## Rollout sequence

1. Review and approve this design.
2. Implement the operator-run provisioning CLI/job and tests on a separate branch.
3. Run lint, tests, and image build in CI.
4. Review the diff and CI result before merging.
5. Only after approval, provision one real owner-controlled scope, verify the enabled grant with read-only SQL, configure Render environment variables, and run a live request against non-sensitive test data.
6. Document rollback/revocation before enabling broader use.

## Open decision

If the product will later support multiple tenants, decide on an identity provider and tenant-admin authorization model before expanding the current single-scope-per-service-token design. This proposal intentionally does not implement multi-tenant identity federation.
