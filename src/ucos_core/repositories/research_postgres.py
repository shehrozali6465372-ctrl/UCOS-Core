"""PostgreSQL durable result repository; JSON payload retains source provenance."""

import json
import os

import psycopg

from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest, ResearchResponse


class ResearchIdempotencyConflict(RuntimeError):
    """A request_id was reused for a different research request."""


class PostgresResearchRepository:
    async def get_existing(self, request: ResearchRequest) -> ResearchResponse | None:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=3) as conn:
            cursor = await conn.execute(
                """SELECT correlation_id, tenant_id, workspace_id, brand_id,
                          workflow_id, workflow_step_id, query_text, max_results,
                          status, analysis_text, evidence_json
                   FROM ucos_research_runs WHERE request_id = %s""",
                (request.request_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            expected = (
                request.correlation_id, request.tenant_id, request.workspace_id, request.brand_id,
                request.workflow_id, request.workflow_step_id, request.query, request.max_results,
            )
            actual = tuple(row[:8])
            if actual != expected:
                raise ResearchIdempotencyConflict(
                    "request_id is already associated with different request inputs"
                )
            evidence_payload = row[10]
            if isinstance(evidence_payload, str):
                evidence_payload = json.loads(evidence_payload)
            evidence = [EvidenceItem.model_validate(item) for item in evidence_payload]
            return ResearchResponse(
                request_id=request.request_id,
                correlation_id=row[0],
                status=row[8],
                analysis=row[9],
                evidence=evidence,
                persisted=True,
            )

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
                    workflow_id, workflow_step_id, query_text, max_results, status,
                    analysis_text, evidence_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (request_id) DO NOTHING
                   RETURNING request_id""",
                (request.request_id, request.correlation_id, request.tenant_id,
                 request.workspace_id, request.brand_id, request.workflow_id,
                 request.workflow_step_id, request.query, request.max_results,
                 status, analysis, payload),
            )
            if await cursor.fetchone() is not None:
                return
            # A competing insert may have completed while providers ran. Never
            # overwrite it; validate input identity in the next durable lookup.
            await conn.commit()
            raise ResearchIdempotencyConflict("request_id was concurrently inserted")
