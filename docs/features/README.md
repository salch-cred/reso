# Advanced feature specs

These are hard, research-grade extensions on top of the base compliance hook. Each doc includes: what it does, why it's genuinely hard, and (where feasible in this sandbox, which has no Rust/Soroban toolchain and no internet access) a small runnable proof-of-concept demonstrating the underlying primitive with plain Node.js.

Honesty note: none of these techniques were invented here — they build on real, cited research and existing systems (Nova folding schemes, threshold cryptography, timelock encryption, cryptographic accumulators, partially/fully homomorphic encryption, formal verification, and Stellar's own native primitives and SEPs). The genuine differentiation is combining several of them into one Stellar/Soroban compliance product. That is a real, defensible edge; it is not a claim that the underlying techniques themselves are unprecedented.

## General cryptographic extensions (1–6)

| # | Feature | Status |
|---|---------|--------|
| 1 | [Recursive proof folding](01-recursive-proof-folding.md) | Spec + conceptual illustration |
| 2 | [Threshold sanctions oracle](02-threshold-sanctions-oracle.md) | Spec + working Shamir secret sharing demo |
| 3 | [Time-locked regulator disclosure](03-timelock-disclosure.md) | Spec + working threshold-gated demo |
| 4 | [Real-time credential revocation](04-realtime-revocation.md) | Spec + working Merkle revocation registry demo |
| 5 | [FHE-encrypted spending limits](05-fhe-spending-limits.md) | Spec + working toy Paillier homomorphic demo |
| 6 | [Formally verified contract](06-formal-verification.md) | Spec + Kani proof harness (requires local `cargo kani`) |

## Stellar-native extensions (7–11)

These build directly on Stellar's own primitives and published roadmap, rather than generic cryptography adapted to Stellar. Ranked here by who they actually benefit:

| # | Feature | Who it helps most | Status |
|---|---------|--------------------|--------|
| 11 | [Anchor-network KYC bridging](11-anchor-kyc-bridging.md) | **Ordinary people** — removes repeat KYC friction for real, often underbanked users | Spec + working demo |
| 8 | [Claimable balance escrow](08-claimable-balance-escrow.md) | **Ordinary people** — turns failed cross-border payments into a recoverable state | Spec + working demo |
| 10 | [Post-quantum readiness](10-post-quantum-readiness.md) | Long-term security for everyone, but preventive/abstract today | Spec only, no demo |
| 7 | [SEP-8 regulated assets](07-sep8-regulated-assets.md) | Mostly issuers/wallets (interoperability) | Spec + working demo |
| 9 | [Clawback-triggered revocation](09-clawback-revocation-integration.md) | Institutions; double-edged for individuals — needs the safeguards described in the doc | Spec + working demo |
