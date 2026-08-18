-- Схема базы данных для телеметрии Квадросима

-- Таблица сессий (один вылет = одна сессия)
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time REAL NOT NULL,          -- Timestamp начала сессии
    end_time REAL,                     -- Timestamp окончания
    pilot_name TEXT,                   -- ФИО пилота (из HUD)
    total_laps INTEGER DEFAULT 0,      -- Всего кругов
    best_lap_time REAL,                -- Лучшее время круга (мс)
    crash_detected BOOLEAN DEFAULT 0   -- Был ли краш
);

-- Таблица кругов
CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,       -- Номер круга (1, 2, ...)
    start_time REAL NOT NULL,          -- Абсолютное время старта круга
    end_time REAL,                     -- Абсолютное время финиша
    lap_duration REAL,                 -- Длительность круга (мс)
    is_best BOOLEAN DEFAULT 0,         -- Является ли лучшим кругом сессии
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Таблица сырых кадров (телеметрия)
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    lap_number INTEGER,                -- NULL если круг еще не начался
    timestamp REAL NOT NULL,           -- Performance counter
    hud_speed REAL,                    -- км/ч
    hud_altitude REAL,                 -- м
    hud_current_lap_time REAL,         -- мс (текущее время круга)
    hud_best_lap_time REAL,            -- мс
    hud_battery_v REAL,                -- Вольт
    hud_battery_a REAL,                -- Ампер
    stick_throttle REAL,               -- [-1, 1]
    stick_roll REAL,                   -- [-1, 1]
    stick_pitch REAL,                  -- [-1, 1]
    stick_yaw REAL,                    -- [-1, 1]
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Индексы для ускорения выборки при анализе
CREATE INDEX IF NOT EXISTS idx_frames_session ON frames(session_id);
CREATE INDEX IF NOT EXISTS idx_frames_lap ON frames(session_id, lap_number);
CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id);
