"""Explicit operator-run provisioning and revocation for Agent 01 scopes.

Create a scope:
  UCOS_PROVISIONING_DATABASE_URL=... UCOS_PROVISIONING_ACTOR=... \
  python -m ucos_core.provisioning --confirm

Disable a scope:
  UCOS_PROVISIONING_DATABASE_URL=... UCOS_PROVISIONING_ACTOR=... \
  python -m ucos_core.provisioning --disable TENANT_ID WORKSPACE_ID BRAND_ID --confirm

This is a controlled operator command, not a public admin API.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

import psycopg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or disable an Agent 01 scope grant as an operator."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="required to write the grant and audit record to PostgreSQL",
    )
    parser.add_argument(
        "--disable",
        nargs=3,
        metavar=("TENANT_ID", "WORKSPACE_ID", "BRAND_ID"),
        help="disable an existing grant instead of creating a new UUID scope",
    )
    return parser


def provision_scope(database_url: str, actor: str) -> tuple[str, str, str]:
    """Create a UUID-based single-owner scope and audit it in one transaction."""
    tenant_id, workspace_id, brand_id = (str(uuid.uuid4()) for _ in range(3))
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO ucos_research_scope_grants
                    (tenant_id, workspace_id, brand_id, enabled)
                VALUES (%s, %s, %s, TRUE)
                """,
                (tenant_id, workspace_id, brand_id),
            )
            conn.execute(
                """
                INSERT INTO ucos_scope_provisioning_audit
                    (actor, action, tenant_id, workspace_id, brand_id)
                VALUES (%s, 'SCOPE_CREATED', %s, %s, %s)
                """,
                (actor, tenant_id, workspace_id, brand_id),
            )
    return tenant_id, workspace_id, brand_id


def disable_scope(
    database_url: str,
    actor: str,
    tenant_id: str,
    workspace_id: str,
    brand_id: str,
) -> None:
    """Disable an existing grant and write its audit event atomically."""
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        with conn.transaction():
            cursor = conn.execute(
                """
                UPDATE ucos_research_scope_grants
                SET enabled = FALSE
                WHERE tenant_id = %s AND workspace_id = %s AND brand_id = %s
                  AND enabled = TRUE
                RETURNING tenant_id
                """,
                (tenant_id, workspace_id, brand_id),
            )
            if cursor.fetchone() is None:
                raise ValueError("scope grant does not exist or is already disabled")
            conn.execute(
                """
                INSERT INTO ucos_scope_provisioning_audit
                    (actor, action, tenant_id, workspace_id, brand_id)
                VALUES (%s, 'GRANT_DISABLED', %s, %s, %s)
                """,
                (actor, tenant_id, workspace_id, brand_id),
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm:
        print(
            "No changes made. Review the provisioning instructions, then rerun with --confirm.",
            file=sys.stderr,
        )
        return 2

    database_url = os.getenv("UCOS_PROVISIONING_DATABASE_URL", "").strip()
    actor = os.getenv("UCOS_PROVISIONING_ACTOR", "").strip()
    if not database_url:
        print("UCOS_PROVISIONING_DATABASE_URL is required.", file=sys.stderr)
        return 2
    if not actor:
        print("UCOS_PROVISIONING_ACTOR is required.", file=sys.stderr)
        return 2

    try:
        if args.disable:
            disable_scope(database_url, actor, *args.disable)
            print("Scope grant disabled and audit event recorded.")
            return 0
        tenant_id, workspace_id, brand_id = provision_scope(database_url, actor)
    except Exception:
        # Avoid printing exception details that may contain connection data.
        print(
            "Provisioning failed. Check migrations, database permissions, and scope IDs.",
            file=sys.stderr,
        )
        return 1

    print("Scope created. Save these identifiers in your approved deployment record:")
    print(f"UCOS_RESEARCH_SCOPE_TENANT_ID={tenant_id}")
    print(f"UCOS_RESEARCH_SCOPE_WORKSPACE_ID={workspace_id}")
    print(f"UCOS_RESEARCH_SCOPE_BRAND_ID={brand_id}")
    print("Configure these values in Render only after reviewing the grant and deployment plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
