-- Initial database setup for BSAI
-- This runs automatically when PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Create default schema
CREATE SCHEMA IF NOT EXISTS bsai;

-- Set default search path
ALTER DATABASE bsai SET search_path TO bsai, public;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA bsai TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bsai TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bsai TO postgres;

-- Log message
DO $$
BEGIN
  RAISE NOTICE 'BSAI database initialized successfully';
END
$$;
