-- Esquema de la memoria transaccional de InsurAgent.
-- Escrito en SQL portable: los mismos DDL corren en SQLite (PoC local) y, con
-- SERIAL/TIMESTAMPTZ en lugar de TEXT, en el PostgreSQL de Cloud SQL (PRD §4.2).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    rfc           TEXT NOT NULL UNIQUE,
    curp          TEXT NOT NULL UNIQUE,
    phone         TEXT NOT NULL,
    email         TEXT NOT NULL,
    city          TEXT NOT NULL,
    policy_number TEXT NOT NULL UNIQUE,
    coverage_type TEXT NOT NULL CHECK (coverage_type IN ('basica', 'amplia', 'rc')),
    policy_start  TEXT NOT NULL,
    policy_end    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_customers_policy ON customers (policy_number);

CREATE TABLE IF NOT EXISTS vehicles (
    vin         TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    brand       TEXT NOT NULL,
    model       TEXT NOT NULL,
    year        INTEGER NOT NULL,
    plates      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vehicles_customer ON vehicles (customer_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id               TEXT PRIMARY KEY,
    customer_id            TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    policy_number          TEXT NOT NULL,
    incident_type          TEXT NOT NULL,
    incident_date          TEXT NOT NULL,
    location               TEXT NOT NULL,
    description            TEXT NOT NULL,
    third_parties_involved INTEGER NOT NULL DEFAULT 0,
    deductible_quoted_mxn  REAL,
    created_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_customer ON claims (customer_id);

-- Metadata de la evidencia. El binario vive en disco (PRD §6.5); aquí sólo la ruta.
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id     TEXT NOT NULL REFERENCES claims (claim_id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    stored_path  TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    uploaded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence (claim_id);

-- Memoria de largo plazo: historial conversacional persistente (PRD §3.2).
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    run_id      TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    route       TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_customer ON conversation_turns (customer_id, turn_id);
