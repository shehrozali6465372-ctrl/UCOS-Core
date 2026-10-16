"""Fail-closed tenant authorization adapter backed by PostgreSQL."""

import os

import psycopg


class PostgresResearchAuthorizer:
    async def authorize(self, tenant_id: str, workspace_id: str, brand_id: str) -> bool:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=3) as conn:
            cursor = await conn.execute(
                """SELECT 1 FROM ucos_research_scope_grants
                   WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s
                     AND enabled = TRUE LIMIT 1""",
                (tenant_id, workspace_id, brand_id),
            )
            return await cursor.fetchone() is not None
