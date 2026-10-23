CREATE TABLE IF NOT EXISTS ucos_research_scope_grants (
    tenant_id text NOT NULL,
    workspace_id text NOT NULL,
    brand_id text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, workspace_id, brand_id)
);

CREATE TABLE IF NOT EXISTS ucos_research_runs (
    request_id text PRIMARY KEY,
    correlation_id text NOT NULL,
    tenant_id text NOT NULL,
    workspace_id text NOT NULL,
    brand_id text NOT NULL,
    workflow_id text NOT NULL,
    workflow_step_id text NOT NULL,
    query_text text NOT NULL,
    status text NOT NULL CHECK (status IN ('SUCCEEDED', 'NO_RESULTS')),
    analysis_text text NOT NULL,
    evidence_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ucos_research_tenant_created
    ON ucos_research_runs (tenant_id, created_at DESC);
