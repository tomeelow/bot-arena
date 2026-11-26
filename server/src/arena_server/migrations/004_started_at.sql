-- When a worker claimed the match: queue wait is started_at - created_at, and match duration
-- is finished_at - started_at (Phase 10 health metrics). NULL for matches claimed before this.
ALTER TABLE matches ADD COLUMN started_at TEXT;
