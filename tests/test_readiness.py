from fastapi.testclient import TestClient

from ucos_core import main
from ucos_core.readiness import DependencyStatus, evaluate_readiness


def test_readiness_requires_both_postgres_and_redis():
    ready, components = evaluate_readiness(
        postgres=DependencyStatus(configured=True, available=True),
        redis=DependencyStatus(configured=True, available=False),
    )
    assert not ready
    assert components == {"postgres": True, "redis": False}


def test_unconfigured_dependencies_are_not_ready():
    ready, components = evaluate_readiness(
        postgres=DependencyStatus(configured=False, available=False),
        redis=DependencyStatus(configured=True, available=True),
    )
    assert not ready
    assert components["postgres"] is False


def test_liveness_does_not_depend_on_databases(monkeypatch):
    monkeypatch.setattr(main, "required_dependencies_ready", lambda: (False, {"postgres": False, "redis": False}))
    with TestClient(main.app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
