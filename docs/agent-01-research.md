# Agent 01 — Research (L02)

## Frozen ownership

The agent implements L02 source discovery and provenance capture. Provider-specific lifecycle and transport are delegated to the L11 `ResearchSourcePort` adapter; authorization is delegated to L17's `ResearchAuthorizationPort`; durable writes are delegated to L13's `ResearchRepositoryPort`. The L02 service does not own SQL, provider SDKs, credentials or authorization policy.

## Contract and behavior

`ResearchRequest` requires workflow, request, correlation and full tenant/workspace/brand/account/platform identity. Requests with missing scope fail validation. `ResearchResult` is versioned (`schema_version=1.0.0`) and carries status, provenance, explicit error codes and retryability.

The service verifies persistence readiness before calling a research source, then persists the result before returning it. Empty provider results are `NO_RESULTS`; provider failures are represented explicitly as `FAILED` with normalized error codes. Provider-returned URL, title, excerpt, provider identifier and timestamps are retained as provenance; the agent does not invent observations or confidence values.

## HTTP route

`POST /v1/research`

The route is intentionally not usable with implicit permissive adapters. Production wiring must supply the L17 authorization adapter, L13 persistence adapter and L11 source adapter. Missing required adapters fail closed with HTTP 503; rejected authorization returns HTTP 401. The concrete Tavily adapter reads `TAVILY_API_KEY` from the environment and never returns the key in responses or errors.

## Current integration boundary

The L02 contracts/service and L11 Tavily transport adapter are implemented and testable with injected ports. The production L17 authorization and L13 PostgreSQL repository adapters are not yet implemented in this commit sequence, so the default core application must not be represented as a production-ready live research deployment.

## Validation

CI validates schema identity requirements, explicit empty/failure statuses, source provenance, auth-before-provider ordering, persistence-before-provider ordering, adapter credential fail-closed behavior, lint and container build. This does not by itself certify whole-system production conformance.
