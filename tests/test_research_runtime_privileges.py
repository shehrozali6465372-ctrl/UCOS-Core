"""Regression tests for runtime database permissions required by Agent 01."""

from unittest.mock import MagicMock, patch

import pytest

from ucos_core.dependencies import probe_research_runtime_privileges


@pytest.mark.parametrize(
    "privileges",
    [
        (True, True, True, True),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, False, True),
        (True, True, True, False),
    ],
)
def test_runtime_privilege_probe_fails_closed_if_any_required_grant_is_missing(
    monkeypatch, privileges
):
    database_url = "postgresql://probe-test.invalid/database"
    monkeypatch.setenv("DATABASE_URL", database_url)

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = privileges

    with patch("psycopg.connect", return_value=connection) as connect:
        result = probe_research_runtime_privileges()

    connect.assert_called_once_with(database_url, connect_timeout=2)
    assert result.configured is True
    assert result.available is all(privileges)


def test_runtime_privilege_probe_fails_closed_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = probe_research_runtime_privileges()

    assert result.configured is False
    assert result.available is False
