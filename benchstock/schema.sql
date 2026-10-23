-- Private Bench Stock SQLite schema (single user, no accounts)
-- Category ids keep the original ecDB numbering: subcategory id = category id * 100 + n
-- (e.g. 1204 = Transistor / NPN), so old links and the imported data stay valid.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS category (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subcategory (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES category(id),
    name        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_subcategory_category ON subcategory(category_id);

-- Preferences as key/value pairs (e.g. currency)
CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS component (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    subcategory_id INTEGER NOT NULL REFERENCES subcategory(id),
    manufacturer   TEXT NOT NULL DEFAULT '',
    package        TEXT NOT NULL DEFAULT '',
    pins           INTEGER,                         -- NULL = unknown
    smd            INTEGER NOT NULL DEFAULT 0,      -- 0/1
    scrap          INTEGER NOT NULL DEFAULT 0,      -- 0/1 ("Recycled")
    quantity       NUMERIC NOT NULL DEFAULT 0,
    order_quantity NUMERIC NOT NULL DEFAULT 0,
    price          REAL,                            -- NULL = unknown
    location       TEXT NOT NULL DEFAULT '',
    datasheet      TEXT NOT NULL DEFAULT '',        -- file name in sheets/
    appnote        TEXT NOT NULL DEFAULT '',        -- file name in appnotes/
    image          TEXT NOT NULL DEFAULT '',        -- file name in img/parts/
    comment        TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_component_subcat ON component(subcategory_id);

CREATE TABLE IF NOT EXISTS project (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_component (
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    component_id INTEGER NOT NULL REFERENCES component(id) ON DELETE CASCADE,
    quantity     NUMERIC NOT NULL DEFAULT 1,
    PRIMARY KEY (project_id, component_id)
);
