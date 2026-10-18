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


def required_dependencies_ready() -> tuple[bool, dict[str, bool]]:
    from ucos_core.readiness import DependencyStatus, evaluate_readiness

    postgres = probe_postgres()
    cache = probe_redis()
    scope_grant = probe_research_scope()
    ready, components = evaluate_readiness(
        postgres=DependencyStatus(postgres.configured, postgres.available),
        redis=DependencyStatus(cache.configured, cache.available),
    )

    # Readiness is also a configuration safety gate: don't accept traffic when
    # authentication, the single authorized scope, or provider credentials are absent.
    token_configured = bool(os.getenv("UCOS_RESEARCH_API_TOKEN", "").strip())
    scope_names = (
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
    )
    components["research_auth"] = token_configured
    components["research_scope"] = scope_grant.ready
    components["tavily"] = bool(os.getenv("TAVILY_API_KEY", "").strip())
    components["analysis_model"] = bool(
        os.getenv("ANALYSIS_API_KEY", "").strip()
        and os.getenv("ANALYSIS_MODEL", "gpt-4.1-mini").strip()
        and os.getenv("ANALYSIS_BASE_URL", "https://api.openai.com/v1").strip()
    )
    return ready and all(components.values()), components


def production_environment() -> bool:
    return os.getenv("UCOS_ENV", "development").strip().casefold() == "production"
