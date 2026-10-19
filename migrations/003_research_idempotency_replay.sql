ALTER TABLE ucos_research_runs
    ADD COLUMN IF NOT EXISTS max_results integer
        CHECK (max_results BETWEEN 1 AND 10);

-- Historical rows did not persist max_results, so their original value is
-- unknowable. Keep it NULL for those rows instead of fabricating a value.
-- Current application inserts always supply max_results explicitly.
ALTER TABLE ucos_research_runs
    ALTER COLUMN max_results DROP NOT NULL,
    ALTER COLUMN max_results DROP DEFAULT;
