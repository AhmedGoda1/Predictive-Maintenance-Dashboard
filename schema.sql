-- Track machines
CREATE TABLE IF NOT EXISTS machines (
    machine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    location TEXT
);

-- Store time-series sensor data
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    machine_id TEXT NOT NULL,
    vibration REAL NOT NULL,
    temperature REAL NOT NULL,
    current REAL NOT NULL,
    FOREIGN KEY (machine_id) REFERENCES machines (machine_id)
);

-- Index for fast queries by machine and time
CREATE INDEX IF NOT EXISTS idx_sensor_machine_time 
ON sensor_readings (machine_id, timestamp);

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