from unittest.mock import patch

from ucos_core import provisioning


def test_provisioning_requires_confirmation(capsys) -> None:
    result = provisioning.main([])
    captured = capsys.readouterr()
    assert result == 2
    assert "No changes made" in captured.err


def test_provisioning_requires_database_url(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_ACTOR", "owner-operator")
    monkeypatch.delenv("UCOS_PROVISIONING_DATABASE_URL", raising=False)
    result = provisioning.main(["--confirm"])
    captured = capsys.readouterr()
    assert result == 2
    assert "UCOS_PROVISIONING_DATABASE_URL is required" in captured.err


def test_provisioning_requires_actor(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_DATABASE_URL", "postgresql://unused")
    monkeypatch.delenv("UCOS_PROVISIONING_ACTOR", raising=False)
    result = provisioning.main(["--confirm"])
    captured = capsys.readouterr()
    assert result == 2
    assert "UCOS_PROVISIONING_ACTOR is required" in captured.err


def test_provisioning_prints_ids_only_after_transaction_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("UCOS_PROVISIONING_ACTOR", "owner-operator")
    expected = ("tenant", "workspace", "brand")
    with patch.object(provisioning, "provision_scope", return_value=expected):
        result = provisioning.main(["--confirm"])
    captured = capsys.readouterr()
    assert result == 0
    assert "UCOS_RESEARCH_SCOPE_TENANT_ID=tenant" in captured.out
    assert "UCOS_RESEARCH_SCOPE_WORKSPACE_ID=workspace" in captured.out
    assert "UCOS_RESEARCH_SCOPE_BRAND_ID=brand" in captured.out


def test_provision_scope_uses_parameterized_sql_and_transaction() -> None:
    class FakeConnection:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return self

        def execute(self, query, params):
            self.statements.append((query, params))
            return self

    fake = FakeConnection()
    with patch.object(provisioning.psycopg, "connect", return_value=fake):
        ids = provisioning.provision_scope("postgresql://unused", "operator-test")
    assert len(ids) == 3
    assert all(len(value) == 36 for value in ids)
    assert len(fake.statements) == 2
    assert fake.statements[0][1] == ids
    assert fake.statements[1][1] == ("operator-test", *ids)
