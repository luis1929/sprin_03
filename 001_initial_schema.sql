-- Optimized schema for ATO Financial WhatsApp Bot
-- Postgres 16 + PostGIS ready

CREATE EXTENSION IF NOT EXISTS postgis;

-- Users/Sessions (phone-based)
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) UNIQUE NOT NULL,
    session_id UUID DEFAULT gen_random_uuid(),
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    user_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active'
);

-- Chat Messages
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    session_id UUID,
    message TEXT NOT NULL,
    role VARCHAR(20) NOT NULL, -- 'user' or 'assistant'
    timestamp TIMESTAMP DEFAULT NOW(),
    flowise_response_time INTEGER, -- ms
    FOREIGN KEY (phone) REFERENCES sessions(phone)
);

-- Stats for optimization
CREATE TABLE IF NOT EXISTS stats (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20),
    date DATE DEFAULT CURRENT_DATE,
    messages_count INTEGER DEFAULT 0,
    avg_response_time INTEGER,
    errors_count INTEGER DEFAULT 0
);

-- Indexes for high perf (80% queries by phone/time)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_phone ON sessions(phone);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_phone_time ON messages(phone, timestamp DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stats_phone_date ON stats(phone, date);

-- Vacuum settings for auto-optimize
ALTER TABLE messages SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE stats SET (autovacuum_vacuum_scale_factor = 0.1);

-- Spatial example if needed (PostGIS)
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20),
    geom GEOMETRY(Point, 4326),
    recorded_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_locations_phone_geom ON locations USING GIST (geom);

