# 10. Post-quantum-ready compliance credentials

## The problem

Compliance credentials and proofs issued today could, in principle, be forged decades from now if a sufficiently powerful quantum computer breaks the signature scheme used to issue them ("harvest now, decrypt/forge later" risk).

## The idea

Build credential issuance crypto-agile from day one — able to support post-quantum signature schemes — so Reso can adopt Stellar's own post-quantum signatures as they roll out, rather than needing to re-issue every credential ever created.

## Why it's real, not speculative

Stellar Development Foundation published a real, dated "Quantum Preparedness Plan" (announced June 2026): Stage 1 (2026) adds native post-quantum signature verification to Soroban as host functions, supporting **ML-DSA-44 and ML-DSA-65** (NIST-standardized signature schemes), enabling quantum-safe contract accounts without any protocol-level change to classic Stellar accounts. This isn't hypothetical — it's Stellar's own committed roadmap.

## Why it's genuinely hard

- Crypto-agility (supporting multiple signature schemes side-by-side, with a clean migration path) is real software-architecture work, not just "swap one algorithm for another."
- Post-quantum signatures (ML-DSA/Dilithium-family) have much larger key and signature sizes than classical ECDSA/Ed25519, which affects storage costs and proof sizes throughout the system — this needs to be designed for, not bolted on later.

## Status: spec only, no demo

Unlike the other features in this repo, there is no runnable demo here. Post-quantum signature libraries are not installed in this sandbox, and there is no internet access to install one. This doc exists purely to record the design intent and the real Stellar roadmap it depends on.

## References

- Stellar: "Introducing the Quantum Preparedness Plan" — https://stellar.org/blog/foundation-news/introducing-the-quantum-preparedness-plan
