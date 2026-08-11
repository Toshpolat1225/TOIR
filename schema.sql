-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'user', -- e.g., 'user', 'manager', 'admin'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Departments table
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    color VARCHAR(7),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sections table (can be the same as departments or a sub-unit)
CREATE TABLE IF NOT EXISTS sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fixed Assets (e.g., locomotives)
CREATE TABLE IF NOT EXISTS fixed_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    asset_type VARCHAR(100),
    depot VARCHAR(255),
    mileage NUMERIC(10, 2) DEFAULT 0,
    last_maint_date DATE,
    -- ML fields
    failure_probability REAL,
    health_score REAL,
    predicted_failure_km NUMERIC(10, 2),
    last_ml_update TIMESTAMPTZ,
    -- Wialon fields
    wialon_id VARCHAR(100),
    wialon_last_sync TIMESTAMPTZ,
    wialon_speed REAL,
    wialon_online BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Nomenclature (materials and parts)
CREATE TABLE IF NOT EXISTS nomenclature (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100),
    unit VARCHAR(50) NOT NULL DEFAULT 'шт.',
    department_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    extra JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, name)
);

-- Work Orders
CREATE TABLE IF NOT EXISTS work_orders (
    id VARCHAR(50) PRIMARY KEY, -- Using text as per existing logic e.g., "НЗ-20240726-105301"
    fixed_asset_id UUID REFERENCES fixed_assets(id) ON DELETE SET NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    section_id UUID REFERENCES sections(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- e.g., pending, in_progress, completed, cancelled
    priority VARCHAR(50) DEFAULT 'normal',
    repair_kind VARCHAR(100),
    description TEXT,
    date_start DATE,
    date_end DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TMC Documents (material requirements)
CREATE TABLE IF NOT EXISTS tmc_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_no VARCHAR(50) UNIQUE NOT NULL,
    doc_date DATE NOT NULL,
    work_order_id VARCHAR(50) REFERENCES work_orders(id) ON DELETE SET NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft', -- e.g., draft, issued, closed
    items JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add basic indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_fixed_assets_name ON fixed_assets(name);
CREATE INDEX IF NOT EXISTS idx_nomenclature_name ON nomenclature(name);
CREATE INDEX IF NOT EXISTS idx_work_orders_fixed_asset_id ON work_orders(fixed_asset_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_tmc_documents_work_order_id ON tmc_documents(work_order_id);