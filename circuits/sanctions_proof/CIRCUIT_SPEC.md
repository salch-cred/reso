# ZK Circuit Spec: Sanctions Non-Membership + KYC Tier + Limit Proof

Status: design spec only. Hand this to a ZK engineer or implement in Noir, targeting Stellar's native BN254/Poseidon host functions (Protocol 25 "X-Ray").

## Public inputs

- `sanctions_root`: Bytes32 — current Merkle root of the sanctions/PEP list (published on-chain by the oracle).
- `min_kyc_tier`: u32 — required KYC tier from the issuer's rule set.
- `amount`: i128 — the transaction amount (can be public; only identity/history stays private).
- `daily_limit`: i128 — issuer's configured daily cap.

## Private witness (never revealed)

- `identity_commitment`: Poseidon hash of the user's KYC-verified identity attributes.
- `kyc_tier`: the user's actual KYC tier (must be >= `min_kyc_tier`).
- `merkle_path`: sibling hashes proving `identity_commitment` is absent from the sanctions tree (non-membership path).
- `prior_daily_volume`: user's running total for the day (must be known to the prover, e.g. tracked client-side or by a wallet-side helper service).

## Circuit constraints

1. **Non-membership**: recompute the Merkle path from `identity_commitment` using Poseidon hashing and assert the resulting root does NOT equal any leaf under `sanctions_root` (standard ZK non-membership pattern: prove the leaf at the claimed position differs from `identity_commitment`, combined with a sorted/indexed Merkle tree).
2. **KYC tier check**: assert `kyc_tier >= min_kyc_tier`.
3. **Limit check**: assert `prior_daily_volume + amount <= daily_limit`.
4. Output a single boolean (encoded as a BN254 pairing check result) that the Soroban contract verifies on-chain.

## Recommended implementation path

1. Prototype the circuit in **Noir** (`nargo`), which has existing Stellar/Soroban integration examples.
2. Compile to a Groth16 or PLONK proof.
3. Use Stellar's native `pairing_check` and Poseidon host functions (CAP-0074 / CAP-0075) inside the Soroban verifier instead of a general-purpose EVM-style verifier contract — this is what makes per-transaction verification cheap post-SLP-4.
4. Benchmark proof generation time on a mobile/light client; if too slow, consider a delegated proving service.
