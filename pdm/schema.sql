-- Asset-agnostic schema: any equipment type, any set of sensor channels.

-- What kinds of equipment exist and how they are described
CREATE TABLE IF NOT EXISTS asset_types (
    type_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age_unit TEXT NOT NULL,          -- unit of age and RUL for this type: s, cycle, ...
    config TEXT                      -- JSON: thresholds and limits from the registry
);

CREATE TABLE IF NOT EXISTS channel_defs (
    type_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    unit TEXT,
    kind TEXT NOT NULL,              -- sensor | condition (operating condition, not a health signal)
    description TEXT,
    health TEXT,                     -- how the channel feeds the health index (NULL = not used)
    PRIMARY KEY (type_id, channel),
    FOREIGN KEY (type_id) REFERENCES asset_types (type_id)
);

-- Individual pieces of equipment
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    type_id TEXT NOT NULL,
    name TEXT NOT NULL,
    site TEXT,
    source TEXT,                     -- where the data came from (dataset, gateway, ...)
    metadata TEXT,                   -- JSON
    FOREIGN KEY (type_id) REFERENCES asset_types (type_id)
);

-- One row per time step of an asset; the values live in `measurements`
CREATE TABLE IF NOT EXISTS readings (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    age REAL NOT NULL,               -- time since the asset started, in the type's age_unit
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id)
);
CREATE INDEX IF NOT EXISTS idx_readings_asset_age ON readings (asset_id, age);

-- Long format: new sensors need no schema change
CREATE TABLE IF NOT EXISTS measurements (
    reading_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (reading_id, channel),
    FOREIGN KEY (reading_id) REFERENCES readings (reading_id)
) WITHOUT ROWID;

-- Failure of an asset. observed = 0 when the failure lies beyond the recorded data
-- but its time is known from a label (benchmark test sets). Ground truth for RUL.
CREATE TABLE IF NOT EXISTS failure_events (
    asset_id TEXT PRIMARY KEY,
    ts DATETIME NOT NULL,
    age REAL NOT NULL,
    mode TEXT,
    observed INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id)
);

-- Named periods of an asset's life (operating phases, maintenance windows, ...)
CREATE TABLE IF NOT EXISTS segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_ts DATETIME NOT NULL,
    end_ts DATETIME NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id)
);

-- Model output per reading
CREATE TABLE IF NOT EXISTS health_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    age REAL NOT NULL,
    drift REAL NOT NULL,             -- deviation from the healthy baseline (0 = healthy)
    health_score REAL NOT NULL,      -- 0-100
    status TEXT NOT NULL,            -- Healthy / Warning / Critical / Failed
    top_driver TEXT,                 -- channel contributing most to the deviation
    method TEXT,                     -- how rul_pred was produced (see models.kind)
    rul_pred REAL,                   -- estimated remaining life in age units
    rul_low REAL,                    -- lower / upper bound of the prediction interval
    rul_high REAL,
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id)
);
CREATE INDEX IF NOT EXISTS idx_health_asset_age ON health_scores (asset_id, age);

CREATE TABLE IF NOT EXISTS maintenance_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    status_level TEXT NOT NULL,
    detected_issue TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id)
);

-- Trained models and how they were evaluated
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    type_id TEXT NOT NULL,
    kind TEXT NOT NULL,              -- learned | single_run_experimental | ...
    source TEXT,                     -- training data
    trained_at DATETIME,
    artifact_path TEXT,
    params TEXT,                     -- JSON
    metrics TEXT,                    -- JSON
    FOREIGN KEY (type_id) REFERENCES asset_types (type_id)
);

-- Scalar evaluation numbers shown on the dashboard (scope = asset_id or model_id)
CREATE TABLE IF NOT EXISTS metrics (
    scope TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (scope, name)
);
