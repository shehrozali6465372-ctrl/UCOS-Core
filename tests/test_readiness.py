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
    monkeypatch.setattr(
        main,
        "required_dependencies_ready",
        lambda: (False, {"postgres": False, "redis": False}),
    )
    with TestClient(main.app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_readiness_fails_closed_without_auth_scope_or_provider_config(monkeypatch):
    from ucos_core.dependencies import ProbeResult

    monkeypatch.setattr(
        "ucos_core.dependencies.probe_postgres",
        lambda: ProbeResult(True, True),
    )
    monkeypatch.setattr(
        "ucos_core.dependencies.probe_redis",
        lambda: ProbeResult(True, True),
    )
    for name in (
        "UCOS_RESEARCH_API_TOKEN",
        "UCOS_RESEARCH_SCOPE_TENANT_ID",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID",
        "UCOS_RESEARCH_SCOPE_BRAND_ID",
        "TAVILY_API_KEY",
        "ANALYSIS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANALYSIS_MODEL", raising=False)
    monkeypatch.delenv("ANALYSIS_BASE_URL", raising=False)

    from ucos_core.dependencies import required_dependencies_ready

    ready, components = required_dependencies_ready()
    assert not ready
    assert components["postgres"] is True
    assert components["redis"] is True
    assert components["research_auth"] is False
    assert components["research_scope"] is False
    assert components["tavily"] is False
    assert components["analysis_model"] is False


def test_readiness_passes_configuration_gate_when_all_values_exist(monkeypatch):
    from ucos_core.dependencies import ProbeResult, required_dependencies_ready

    monkeypatch.setattr(
        "ucos_core.dependencies.probe_postgres",
        lambda: ProbeResult(True, True),
    )
    monkeypatch.setattr(
        "ucos_core.dependencies.probe_redis",
        lambda: ProbeResult(True, True),
    )
    monkeypatch.setattr(
        "ucos_core.dependencies.probe_research_scope",
        lambda: ProbeResult(True, True),
    )
    monkeypatch.setattr(
        "ucos_core.dependencies.probe_research_schema",
        lambda: ProbeResult(True, True),
    )
    values = {
        "UCOS_RESEARCH_API_TOKEN": "agent01-test-token-0123456789-abcdef-0123456789",
        "UCOS_RESEARCH_SCOPE_TENANT_ID": "tenant",
        "UCOS_RESEARCH_SCOPE_WORKSPACE_ID": "workspace",
        "UCOS_RESEARCH_SCOPE_BRAND_ID": "brand",
        "TAVILY_API_KEY": "test-tavily",
        "ANALYSIS_API_KEY": "test-analysis",
        "ANALYSIS_MODEL": "test-model",
        "ANALYSIS_BASE_URL": "https://example.invalid/v1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    ready, components = required_dependencies_ready()
    assert ready
    assert all(components.values())
