-- PostgreSQL initialization script for saas-template
-- This file is executed on first database creation

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant permissions (the app will create tables via Alembic migrations)
GRANT ALL PRIVILEGES ON DATABASE saas_template TO postgres;
