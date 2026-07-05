# Advanced feature specs

These are hard, research-grade extensions on top of the base compliance hook. Each doc includes: what it does, why it's genuinely hard, and (where feasible in this sandbox, which has no Rust/Soroban toolchain and no internet access) a small runnable proof-of-concept demonstrating the underlying cryptographic primitive with plain Node.js.

Honesty note: none of these techniques were invented here — they build on real, cited research and existing systems (Nova folding schemes, threshold cryptography, timelock encryption, cryptographic accumulators, partially/fully homomorphic encryption, formal verification). The genuine differentiation is combining several of them into one Stellar/Soroban compliance product, which — as far as available research shows — nobody has shipped yet. That is a real, defensible edge; it is not a claim that the underlying cryptography itself is unprecedented.

| # | Feature | Status |
|---|---------|--------|
| 1 | [Recursive proof folding](01-recursive-proof-folding.md) | Spec + conceptual illustration |
| 2 | [Threshold sanctions oracle](02-threshold-sanctions-oracle.md) | Spec + working Shamir secret sharing demo |
| 3 | [Time-locked regulator disclosure](03-timelock-disclosure.md) | Spec + working threshold-gated demo |
| 4 | [Real-time credential revocation](04-realtime-revocation.md) | Spec + working Merkle revocation registry demo |
| 5 | [FHE-encrypted spending limits](05-fhe-spending-limits.md) | Spec + working toy Paillier homomorphic demo |
| 6 | [Formally verified contract](06-formal-verification.md) | Spec + Kani proof harness (requires local `cargo kani`) |
