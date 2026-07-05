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
├── oracle/                       Sanctions feed, threshold sharing, timelock disclosure, revocation, SEP-8, claimable balance, clawback, anchor KYC bridge
├── crypto/                       Standalone cryptography demos (e.g. toy Paillier homomorphic encryption)
├── folding/                      Illustrative recursive-proof (IVC/folding) simulation
├── dashboard/                    No-code compliance rule builder + audit dashboard (HTML/CSS/JS demo)
├── brand/                        Reso logo, wordmark, and brand glyph assets (SVG)
├── docs/ARCHITECTURE.md          Full base system architecture and data flow
└── docs/features/                Advanced feature specs (see below)
```

## Advanced features

`docs/features/` specifies eleven hard, research-grade extensions — six general cryptographic techniques and five built directly on Stellar's own native primitives and published roadmap:

**General (1–6):** recursive proof folding, threshold sanctions oracle, time-locked disclosure, real-time revocation, FHE-encrypted limits, formal verification.

**Stellar-native (7–11):**
7. [SEP-8 regulated assets](docs/features/07-sep8-regulated-assets.md) — plug into Stellar's existing compliance-approval standard.
8. [Claimable balance escrow](docs/features/08-claimable-balance-escrow.md) — hold payments safely instead of rejecting them outright.
9. [Clawback-triggered revocation](docs/features/09-clawback-revocation-integration.md) — recover funds from confirmed bad actors, with a contest window safeguard.
10. [Post-quantum readiness](docs/features/10-post-quantum-readiness.md) — crypto-agile for Stellar's own upcoming ML-DSA signature support.
11. [Anchor-network KYC bridging](docs/features/11-anchor-kyc-bridging.md) — reuse KYC people already completed at a Stellar anchor, instead of asking them to redo it.

Of these, **#11 and #8 are the ones that most directly solve a problem for ordinary people** rather than institutions — see `docs/features/README.md` for the full ranked breakdown.

Honesty note: these build on real, cited research, standards, and existing systems — not a claim that any single technique is unprecedented. The differentiation is combining them into one Stellar/Soroban compliance product.

## Status: scaffold, not production

The contract is written but not compiled (no local Rust/Soroban toolchain was available when this was authored). The oracle, dashboard, and feature demos are runnable with plain Node.js and use real, correct logic (Shamir secret sharing, Merkle accumulators, Miller-Rabin-verified Paillier encryption, Stellar predicate-tree simulation). The core ZK proof step is specified in `circuits/sanctions_proof/CIRCUIT_SPEC.md` but simulated, not implemented with a real proving system. Features that reference real Stellar operations (claimable balances, clawback, SEP-8) simulate the decision logic in plain JS since this sandbox cannot install the Stellar SDK.

## Next steps

1. Install `rustup`, `cargo`, and `soroban-cli`; run `soroban contract build` on `contracts/compliance_hook`.
2. Replace the ZK proof stub in the contract with a real verifier call using Stellar's native `pairing_check` host function (CAP-0074, CAP-0075).
3. Implement the circuit spec in Noir, compile to Groth16/PLONK, and wire it to the oracle's Merkle root.
4. Install `stellar-sdk` and wire the SEP-8, claimable balance, and clawback demos to real Stellar transactions/operations.
5. Start with feature #11 (anchor KYC bridging) or #8 (claimable balance escrow) — the two features that most directly help real users — and move them from spec to a real Soroban/anchor integration.
6. Deploy to Stellar testnet, then pursue hackathon bounties, an SDF ecosystem grant, and paid SEP-0057 integration work with early issuers.
