-- Supabase Database Schema for Reso Privacy Compliance Console
-- Run this script in the SQL Editor of your Supabase Project.

-- 1. Rules Table
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY,
    max_amount NUMERIC NOT NULL DEFAULT 10000,
    daily_limit NUMERIC NOT NULL DEFAULT 25000,
    min_kyc_tier INT NOT NULL DEFAULT 1,
    sanctions_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default rules if empty
INSERT INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled)
VALUES (1, 10000.0, 25000.0, 1, TRUE)
ON CONFLICT (id) DO NOTHING;

-- 2. Wallets Table
CREATE TABLE IF NOT EXISTS wallets (
    address VARCHAR(100) PRIMARY KEY,
    kyc_tier INT NOT NULL DEFAULT 0,
    is_sanctioned BOOLEAN NOT NULL DEFAULT FALSE,
    name VARCHAR(100) NOT NULL DEFAULT '',
    daily_volume NUMERIC NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert seed wallets
INSERT INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume)
VALUES 
('GCLEANUSERADDRESSTHATISFINE00099', 2, FALSE, 'Alice (Tier 2 User)', 5000.0),
('GBASICKYCUSERADDRESS00000000001', 1, FALSE, 'Bob (Tier 1 User)', 0.0),
('GNOKYCUSERADDRESS000000000000002', 0, FALSE, 'Charlie (No KYC)', 0.0),
('GABC1SANCTIONEDEXAMPLEADDRESS0001', 1, TRUE, 'Sanctioned Entity A', 0.0)
ON CONFLICT (address) DO NOTHING;

-- 3. Escrows Table
CREATE TABLE IF NOT EXISTS escrows (
    recipient VARCHAR(100) PRIMARY KEY,
    sender VARCHAR(100) NOT NULL,
    amount NUMERIC NOT NULL,
    unlock_time BIGINT NOT NULL,
    onchain_tx VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp VARCHAR(50) NOT NULL,
    sender VARCHAR(100) NOT NULL,
    amount NUMERIC NOT NULL,
    rule_checked VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    proof_ref VARCHAR(100) NOT NULL,
    merkle_root VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Seed initial audit log
INSERT INTO audit_logs (timestamp, sender, amount, rule_checked, status, reason, proof_ref, merkle_root)
VALUES (
    TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    'GABC1SANCTIONEDEXAMPLEADDRESS0001',
    250.0,
    'Sanctions screen',
    'blocked',
    'Address is listed on the active sanctions list (proven via non-membership check failure)',
    '0x9f2a24c8b618bc360b0e5d41c888ee11ec9f2a24c8b618bc360b0e5d41c888ee11',
    '0x9f2a24c8b618bc...'
) ON CONFLICT DO NOTHING;
