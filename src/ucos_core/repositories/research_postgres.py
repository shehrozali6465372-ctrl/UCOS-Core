"""PostgreSQL durable result repository with leased, fenced request claims."""

import json
import os

import psycopg

from ucos_core.agents.research.contracts import (
    EvidenceItem,
    ResearchRequest,
    ResearchResponse,
    ResearchTaskResponse,
)


class ResearchIdempotencyConflict(RuntimeError):
    """A request_id was reused for a different research request."""


class ResearchRequestInProgress(RuntimeError):
    """A matching request is currently owned by a live worker lease."""


class PostgresResearchRepository:
    @staticmethod
    def _database_url() -> str:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return database_url

    @staticmethod
    def _validate_request(row: tuple, request: ResearchRequest) -> None:
        expected = (
            request.correlation_id, request.tenant_id, request.workspace_id, request.brand_id,
            request.workflow_id, request.workflow_step_id, request.query, request.max_results,
        )
        # Legacy rows predate max_results persistence. A NULL value means the
        # original value is unknowable, so validate all known inputs and replay
        # the stored result instead of inventing a mismatch.
        known_inputs_match = tuple(row[:7]) == expected[:7]
        max_results_matches = row[7] is None or row[7] == expected[7]
        if not known_inputs_match or not max_results_matches:
            raise ResearchIdempotencyConflict(
                "request_id is already associated with different request inputs"
            )

    @staticmethod
    def _response(request: ResearchRequest, row: tuple) -> ResearchResponse:
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

    async def claim(self, request: ResearchRequest) -> int | ResearchResponse:
        """Atomically claim a request ID or replay/reject an existing request."""
        async with await psycopg.AsyncConnection.connect(
            self._database_url(), connect_timeout=3
        ) as conn:
            async with conn.transaction():
                inserted = await conn.execute(
                    """INSERT INTO ucos_research_runs
                       (request_id, correlation_id, tenant_id, workspace_id, brand_id,
                        workflow_id, workflow_step_id, query_text, max_results, status,
                        analysis_text, evidence_json, claim_expires_at, claim_generation)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'IN_PROGRESS',
                               '', '[]'::jsonb, now() + interval '5 minutes', 1)
                       ON CONFLICT (request_id) DO NOTHING
                       RETURNING claim_generation""",
                    (request.request_id, request.correlation_id, request.tenant_id,
                     request.workspace_id, request.brand_id, request.workflow_id,
                     request.workflow_step_id, request.query, request.max_results),
                )
                inserted_row = await inserted.fetchone()
                if inserted_row is not None:
                    return int(inserted_row[0])

                cursor = await conn.execute(
                    """SELECT correlation_id, tenant_id, workspace_id, brand_id,
                              workflow_id, workflow_step_id, query_text, max_results,
                              status, analysis_text, evidence_json, claim_expires_at,
                              claim_generation
                       FROM ucos_research_runs WHERE request_id = %s FOR UPDATE""",
                    (request.request_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("request claim disappeared during conflict resolution")
                self._validate_request(row, request)
                if row[8] in ("SUCCEEDED", "NO_RESULTS"):
                    return self._response(request, row)
                if row[8] != "IN_PROGRESS":
                    raise RuntimeError("unsupported persisted research status")

                takeover = await conn.execute(
                    """UPDATE ucos_research_runs
                       SET claim_generation = claim_generation + 1,
                           claim_expires_at = now() + interval '5 minutes'
                       WHERE request_id = %s AND claim_generation = %s
                         AND (
                             claim_expires_at IS NULL
                             OR claim_expires_at <= now()
                         )
                       RETURNING claim_generation""",
                    (request.request_id, row[12]),
                )
                takeover_row = await takeover.fetchone()
                if takeover_row is None:
                    raise ResearchRequestInProgress("a live claim already exists")
                return int(takeover_row[0])

    async def release(self, request: ResearchRequest, generation: int) -> None:
        """Expire a failed worker's own lease without disturbing a newer owner.

        The generation predicate fences stale workers. A concurrent retry can
        take over only after this update commits and will receive a new generation.
        """
        async with await psycopg.AsyncConnection.connect(
            self._database_url(), connect_timeout=3
        ) as conn:
            await conn.execute(
                """UPDATE ucos_research_runs
                   SET claim_expires_at = now() - interval '1 second'
                   WHERE request_id = %s AND tenant_id = %s AND workspace_id = %s
                     AND brand_id = %s AND status = 'IN_PROGRESS'
                     AND claim_generation = %s""",
                (request.request_id, request.tenant_id, request.workspace_id,
                 request.brand_id, generation),
            )

    async def save(
        self,
        request: ResearchRequest,
        generation: int,
        status: str,
        analysis: str,
        evidence: list[EvidenceItem],
    ) -> None:
        if status not in ("SUCCEEDED", "NO_RESULTS"):
            raise ValueError("invalid terminal research status")
        payload = json.dumps([item.model_dump(mode="json") for item in evidence])
        async with await psycopg.AsyncConnection.connect(
            self._database_url(), connect_timeout=3
        ) as conn:
            cursor = await conn.execute(
                """UPDATE ucos_research_runs
                   SET status = %s, analysis_text = %s, evidence_json = %s::jsonb,
                       claim_expires_at = NULL
                   WHERE request_id = %s AND tenant_id = %s AND workspace_id = %s
                     AND brand_id = %s AND status = 'IN_PROGRESS'
                     AND claim_generation = %s""",
                (status, analysis, payload, request.request_id, request.tenant_id,
                 request.workspace_id, request.brand_id, generation),
            )
            if cursor.rowcount != 1:
                raise ResearchIdempotencyConflict(
                    "request claim was superseded or is no longer writable"
                )


    async def get_result(
        self,
        request_id: str,
        tenant_id: str,
        workspace_id: str,
        brand_id: str,
    ) -> ResearchTaskResponse | None:
        """Read only a result inside the exact configured project authorization tuple."""
        async with await psycopg.AsyncConnection.connect(
            self._database_url(), connect_timeout=3
        ) as conn:
            cursor = await conn.execute(
                """SELECT correlation_id, status, analysis_text, evidence_json, created_at
                   FROM ucos_research_runs
                   WHERE request_id = %s AND tenant_id = %s
                     AND workspace_id = %s AND brand_id = %s""",
                (request_id, tenant_id, workspace_id, brand_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        evidence_payload = row[3]
        if isinstance(evidence_payload, str):
            evidence_payload = json.loads(evidence_payload)
        evidence = [EvidenceItem.model_validate(item) for item in evidence_payload]
        return ResearchTaskResponse(
            request_id=request_id,
            correlation_id=row[0],
            status=row[1],
            analysis=row[2],
            evidence=evidence,
            created_at=row[4],
            persisted=True,
        )
