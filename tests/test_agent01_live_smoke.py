"""Safety tests for the explicitly opt-in live smoke-test command."""
from scripts.verify_agent01_live import main


def test_live_smoke_requires_explicit_confirmation(capsys):
    result = main(["--query", "non-sensitive verification query"])
    captured = capsys.readouterr()
    assert result == 2
    assert "No network or database calls made" in captured.err


def test_live_smoke_rejects_insecure_remote_endpoint(monkeypatch, capsys):
    monkeypatch.setenv("UCOS_AGENT01_BASE_URL", "http://external.example")
    result = main(["--confirm-live", "--query", "non-sensitive verification query"])
    captured = capsys.readouterr()
    assert result == 2
    assert "must be HTTPS" in captured.err


def test_live_smoke_requires_read_only_verification_database(monkeypatch, capsys):
    monkeypatch.setenv("UCOS_AGENT01_BASE_URL", "https://agent01.example")
    monkeypatch.setenv("UCOS_RESEARCH_API_TOKEN", "test-token")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_TENANT_ID", "tenant")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("UCOS_RESEARCH_SCOPE_BRAND_ID", "brand")
    monkeypatch.delenv("UCOS_AGENT01_VERIFY_DATABASE_URL", raising=False)
    result = main(["--confirm-live", "--query", "non-sensitive verification query"])
    captured = capsys.readouterr()
    assert result == 2
    assert "configuration is incomplete" in captured.err
