# Reso

Privacy-preserving compliance-as-a-service for stablecoin/token issuers on the Stellar network. Reso proves a transaction is KYC'd, not sanctioned, and within limits — without exposing user identity or balances on-chain.

> Status: early-stage starter scaffold. See `docs/ARCHITECTURE.md` for the full design and `docs/PROJECT_README.md` for build status and next steps. Not yet compiled, audited, or deployed.

## Why this, why now

- Stellar's **SEP-0057** (2026) defines a standard "compliance hook" interface for Soroban tokens. It's brand new; no polished reference implementation exists yet.
- **Protocol 25 ("X-Ray")** added native zero-knowledge primitives to Stellar (BN254 pairing checks, Poseidon hashing), and **SLP-4** cut Soroban contract costs by roughly 70%, making per-transaction ZK verification commercially viable for the first time.
- Regulation (e.g. the GENIUS Act) requires stablecoin issuers to run AML/KYC programs, but public blockchains expose every transaction publicly. Issuers need to prove compliance without deanonymizing users.

## Repository layout

```
.
├── contracts/compliance_hook/    Soroban Rust contract implementing the SEP-0057 hook interface
├── circuits/sanctions_proof/     ZK circuit design spec (non-membership proof against a sanctions list)
├── oracle/                       Node.js service simulating a live sanctions-list feed + Merkle proof generation
├── dashboard/                    No-code compliance rule builder + audit dashboard (HTML/CSS/JS demo)
├── brand/                        Reso logo, wordmark, and brand glyph assets (SVG)
└── docs/ARCHITECTURE.md          Full system architecture and data flow
```

## Status: scaffold, not production

The contract is written but not compiled (no local Rust/Soroban toolchain was available when this was authored). The oracle and dashboard are runnable demos using real Merkle-tree logic; the zero-knowledge proof step itself is specified in `circuits/sanctions_proof/CIRCUIT_SPEC.md` but simulated, not implemented with a real proving system.

## Next steps

1. Install `rustup`, `cargo`, and `soroban-cli`; run `soroban contract build` on `contracts/compliance_hook`.
2. Replace the ZK proof stub in the contract with a real verifier call using Stellar's native `pairing_check` host function (CAP-0074, CAP-0075).
3. Implement the circuit spec in Noir, compile to Groth16/PLONK, and wire it to the oracle's Merkle root.
4. Connect the dashboard to the oracle and contract via Soroban RPC / Stellar Horizon.
5. Deploy to Stellar testnet, then pursue hackathon bounties, an SDF ecosystem grant, and paid SEP-0057 integration work with early issuers.
