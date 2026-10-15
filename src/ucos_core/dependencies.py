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


def required_dependencies_ready() -> tuple[bool, dict[str, bool]]:
    from ucos_core.readiness import DependencyStatus, evaluate_readiness

    postgres = probe_postgres()
    cache = probe_redis()
    return evaluate_readiness(
        postgres=DependencyStatus(postgres.configured, postgres.available),
        redis=DependencyStatus(cache.configured, cache.available),
    )


def production_environment() -> bool:
    return os.getenv("UCOS_ENV", "development").strip().casefold() == "production"
