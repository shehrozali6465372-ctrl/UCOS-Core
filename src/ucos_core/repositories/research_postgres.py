"""PostgreSQL durable result repository; JSON payload retains source provenance."""

import json
import os

import psycopg

from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest


class ResearchIdempotencyConflict(RuntimeError):
    """A request_id was reused for a different research request or result."""


class PostgresResearchRepository:
    async def save(self, request: ResearchRequest, status: str, analysis: str,
                   evidence: list[EvidenceItem]) -> None:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        payload = json.dumps([item.model_dump(mode="json") for item in evidence])
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=3) as conn:
            cursor = await conn.execute(
                """INSERT INTO ucos_research_runs
                   (request_id, correlation_id, tenant_id, workspace_id, brand_id,
                    workflow_id, workflow_step_id, query_text, status, analysis_text, evidence_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (request_id) DO NOTHING
                   RETURNING request_id""",
                (request.request_id, request.correlation_id, request.tenant_id,
                 request.workspace_id, request.brand_id, request.workflow_id,
                 request.workflow_step_id, request.query, status, analysis, payload),
            )
            if await cursor.fetchone() is not None:
                return

            existing = await conn.execute(
                """SELECT correlation_id, tenant_id, workspace_id, brand_id,
                          workflow_id, workflow_step_id, query_text, status,
                          analysis_text, evidence_json
                   FROM ucos_research_runs
                   WHERE request_id = %s""",
                (request.request_id,),
            )
            row = await existing.fetchone()
            if row is None:
                raise RuntimeError("research request persistence conflict could not be reconciled")

            expected = (
                request.correlation_id, request.tenant_id, request.workspace_id, request.brand_id,
                request.workflow_id, request.workflow_step_id, request.query, status, analysis,
            )
            actual = tuple(row[:9])
            stored_evidence = row[9]
            if isinstance(stored_evidence, str):
                stored_evidence = json.loads(stored_evidence)
            if actual != expected or stored_evidence != json.loads(payload):
                raise ResearchIdempotencyConflict(
                    "request_id is already associated with a different research request or result"
                )
