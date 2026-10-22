"""Regression tests for runtime database permissions required by Agent 01."""

from unittest.mock import MagicMock, patch

import pytest

from ucos_core.dependencies import probe_research_runtime_privileges


@pytest.mark.parametrize("altered_index", [None, *range(14)])
def test_runtime_privilege_probe_enforces_required_and_least_privilege_grants(
    monkeypatch, altered_index
):
    database_url = "postgresql://probe-test.invalid/database"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("UCOS_ENV", "production")

    # SELECT/INSERT/UPDATE on research runs and SELECT on scope grants are
    # required. Every other table-level privilege is forbidden in production.
    privileges = [True, True, True, True] + [False] * 10
    if altered_index is not None:
        privileges[altered_index] = altered_index >= 4

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = tuple(privileges)

    with patch("psycopg.connect", return_value=connection) as connect:
        result = probe_research_runtime_privileges()

    connect.assert_called_once_with(database_url, connect_timeout=2)
    assert result.configured is True
    assert result.available is (altered_index is None)


def test_runtime_privilege_probe_fails_closed_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = probe_research_runtime_privileges()

    assert result.configured is False
    assert result.available is False


def test_development_can_use_owner_privileges(monkeypatch):
    database_url = "postgresql://probe-test.invalid/database"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("UCOS_ENV", "development")

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (True,) * 14

    with patch("psycopg.connect", return_value=connection):
        result = probe_research_runtime_privileges()

    assert result.configured is True
    assert result.available is True
