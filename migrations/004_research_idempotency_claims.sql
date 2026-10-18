ALTER TABLE ucos_research_runs
    DROP CONSTRAINT IF EXISTS ucos_research_runs_status_check;

ALTER TABLE ucos_research_runs
    ADD CONSTRAINT ucos_research_runs_status_check
    CHECK (status IN ('IN_PROGRESS', 'SUCCEEDED', 'NO_RESULTS'));

ALTER TABLE ucos_research_runs
    ADD COLUMN IF NOT EXISTS claim_expires_at timestamptz,
    ADD COLUMN IF NOT EXISTS claim_generation bigint NOT NULL DEFAULT 0;

-- Completed historical rows are unaffected. New requests claim the request_id
-- before provider calls; claim_generation fences workers whose lease expired.
