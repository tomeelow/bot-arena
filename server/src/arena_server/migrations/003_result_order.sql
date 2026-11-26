-- The order results were recorded in, which is the order ratings were applied in. A rebuild
-- must replay that order; match ids don't give it, because the queue claims by priority first.
ALTER TABLE results ADD COLUMN seq INTEGER;

-- Results recorded before this column existed: the best evidence left is when each finished.
UPDATE results SET seq = (
    SELECT count(*) FROM results r
    WHERE (r.finished_at, r.match_id) <= (results.finished_at, results.match_id)
);

CREATE UNIQUE INDEX results_seq ON results (seq);

-- SQLite can't add a NOT NULL column to a table with rows, so enforce it here instead.
CREATE TRIGGER results_seq_required BEFORE INSERT ON results WHEN NEW.seq IS NULL
BEGIN
    SELECT RAISE(ABORT, 'results.seq is required: the order ratings are applied in');
END;
