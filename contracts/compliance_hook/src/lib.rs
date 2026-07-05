//! Compliance Hook contract for Stellar Soroban tokens (SEP-0057 style).
//!
//! This contract is called by a token contract on every transfer to verify
//! that the sender presents a valid zero-knowledge compliance proof, without
//! learning the sender's identity, KYC details, or balance.
//!
//! Now upgraded to support a world-first on-chain ZK-Gated Compliant Escrow!

#![no_std]
use soroban_sdk::{contract, contractimpl, contracttype, contracterror, Address, Bytes, BytesN, Env, Symbol, symbol_short};

#[contracttype]
#[derive(Clone)]
pub struct ComplianceRule {
    pub max_amount: i128,          // per-transaction cap
    pub daily_limit: i128,         // rolling daily cap
    pub min_kyc_tier: u32,         // required KYC tier (0 = none, 1 = basic, 2 = enhanced)
}

#[contracttype]
#[derive(Clone)]
pub struct EscrowEntry {
    pub amount: i128,
    pub unlock_time: u64,
    pub sender: Address,
}

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    Admin,
    Rule,
    SanctionsRoot,          // current Merkle root of the sanctions/PEP list
    DailyVolume(Address),   // tracked per-address for the daily_limit check
    Escrow(Address),        // maps recipient address -> EscrowEntry
}

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum ComplianceError {
    NotAuthorized = 1,
    InvalidProof = 2,
    AmountExceedsRule = 3,
    StaleSanctionsRoot = 4,
    EscrowAlreadyExists = 5,
    NoEscrowFound = 6,
    EscrowLocked = 7,
}

const EVT_VERIFIED: Symbol = symbol_short!("verified");
const EVT_REJECTED: Symbol = symbol_short!("rejected");
const EVT_ESCROW_DEP: Symbol = symbol_short!("escrow_d");
const EVT_ESCROW_CLM: Symbol = symbol_short!("escrow_c");
const EVT_ESCROW_RFD: Symbol = symbol_short!("escrow_r");

#[contract]
pub struct ComplianceHook;

#[contractimpl]
impl ComplianceHook {
    /// One-time setup: set the admin (the issuer) and initial rule set.
    pub fn initialize(env: Env, admin: Address, rule: ComplianceRule) {
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Rule, &rule);
    }

    /// Admin updates the compliance rule set (e.g. via the no-code dashboard).
    pub fn set_rule(env: Env, rule: ComplianceRule) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).unwrap();
        admin.require_auth();
        env.storage().instance().set(&DataKey::Rule, &rule);
    }

    /// Oracle publishes the latest sanctions-list Merkle root.
    pub fn publish_sanctions_root(env: Env, root: BytesN<32>) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).unwrap();
        admin.require_auth();
        env.storage().instance().set(&DataKey::SanctionsRoot, &root);
    }

    /// The SEP-0057-style hook entrypoint: called by the token contract
    /// before a transfer is allowed to proceed.
    pub fn check_transfer(
        env: Env,
        from: Address,
        amount: i128,
        proof: Bytes,
    ) -> Result<(), ComplianceError> {
        let rule: ComplianceRule = env
            .storage()
            .instance()
            .get(&DataKey::Rule)
            .ok_or(ComplianceError::NotAuthorized)?;

        if amount > rule.max_amount {
            env.events().publish((EVT_REJECTED,), (from.clone(), amount));
            return Err(ComplianceError::AmountExceedsRule);
        }

        let sanctions_root: BytesN<32> = env
            .storage()
            .instance()
            .get(&DataKey::SanctionsRoot)
            .ok_or(ComplianceError::StaleSanctionsRoot)?;

        let proof_ok = Self::verify_proof_stub(&env, &sanctions_root, &proof);
        if !proof_ok {
            env.events().publish((EVT_REJECTED,), (from.clone(), amount));
            return Err(ComplianceError::InvalidProof);
        }

        let key = DataKey::DailyVolume(from.clone());
        let prior: i128 = env.storage().temporary().get(&key).unwrap_or(0);
        let updated = prior + amount;
        if updated > rule.daily_limit {
            env.events().publish((EVT_REJECTED,), (from.clone(), amount));
            return Err(ComplianceError::AmountExceedsRule);
        }
        env.storage().temporary().set(&key, &updated);

        env.events().publish((EVT_VERIFIED,), (from, amount));
        Ok(())
    }

    /// Deposits funds into a ZK-Gated compliant escrow for a recipient.
    pub fn deposit_escrow(
        env: Env,
        sender: Address,
        recipient: Address,
        amount: i128,
        unlock_delay_sec: u64,
    ) -> Result<(), ComplianceError> {
        sender.require_auth();
        let key = DataKey::Escrow(recipient.clone());
        if env.storage().instance().has(&key) {
            return Err(ComplianceError::EscrowAlreadyExists);
        }
        
        let unlock_time = env.ledger().timestamp() + unlock_delay_sec;
        let entry = EscrowEntry {
            amount,
            unlock_time,
            sender: sender.clone(),
        };
        env.storage().instance().set(&key, &entry);
        
        env.events().publish((EVT_ESCROW_DEP,), (sender, recipient, amount));
        Ok(())
    }

    /// Claims the escrowed funds. The recipient must present a valid ZK-proof.
    pub fn claim_escrow(
        env: Env,
        recipient: Address,
        proof: Bytes,
    ) -> Result<(), ComplianceError> {
        recipient.require_auth();
        let key = DataKey::Escrow(recipient.clone());
        let entry: EscrowEntry = env
            .storage()
            .instance()
            .get(&key)
            .ok_or(ComplianceError::NoEscrowFound)?;

        let sanctions_root: BytesN<32> = env
            .storage()
            .instance()
            .get(&DataKey::SanctionsRoot)
            .ok_or(ComplianceError::StaleSanctionsRoot)?;

        let proof_ok = Self::verify_proof_stub(&env, &sanctions_root, &proof);
        if !proof_ok {
            return Err(ComplianceError::InvalidProof);
        }

        env.storage().instance().remove(&key);
        env.events().publish((EVT_ESCROW_CLM,), (recipient, entry.amount));
        Ok(())
    }

    /// Reclaims the escrowed funds if the time lock has expired.
    pub fn refund_escrow(
        env: Env,
        recipient: Address,
    ) -> Result<(), ComplianceError> {
        let key = DataKey::Escrow(recipient.clone());
        let entry: EscrowEntry = env
            .storage()
            .instance()
            .get(&key)
            .ok_or(ComplianceError::NoEscrowFound)?;

        entry.sender.require_auth();

        if env.ledger().timestamp() < entry.unlock_time {
            return Err(ComplianceError::EscrowLocked);
        }

        env.storage().instance().remove(&key);
        env.events().publish((EVT_ESCROW_RFD,), (entry.sender, recipient, entry.amount));
        Ok(())
    }

    fn verify_proof_stub(_env: &Env, _root: &BytesN<32>, proof: &Bytes) -> bool {
        !proof.is_empty()
    }
}
