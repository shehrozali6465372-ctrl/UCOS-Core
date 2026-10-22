"""Runtime dependency probes; credentials/URLs are never returned in API responses."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProbeResult:
    configured: bool
    available: bool


def _configured_url(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def probe_postgres() -> ProbeResult:
    url = _configured_url("DATABASE_URL")
    if not url:
        return ProbeResult(configured=False, available=False)
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
        return ProbeResult(configured=True, available=True)
    except Exception:
        return ProbeResult(configured=True, available=False)


def probe_redis() -> ProbeResult:
    url = _configured_url("REDIS_URL")
    if not url:
        return ProbeResult(configured=False, available=False)
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        try:
            return ProbeResult(configured=True, available=bool(client.ping()))
        finally:
            client.close()
    except Exception:
        return ProbeResult(configured=True, available=False)


def probe_research_scope() -> ProbeResult:
    """Verify the configured single scope has an enabled database authorization grant."""
    names = (
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
    )
    scope = tuple(os.getenv(name, "").strip() for name in names)
    if not all(scope):
        return ProbeResult(configured=False, available=False)
    database_url = _configured_url("DATABASE_URL")
    if not database_url:
        return ProbeResult(configured=True, available=False)
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            cursor = connection.execute(
                """SELECT 1 FROM ucos_research_scope_grants
                   WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s
                     AND enabled = TRUE LIMIT 1""",
                scope,
            )
            allowed = cursor.fetchone() is not None
        return ProbeResult(configured=True, available=allowed)
    except Exception:
        return ProbeResult(configured=True, available=False)



def probe_research_schema() -> ProbeResult:
    """Verify the durable claim/replay schema is present before accepting traffic."""
    database_url = _configured_url("DATABASE_URL")
    if not database_url:
        return ProbeResult(configured=False, available=False)
    required_columns = {
        "request_id", "correlation_id", "tenant_id", "workspace_id", "brand_id",
        "workflow_id", "workflow_step_id", "query_text", "max_results", "status",
        "analysis_text", "evidence_json", "claim_expires_at", "claim_generation",
    }
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            cursor = connection.execute(
                """SELECT column_name
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'ucos_research_runs'
                     AND column_name = ANY(%s)""",
                (list(required_columns),),
            )
            present_columns = {row[0] for row in cursor.fetchall()}
            constraint = connection.execute(
                """SELECT pg_get_constraintdef(oid)
                   FROM pg_constraint
                   WHERE conrelid = 'public.ucos_research_runs'::regclass
                     AND conname = 'ucos_research_runs_status_check'
                     AND contype = 'c'"""
            ).fetchone()
        status_constraint_ready = bool(
            constraint
            and all(
                status in constraint[0]
                for status in ("IN_PROGRESS", "SUCCEEDED", "NO_RESULTS")
            )
        )
        available = required_columns <= present_columns and status_constraint_ready
        return ProbeResult(configured=True, available=available)
    except Exception:
        return ProbeResult(configured=True, available=False)


def probe_research_runtime_privileges() -> ProbeResult:
    """Verify the runtime role can perform every database operation used by Agent 01."""
    database_url = _configured_url("DATABASE_URL")
    if not database_url:
        return ProbeResult(configured=False, available=False)
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            privileges = connection.execute(
                """SELECT
                       has_table_privilege(
                           current_user, 'public.ucos_research_runs', 'SELECT'
                       ),
                       has_table_privilege(
                           current_user, 'public.ucos_research_runs', 'INSERT'
                       ),
                       has_table_privilege(
                           current_user, 'public.ucos_research_runs', 'UPDATE'
                       ),
                       has_table_privilege(
                           current_user, 'public.ucos_research_scope_grants', 'SELECT'
                       )"""
            ).fetchone()
        return ProbeResult(
            configured=True,
            available=bool(privileges and all(privileges)),
        )
    except Exception:
        return ProbeResult(configured=True, available=False)


def required_dependencies_ready() -> tuple[bool, dict[str, bool]]:
    from ucos_core.readiness import DependencyStatus, evaluate_readiness

    postgres = probe_postgres()
    cache = probe_redis()
    scope_grant = probe_research_scope()
    research_schema = probe_research_schema()
    ready, components = evaluate_readiness(
        postgres=DependencyStatus(postgres.configured, postgres.available),
        redis=DependencyStatus(cache.configured, cache.available),
    )

    # Readiness is also a configuration safety gate: don't accept traffic when
    # authentication, the single authorized scope, or provider credentials are absent.
    token = os.getenv("UCOS_RESEARCH_API_TOKEN", "").strip()
    # Match the API authentication gate so readiness never advertises a short
    # configured token as safe for production traffic.
    token_configured = len(token) >= 32
    components["research_auth"] = token_configured
    components["research_scope"] = scope_grant.configured and scope_grant.available
    components["research_schema"] = research_schema.configured and research_schema.available
    runtime_privileges = probe_research_runtime_privileges()
    components["research_runtime_privileges"] = (
        runtime_privileges.configured and runtime_privileges.available
    )
    components["tavily"] = bool(os.getenv("TAVILY_API_KEY", "").strip())
    # Match the analyzer's actual endpoint validation. A non-empty URL is not
    # sufficient: remote endpoints must use HTTPS and must not embed credentials,
    # query strings, or fragments. Loopback HTTP is allowed for local development.
    from ucos_core.integrations.endpoint_policy import is_safe_analysis_base_url

    analysis_base_url = os.getenv(
        "ANALYSIS_BASE_URL", "https://api.openai.com/v1"
    ).strip().rstrip("/")
    analysis_endpoint_safe = is_safe_analysis_base_url(
        analysis_base_url,
        production=production_environment(),
    )
    components["analysis_model"] = bool(
        os.getenv("ANALYSIS_API_KEY", "").strip()
        and os.getenv("ANALYSIS_MODEL", "gpt-4.1-mini").strip()
        and analysis_endpoint_safe
    )
    return ready and all(components.values()), components


def production_environment() -> bool:
    return os.getenv("UCOS_ENV", "development").strip().casefold() == "production"
