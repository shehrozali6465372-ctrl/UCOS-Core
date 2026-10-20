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
    result = provisioning.main(["--confirm", "--idempotency-key", "setup-1"])
    captured = capsys.readouterr()
    assert result == 2
    assert "UCOS_PROVISIONING_DATABASE_URL is required" in captured.err


def test_provisioning_requires_actor(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_DATABASE_URL", "postgresql://unused")
    monkeypatch.delenv("UCOS_PROVISIONING_ACTOR", raising=False)
    result = provisioning.main(["--confirm", "--idempotency-key", "setup-1"])
    captured = capsys.readouterr()
    assert result == 2
    assert "UCOS_PROVISIONING_ACTOR is required" in captured.err


def test_creation_requires_idempotency_key(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("UCOS_PROVISIONING_ACTOR", "owner-operator")
    result = provisioning.main(["--confirm"])
    captured = capsys.readouterr()
    assert result == 2
    assert "--idempotency-key is required" in captured.err


def test_provisioning_prints_ids_only_after_transaction_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UCOS_PROVISIONING_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("UCOS_PROVISIONING_ACTOR", "owner-operator")
    expected = ("tenant", "workspace", "brand")
    with patch.object(provisioning, "provision_scope", return_value=expected) as provision:
        result = provisioning.main(["--confirm", "--idempotency-key", "setup-1"])
    captured = capsys.readouterr()
    assert result == 0
    provision.assert_called_once_with("postgresql://unused", "owner-operator", "setup-1")
    assert "UCOS_RESEARCH_SCOPE_TENANT_ID=tenant" in captured.out
    assert "UCOS_RESEARCH_SCOPE_WORKSPACE_ID=workspace" in captured.out
    assert "UCOS_RESEARCH_SCOPE_BRAND_ID=brand" in captured.out


def test_provision_scope_creates_grant_and_audit_atomically() -> None:
    class FakeCursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

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
            if "INSERT INTO ucos_scope_provisioning_requests" in " ".join(query.split()):
                return FakeCursor(params[2:5])
            return FakeCursor(None)

    fake = FakeConnection()
    with patch.object(provisioning.psycopg, "connect", return_value=fake):
        ids = provisioning.provision_scope(
            "postgresql://unused", "operator-test", "initial-setup-1"
        )
    assert len(ids) == 3
    assert all(len(value) == 36 for value in ids)
    assert len(fake.statements) == 3
    assert fake.statements[0][1] == ("initial-setup-1", "operator-test", *ids)
    assert fake.statements[1][1] == ids
    assert fake.statements[2][1] == ("operator-test", *ids)


def test_provision_scope_retry_returns_same_scope_without_duplicate_writes() -> None:
    class FakeCursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

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
            normalized = " ".join(query.split())
            if "INSERT INTO ucos_scope_provisioning_requests" in normalized:
                return FakeCursor(None)
            if normalized.startswith("SELECT request.actor,"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand", True))
            if normalized.startswith("SELECT actor, tenant_id, workspace_id, brand_id"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand"))
            if normalized.startswith("SELECT enabled FROM ucos_research_scope_grants"):
                return FakeCursor((True,))
            raise AssertionError("unexpected SQL")

    fake = FakeConnection()
    with patch.object(provisioning.psycopg, "connect", return_value=fake):
        ids = provisioning.provision_scope(
            "postgresql://unused", "operator-test", "initial-setup-1"
        )
    assert ids == ("tenant", "workspace", "brand")
    assert len(fake.statements) == 3
    assert "SELECT actor, tenant_id, workspace_id, brand_id" in (
        " ".join(fake.statements[1][0].split())
    )
    assert "SELECT enabled FROM ucos_research_scope_grants" in (
        " ".join(fake.statements[2][0].split())
    )


def test_provision_scope_rejects_idempotency_key_owned_by_another_actor() -> None:
    class FakeCursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return self

        def execute(self, query, _params):
            normalized = " ".join(query.split())
            if "INSERT INTO ucos_scope_provisioning_requests" in normalized:
                return FakeCursor(None)
            if normalized.startswith("SELECT request.actor,"):
                return FakeCursor(("different-operator", "tenant", "workspace", "brand", True))
            if normalized.startswith("SELECT actor, tenant_id, workspace_id, brand_id"):
                return FakeCursor(("different-operator", "tenant", "workspace", "brand"))
            raise AssertionError("different actor must be rejected before grant lookup")

    with patch.object(provisioning.psycopg, "connect", return_value=FakeConnection()):
        try:
            provisioning.provision_scope(
                "postgresql://unused", "operator-test", "initial-setup-1"
            )
        except ValueError as exc:
            assert "different actor" in str(exc)
        else:
            raise AssertionError("a key owned by another actor must not be reused")


def test_disable_scope_updates_grant_and_audits_atomically() -> None:
    class FakeCursor:
        def fetchone(self):
            return ("tenant",)

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
            return FakeCursor()

    fake = FakeConnection()
    with patch.object(provisioning.psycopg, "connect", return_value=fake):
        provisioning.disable_scope(
            "postgresql://unused",
            "operator-test",
            "tenant",
            "workspace",
            "brand",
        )
    assert len(fake.statements) == 2
    assert fake.statements[0][1] == ("tenant", "workspace", "brand")
    assert fake.statements[1][1] == ("operator-test", "tenant", "workspace", "brand")


def test_disable_scope_refuses_missing_or_already_disabled_grant() -> None:
    class FakeCursor:
        def fetchone(self):
            return None

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return self

        def execute(self, _query, _params):
            return FakeCursor()

    with patch.object(provisioning.psycopg, "connect", return_value=FakeConnection()):
        try:
            provisioning.disable_scope(
                "postgresql://unused", "operator-test", "tenant", "workspace", "brand"
            )
        except ValueError as exc:
            assert "does not exist or is already disabled" in str(exc)
        else:
            raise AssertionError("missing grant must not be reported as disabled")


def test_provision_scope_fails_closed_when_ledger_exists_without_grant() -> None:
    class FakeCursor:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def transaction(self):
            return self
        def execute(self, query, _params):
            normalized = " ".join(query.split())
            if "INSERT INTO ucos_scope_provisioning_requests" in normalized:
                return FakeCursor(None)
            if normalized.startswith("SELECT request.actor,"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand", True))
            if normalized.startswith("SELECT actor, tenant_id, workspace_id, brand_id"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand"))
            if normalized.startswith("SELECT enabled FROM ucos_research_scope_grants"):
                return FakeCursor(None)
            raise AssertionError("unexpected SQL")

    with patch.object(provisioning.psycopg, "connect", return_value=FakeConnection()):
        try:
            provisioning.provision_scope("postgresql://unused", "operator-test", "orphaned-key")
        except RuntimeError as exc:
            assert "operator reconciliation required" in str(exc)
        else:
            raise AssertionError("orphaned ledger must fail closed")


def test_provision_scope_refuses_reenabling_disabled_grant() -> None:
    class FakeCursor:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def transaction(self):
            return self
        def execute(self, query, _params):
            normalized = " ".join(query.split())
            if "INSERT INTO ucos_scope_provisioning_requests" in normalized:
                return FakeCursor(None)
            if normalized.startswith("SELECT request.actor,"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand", True))
            if normalized.startswith("SELECT actor, tenant_id, workspace_id, brand_id"):
                return FakeCursor(("operator-test", "tenant", "workspace", "brand"))
            if normalized.startswith("SELECT enabled FROM ucos_research_scope_grants"):
                return FakeCursor((False,))
            raise AssertionError("unexpected SQL")

    with patch.object(provisioning.psycopg, "connect", return_value=FakeConnection()):
        try:
            provisioning.provision_scope("postgresql://unused", "operator-test", "revoked-key")
        except ValueError as exc:
            assert "disabled scope" in str(exc)
        else:
            raise AssertionError("retry must not reenable a disabled scope")
