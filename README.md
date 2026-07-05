# Reso

Privacy-preserving compliance-as-a-service for stablecoin/token issuers on the Stellar network. Reso proves a transaction is KYC'd, not sanctioned, and within limits — without exposing user identity or balances on-chain.

> Status: early-stage starter scaffold. See `docs/ARCHITECTURE.md` for the base design and `docs/features/README.md` for advanced, research-grade extensions. Not yet compiled, audited, or deployed.

## Why this, why now

- Stellar's **SEP-0057** (2026) defines a standard "compliance hook" interface for Soroban tokens. It's brand new; no polished reference implementation exists yet.
- **Protocol 25 ("X-Ray")** added native zero-knowledge primitives to Stellar (BN254 pairing checks, Poseidon hashing), and **SLP-4** cut Soroban contract costs by roughly 70%, making per-transaction ZK verification commercially viable for the first time.
- Regulation (e.g. the GENIUS Act) requires stablecoin issuers to run AML/KYC programs, but public blockchains expose every transaction publicly. Issuers need to prove compliance without deanonymizing users.

## Repository layout

```
.
├── contracts/compliance_hook/    Soroban Rust contract implementing the SEP-0057 hook interface
│   └── src/verification.rs       Formal verification (Kani) proof harness specs
├── circuits/sanctions_proof/     ZK circuit design spec (non-membership proof against a sanctions list)
├── oracle/                       Sanctions feed, threshold secret sharing, timelock disclosure, revocation registry
├── crypto/                       Standalone cryptography demos (e.g. toy Paillier homomorphic encryption)
├── folding/                      Illustrative recursive-proof (IVC/folding) simulation
├── dashboard/                    No-code compliance rule builder + audit dashboard (HTML/CSS/JS demo)
├── brand/                        Reso logo, wordmark, and brand glyph assets (SVG)
├── docs/ARCHITECTURE.md          Full base system architecture and data flow
└── docs/features/                Advanced, research-grade feature specs (see below)
```

## Advanced features

Beyond the base compliance hook, `docs/features/` specifies six hard, research-grade extensions, most with a working Node.js proof-of-concept for the underlying cryptographic primitive:

1. [Recursive proof folding](docs/features/01-recursive-proof-folding.md) — constant-cost verification regardless of transaction history length.
2. [Threshold sanctions oracle](docs/features/02-threshold-sanctions-oracle.md) — no single party can unilaterally control the sanctions list.
3. [Time-locked regulator disclosure](docs/features/03-timelock-disclosure.md) — lawful disclosure with due process, not a permanent backdoor.
4. [Real-time credential revocation](docs/features/04-realtime-revocation.md) — revocation takes effect on the very next transaction, not after a batch delay.
5. [FHE-encrypted spending limits](docs/features/05-fhe-spending-limits.md) — even the running spending total stays encrypted.
6. [Formally verified contract](docs/features/06-formal-verification.md) — mathematically proven safety properties, not just an audit.

Honesty note (see `docs/features/README.md` for the full version): these build on real, cited research and existing systems. The genuine differentiation is combining them into one Stellar/Soroban compliance product — not a claim that the underlying cryptography itself has never been seen before.

## Status: scaffold, not production

The contract is written but not compiled (no local Rust/Soroban toolchain was available when this was authored). The oracle, dashboard, and advanced-feature demos are runnable with plain Node.js and use real, correct cryptographic math (Shamir secret sharing, Merkle accumulators, Miller-Rabin-verified Paillier encryption). The core ZK proof step itself is specified in `circuits/sanctions_proof/CIRCUIT_SPEC.md` but simulated, not implemented with a real proving system.

## Next steps

1. Install `rustup`, `cargo`, and `soroban-cli`; run `soroban contract build` on `contracts/compliance_hook`.
2. Replace the ZK proof stub in the contract with a real verifier call using Stellar's native `pairing_check` host function (CAP-0074, CAP-0075).
3. Implement the circuit spec in Noir, compile to Groth16/PLONK, and wire it to the oracle's Merkle root.
4. Connect the dashboard to the oracle and contract via Soroban RPC / Stellar Horizon.
5. Pick one advanced feature (start with threshold oracle or real-time revocation — the most tractable) and move it from spec to a real Soroban integration.
6. Deploy to Stellar testnet, then pursue hackathon bounties, an SDF ecosystem grant, and paid SEP-0057 integration work with early issuers.
