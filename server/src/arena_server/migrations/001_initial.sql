-- Phase 4 schema. Results are the source of truth; ratings are derived from them (Phase 5).

CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    github_id   INTEGER UNIQUE,              -- NULL only for the built-in "arena" account
    handle      TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE bots (                          -- a lineage of versions
    id          INTEGER PRIMARY KEY,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_id, name)
);

CREATE TABLE bot_versions (
    id          INTEGER PRIMARY KEY,
    bot_id      INTEGER NOT NULL REFERENCES bots(id),
    n           INTEGER NOT NULL,            -- 1, 2, 3, ... within the bot
    code        TEXT NOT NULL,               -- "sha256:<hex>" in the code store, or "builtin:<name>"
    parent_id   INTEGER REFERENCES bot_versions(id),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'active', 'rejected', 'retired')),
    error       TEXT,                        -- why validation rejected it, shown to the owner
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bot_id, n)
);

CREATE TABLE matches (
    id              INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('placement', 'ranked', 'comparison')),
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'done', 'void')),
    seed            INTEGER NOT NULL,
    engine_version  TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    worker_id       TEXT,
    lease_until     REAL,                    -- unix time; a running match past it is reaped
    void_reason     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT
);
CREATE INDEX matches_queue ON matches (status, priority DESC, id);

CREATE TABLE match_players (
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    seat            INTEGER NOT NULL CHECK (seat IN (0, 1)),
    bot_version_id  INTEGER NOT NULL REFERENCES bot_versions(id),
    PRIMARY KEY (match_id, seat)
);

CREATE TABLE results (
    match_id        INTEGER PRIMARY KEY REFERENCES matches(id),
    winner_seat     INTEGER CHECK (winner_seat IN (0, 1)),   -- NULL is a draw
    end_reason      TEXT NOT NULL,
    turns           INTEGER NOT NULL,
    replay_sha256   TEXT NOT NULL,
    finished_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ratings (                       -- derived, rebuildable from results (Phase 5)
    bot_version_id  INTEGER PRIMARY KEY REFERENCES bot_versions(id),
    mu              REAL NOT NULL,
    sigma           REAL NOT NULL,
    games           INTEGER NOT NULL
);
