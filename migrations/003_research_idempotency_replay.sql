ALTER TABLE ucos_research_runs
    ADD COLUMN IF NOT EXISTS max_results integer NOT NULL DEFAULT 5
        CHECK (max_results BETWEEN 1 AND 10);

-- Existing rows predate max_results persistence. The default of 5 is retained
-- for compatibility; new requests persist their explicit value.
