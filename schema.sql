-- Track machines
CREATE TABLE IF NOT EXISTS machines (
    machine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    location TEXT
);

-- Store time-series sensor data (one row per processed raw recording)
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    machine_id TEXT NOT NULL,
    source_file TEXT,
    phase TEXT,                 -- operating phase of the test run (folder name)
    regime TEXT,                -- supply regime: '3V' (nominal) or '5V' (overstress)
    speed_rpm REAL,
    current REAL,               -- A
    voltage REAL,               -- V
    temp_motor REAL,            -- surface temperature, degC
    temp_ambient REAL,          -- degC
    vib_1x REAL,                -- vibration amplitude at the motor speed (g)
    vib_5x REAL,                -- vibration amplitude at 5x motor speed
    vib_7x REAL,                -- vibration amplitude at 7x motor speed
    vib_band_0_4k REAL,         -- vibration spectrum energy, 0-4 kHz
    vib_band_4_8k REAL,         -- 4-8 kHz
    vib_band_8_16k REAL,        -- 8-16 kHz
    vib_band_16_26k REAL,       -- 16-26 kHz
    is_failed INTEGER NOT NULL DEFAULT 0,  -- 1 once the motor has stopped working
    rul_true_s REAL,            -- ground truth: seconds until failure (known from the run)
    FOREIGN KEY (machine_id) REFERENCES machines (machine_id)
);

-- Index for fast queries by machine and time
CREATE INDEX IF NOT EXISTS idx_sensor_machine_time
ON sensor_readings (machine_id, timestamp);

-- Model output per reading (health index, status, estimated RUL)
CREATE TABLE IF NOT EXISTS health_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    machine_id TEXT NOT NULL,
    drift REAL NOT NULL,        -- deviation from the healthy baseline (0 = healthy)
    health_score REAL NOT NULL, -- 0-100
    status TEXT NOT NULL,       -- Healthy / Warning / Critical / Failed
    top_driver TEXT,            -- feature contributing most to the deviation
    rul_pred_s REAL,            -- estimated seconds until failure
    FOREIGN KEY (machine_id) REFERENCES machines (machine_id)
);

CREATE INDEX IF NOT EXISTS idx_health_machine_time
ON health_scores (machine_id, timestamp);

-- Store alerts and suggested actions
CREATE TABLE IF NOT EXISTS maintenance_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    machine_id TEXT NOT NULL,
    status_level TEXT NOT NULL,
    detected_issue TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    FOREIGN KEY (machine_id) REFERENCES machines (machine_id)
);

-- Model evaluation numbers shown on the dashboard
CREATE TABLE IF NOT EXISTS model_metrics (
    name TEXT PRIMARY KEY,
    value REAL NOT NULL
);
