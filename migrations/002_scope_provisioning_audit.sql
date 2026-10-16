CREATE TABLE IF NOT EXISTS ucos_scope_provisioning_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor text NOT NULL,
    action text NOT NULL CHECK (action IN ('SCOPE_CREATED', 'GRANT_DISABLED')),
    tenant_id text NOT NULL,
    workspace_id text NOT NULL,
    brand_id text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ucos_scope_audit_scope_time
    ON ucos_scope_provisioning_audit
       (tenant_id, workspace_id, brand_id, occurred_at DESC);
