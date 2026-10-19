-- Durable idempotency ledger for operator scope creation. The key identifies
-- one provisioning intent; reusing it returns the same enabled scope.
CREATE TABLE IF NOT EXISTS ucos_scope_provisioning_requests (
    idempotency_key text PRIMARY KEY
        CHECK (length(btrim(idempotency_key)) BETWEEN 1 AND 200),
    actor text NOT NULL,
    tenant_id text NOT NULL,
    workspace_id text NOT NULL,
    brand_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, workspace_id, brand_id)
);
