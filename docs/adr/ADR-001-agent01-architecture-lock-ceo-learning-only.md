# ADR-001: Lock Agent 01 Research Architecture and CEO-Only Learning

- Status: Proposed for owner approval
- Scope: UCOS Agent 01 only
- Based on: UCOS Agent 01 Research Intelligence Architecture v1.0 (2026-10-21)
- Decision date: 2026-10-22

## Decision

Lock Agent 01 to the existing Research Intelligence Architecture v1.0. This ADR clarifies the ownership boundary; it does not introduce new agents, services, queues, databases, or architectural subsystems.

**Only the CEO / Super-Intelligence Agent owns the system learning loop. Agent 01 must not implement an independent learning loop, self-improvement loop, outcome-driven adaptive scoring engine, or autonomous strategy update mechanism.**

Agent 01 remains a specialist research capability callable by the CEO. It independently performs the existing research lifecycle: understand the task, plan research, select permitted sources, retrieve and normalize evidence, deduplicate, validate and cross-check, analyze, score transparently for the current task, self-review, synthesize a traceable report, persist authorized research artifacts, and return results/follow-ups.

## Permitted Agent 01 behavior

- Persist authorized task records, source references, evidence/provenance, report outputs, confidence, limitations, and status for reproducibility and audit.
- Apply the current versioned, explainable task-specific scoring rubric to the current research task.
- Return outcome/analytics evidence supplied by an authorized source as research data when relevant to a task, without adapting its own strategy from those outcomes.
- Report unknowns and distinguish verified facts, estimates, inferences, and proxies.
- Expose only capabilities that are actually implemented and permitted by the connected source/API.

## Prohibited Agent 01 behavior

- Owning or running a learning loop.
- Updating its own scoring weights, strategy, model weights, or policies based on engagement, conversion, revenue, or other outcomes.
- Promoting new strategies autonomously.
- Publishing or scheduling content, mutating platform accounts, or modifying another UCOS agent/system under this architecture lock.

## CEO / Super-Intelligence responsibility

The CEO / Super-Intelligence Agent owns cross-agent learning, outcome interpretation, strategy selection, and any system-level decision loop. It may consume Agent 01's evidence-backed findings and authorized outcome data. Any feedback sent back to Agent 01 is a research task/context input; it does not grant Agent 01 authority to self-modify.

## Scoring clarification

Agent 01 may use the existing specification's transparent, task-specific scoring rubric for ranking findings in an individual research report. It must not tune that rubric from post-publication outcomes. Rubric calibration, if desired, belongs to the CEO-owned learning architecture and requires its own approved design and evaluation.

## Production-readiness gate

Architecture approval is not implementation or production-readiness proof. Before release, verify against the exact candidate commit:

1. Current code and API contracts match this boundary.
2. Research task lifecycle, evidence provenance, source validation, confidence/unknown handling, and follow-up behavior have tests.
3. Authentication, scope authorization, idempotency, persistence, rate/deadline controls, prompt-injection/SSRF defenses, and secret redaction are tested.
4. Each platform adapter declares real supported capabilities and limitations; unsupported APIs are not simulated.
5. Product/affiliate fields are sourced and timestamped; sales are not inferred from proxy metrics.
6. Unit, integration, security, and end-to-end tests have recorded results.
7. Deployment and live verification are reported separately; no production rollout occurs without explicit approval and a rollback plan.

## Consequences

- Keep the Agent 01 architecture scope fixed; do not add an Agent 01 learning subsystem.
- Continue implementation by mapping existing code to the locked specification and addressing only verified gaps within Agent 01.
- Preserve the existing service boundary and avoid unrelated agents/shared-system changes.
- This ADR remains proposed until the owner approves it; creating this document does not merge it to main or authorize production changes.
