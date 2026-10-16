"""PostgreSQL durable result repository; JSON payload retains source provenance."""

import json
import os

import psycopg

from ucos_core.agents.research.contracts import EvidenceItem, ResearchRequest


class PostgresResearchRepository:
    async def save(self, request: ResearchRequest, status: str, analysis: str,
                   evidence: list[EvidenceItem]) -> None:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        payload = json.dumps([item.model_dump(mode="json") for item in evidence])
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=3) as conn:
            await conn.execute(
                """INSERT INTO ucos_research_runs
                   (request_id, correlation_id, tenant_id, workspace_id, brand_id,
                    workflow_id, workflow_step_id, query_text, status, analysis_text, evidence_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (request_id) DO NOTHING""",
                (request.request_id, request.correlation_id, request.tenant_id,
                 request.workspace_id, request.brand_id, request.workflow_id,
                 request.workflow_step_id, request.query, status, analysis, payload),
            )
