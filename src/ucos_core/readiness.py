"""Dependency configuration and readiness evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    configured: bool
    available: bool

    @property
    def ready(self) -> bool:
        return self.configured and self.available


def evaluate_readiness(
    *,
    postgres: DependencyStatus,
    redis: DependencyStatus,
) -> tuple[bool, dict[str, bool]]:
    """Production readiness requires both PostgreSQL and Redis to be configured and reachable."""
    components = {"postgres": postgres.ready, "redis": redis.ready}
    return all(components.values()), components
