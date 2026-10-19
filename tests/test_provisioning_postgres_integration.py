"""Real PostgreSQL integration tests for idempotent scope provisioning.

CI supplies TEST_DATABASE_URL pointing at an ephemeral PostgreSQL service.
These tests do not use the application's DATABASE_URL or production systems.
"""
import os
import pathlib
import uuid

import psycopg
import pytest

from ucos_core.provisioning import disable_scope, provision_scope

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL not configured"
)
ACTOR = "provisioning-integration-test"


@pytest.fixture(scope="module", autouse=True)
def migrated_database():
    assert DATABASE_URL
    root = pathlib.Path(__file__).resolve().parents[1]
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        for migration in sorted((root / "migrations").glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
    yield


def fetch_one(query: str, params: tuple):
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(query, params).fetchone()


def test_same_key_retry_returns_same_scope_without_duplicate_grants_or_audit():
    key = f"provisioning-retry-{uuid.uuid4()}"
    first = provision_scope(DATABASE_URL, ACTOR, key)
    second = provision_scope(DATABASE_URL, ACTOR, key)

    assert second == first
    grant = fetch_one(
        """SELECT enabled FROM ucos_research_scope_grants
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        first,
    )
    grant_count = fetch_one(
        """SELECT count(*) FROM ucos_research_scope_grants
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        first,
    )[0]
    audit_count = fetch_one(
        """SELECT count(*) FROM ucos_scope_provisioning_audit
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s
             AND action = 'SCOPE_CREATED'""",
        first,
    )[0]
    request_count = fetch_one(
        """SELECT count(*) FROM ucos_scope_provisioning_requests
           WHERE idempotency_key = %s AND actor = %s
             AND tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        (key, ACTOR, *first),
    )[0]

    assert grant == (True,)
    assert grant_count == 1
    assert audit_count == 1
    assert request_count == 1


def test_same_key_cannot_be_reused_by_another_actor():
    key = f"provisioning-actor-{uuid.uuid4()}"
    scope = provision_scope(DATABASE_URL, ACTOR, key)

    with pytest.raises(ValueError, match="different actor"):
        provision_scope(DATABASE_URL, "different-operator", key)

    assert fetch_one(
        """SELECT count(*) FROM ucos_research_scope_grants
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        scope,
    )[0] == 1
    assert fetch_one(
        """SELECT count(*) FROM ucos_scope_provisioning_audit
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        scope,
    )[0] == 1


def test_retry_of_revoked_scope_fails_closed_and_audits_revocation():
    key = f"provisioning-revoked-{uuid.uuid4()}"
    scope = provision_scope(DATABASE_URL, ACTOR, key)

    disable_scope(DATABASE_URL, ACTOR, *scope)

    with pytest.raises(ValueError, match="disabled scope"):
        provision_scope(DATABASE_URL, ACTOR, key)

    assert fetch_one(
        """SELECT enabled FROM ucos_research_scope_grants
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        scope,
    ) == (False,)
    actions = fetch_one(
        """SELECT array_agg(action ORDER BY audit_id)
           FROM ucos_scope_provisioning_audit
           WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s""",
        scope,
    )[0]
    assert actions == ["SCOPE_CREATED", "GRANT_DISABLED"]
