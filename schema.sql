-- Existing tables (normalEvents and specialEvents)
CREATE TABLE IF NOT EXISTS normalEvents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    time TEXT NOT NULL,
    delay INTEGER NOT NULL DEFAULT 0,
    tone TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    frequency TEXT NOT NULL -- JSON string of weekdays array
);

CREATE TABLE IF NOT EXISTS specialEvents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,      -- in YYYY-MM-DD format
    time TEXT NOT NULL,
    description TEXT NOT NULL,
    tone TEXT DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0
);

-- New ESP32 table replacing old esp32, includes tone column
CREATE TABLE IF NOT EXISTS ESP32 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    time TEXT NOT NULL,
    delay INTEGER NOT NULL DEFAULT 0,
    tone TEXT DEFAULT '',
    source TEXT DEFAULT 'normal'
);
