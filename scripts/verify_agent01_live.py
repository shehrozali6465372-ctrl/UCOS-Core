"""Explicit, opt-in live smoke test for Agent 01 persistence and idempotent replay.

This script makes real provider-backed requests and may incur provider costs.
It never runs unless --confirm-live is supplied.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import httpx
import psycopg

from ucos_core.integrations.endpoint_policy import is_safe_analysis_base_url


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--confirm-live", action="store_true")
    result.add_argument("--query", required=True, help="specific, non-sensitive research query")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.confirm_live:
        print("No network or database calls made; pass --confirm-live to run.", file=sys.stderr)
        return 2

    base_url = os.getenv("UCOS_AGENT01_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("UCOS_RESEARCH_API_TOKEN", "").strip()
    database_url = os.getenv("UCOS_AGENT01_VERIFY_DATABASE_URL", "").strip()
    scope_names = (
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
    )
    scope = tuple(os.getenv(name, "").strip() for name in scope_names)
    if not is_safe_analysis_base_url(base_url, production=False):
        print("UCOS_AGENT01_BASE_URL must be HTTPS (HTTP only for loopback).", file=sys.stderr)
        return 2
    if not token or not database_url or not all(scope):
        print("Live smoke-test configuration is incomplete.", file=sys.stderr)
        return 2

    request_id = str(uuid.uuid4())
    request = {
        "request_id": request_id,
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": scope[0],
        "workspace_id": scope[1],
        "brand_id": scope[2],
        "workflow_id": "agent01-live-smoke",
        "workflow_step_id": str(uuid.uuid4()),
        "query": args.query,
        "max_results": 3,
    }
    endpoint = f"{base_url}/v1/agents/01/research"
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            first = client.post(
                endpoint,
                json=request,
                headers={"Authorization": f"Bearer {token}"},
            )
            first.raise_for_status()
            first_payload = first.json()
            replay = client.post(
                endpoint,
                json=request,
                headers={"Authorization": f"Bearer {token}"},
            )
            replay.raise_for_status()
            replay_payload = replay.json()

        if first_payload.get("persisted") is not True:
            raise RuntimeError("first response did not confirm durable persistence")
        if first_payload.get("status") not in {"SUCCEEDED", "NO_RESULTS"}:
            raise RuntimeError("first response returned an unsupported terminal status")
        if first_payload != replay_payload:
            raise RuntimeError("idempotent replay did not return the same stored response")

        with psycopg.connect(database_url, connect_timeout=5) as connection:
            # Enforce read-only mode in the database session even if the supplied
            # verification credential was accidentally granted write privileges.
            connection.execute("SET TRANSACTION READ ONLY")
            row = connection.execute(
                """SELECT correlation_id, tenant_id, workspace_id, brand_id,
                          workflow_id, workflow_step_id, query_text, max_results,
                          status, analysis_text, evidence_json
                   FROM ucos_research_runs WHERE request_id = %s""",
                (request_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("request result was not found in PostgreSQL")
        expected_evidence = first_payload.get("evidence", [])
        stored_evidence = row[10]
        if isinstance(stored_evidence, str):
            stored_evidence = json.loads(stored_evidence)
        if (
            row[0] != request["correlation_id"]
            or tuple(row[1:4]) != scope
            or row[4] != request["workflow_id"]
            or row[5] != request["workflow_step_id"]
            or row[6] != request["query"]
            or row[7] != request["max_results"]
            or row[8] != first_payload["status"]
            or row[9] != first_payload.get("analysis", "")
            or stored_evidence != expected_evidence
        ):
            raise RuntimeError("persisted PostgreSQL result does not match API response")
    except Exception:
        print(
            "Live smoke test failed. Check endpoint readiness, scope grant, migrations, "
            "provider configuration, and database access; no credentials were printed.",
            file=sys.stderr,
        )
        return 1

    print(
        f"PASS request_id={request_id} status={first_payload['status']} "
        f"evidence_count={len(first_payload.get('evidence', []))} replay_match=true db_match=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
