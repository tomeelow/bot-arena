-- Who asked for which version comparison, so requests can be rate-limited per user.
CREATE TABLE comparisons (
    id              INTEGER PRIMARY KEY,
    requester_id    INTEGER NOT NULL REFERENCES users(id),
    challenger_id   INTEGER NOT NULL REFERENCES bot_versions(id),
    incumbent_id    INTEGER NOT NULL REFERENCES bot_versions(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
