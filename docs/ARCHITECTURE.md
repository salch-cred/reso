# Architecture

## Actors

- **Issuer**: a company issuing a stablecoin/token on Stellar (e.g. a MoneyGram-style MGUSD issuer, an anchor, an RWA platform).
- **Compliance Officer**: a non-technical staff member at the issuer who configures rules via the dashboard.
- **User**: a wallet holder transacting in the issuer's token.
- **Regulator/Auditor**: reviews aggregate compliance evidence without seeing individual user data.

## Data flow

1. **Rule configuration**: Compliance Officer uses the no-code dashboard to define rules (e.g. "block sanctioned wallets", "cap daily transfer at $10,000", "require KYC tier 2 above $1,000"). Rules are stored and compiled into circuit parameters.
2. **Sanctions/KYC data ingestion**: The oracle service periodically pulls a sanctions/PEP list (simulated here) and KYC attestations, builds a Merkle tree, and publishes the current Merkle root on-chain (or to a location the contract can read).
3. **Proof generation**: When a User initiates a transfer, their wallet (or a client-side proving service) generates a zero-knowledge proof that:
   - their address is NOT in the current sanctions Merkle tree (non-membership proof), AND
   - they hold a valid KYC credential of the required tier, AND
   - the transaction amount is within their configured limit.
   None of the underlying identity data or exact balance is revealed — only that the proof is valid.
4. **On-chain verification**: The Soroban compliance hook contract (SEP-0057-style) verifies the proof using Stellar's native pairing-check host functions before allowing the token transfer to proceed.
5. **Audit reporting**: The dashboard aggregates verification events (pass/fail counts, thresholds triggered) into a regulator-facing report — without ever exposing which specific user triggered which event.

## Why Stellar specifically

- **Protocol 25 "X-Ray"**: native BN254 pairing operations + Poseidon hashing make ZK proof verification a first-class, low-level operation instead of an expensive custom implementation.
- **SLP-4**: cut non-refundable Soroban resource costs and roughly halved/quartered typical invocation costs, making per-transaction ZK verification commercially viable.
- **Anchor network**: 170+ country cash-in/cash-out network means KYC/compliance attestations can eventually be tied to real-world onboarding points, not just crypto-native wallets.

## Components in this repo, mapped to the flow above

| Step | Component |
|------|-----------|
| Rule configuration | `dashboard/index.html` (no-code rule builder) |
| Sanctions ingestion + Merkle root | `oracle/sanctions-feed.js` |
| Proof generation (spec) | `circuits/sanctions_proof/CIRCUIT_SPEC.md` |
| On-chain verification | `contracts/compliance_hook/src/lib.rs` |
| Audit reporting | `dashboard/index.html` (audit tab) |
