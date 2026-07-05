# 4. Real-time credential revocation

## The problem

Revocation is one of the hardest parts of any credential system (this is true even outside crypto — see X.509 certificate revocation lists / OCSP). Most zkKYC systems batch revocation updates (e.g. daily), which means a user flagged for fraud can keep transacting for hours after being revoked.

## The idea

Use a Merkle-based revocation registry (a cryptographic accumulator) whose root updates **immediately** on every revocation event. Any proof generated against a stale root should be checked against the current root at verification time, so a revoked user is blocked on their very next transaction attempt, not after a batch delay.

## Why it's genuinely hard

- There's a real tension between privacy and speed: checking revocation status without contacting the issuer (for privacy) usually means the verifier needs a fresh copy of the registry root, which pushes complexity onto how often/how the root is distributed.
- Real research on this is active and unsettled — for example, the 2025 "zkToken" paper proposes letting the credential holder configure how long a proof stays valid before requiring a revocation re-check, as a way to bound bandwidth without sacrificing too much freshness.
- Cryptographic accumulators (RSA accumulators, Merkle accumulators, bilinear accumulators) all have different tradeoffs in proof size, update cost, and whether they need a trusted setup.

## Working demo

`../../oracle/revocation-registry.js` implements a real Merkle-accumulator-based revocation registry: revoking a credential updates the root instantly, and the very next lookup reflects the new state. Run with `node oracle/revocation-registry.js`.

**Production gap:** this demo keeps the full revoked-credential set in memory for simplicity. Production would need a real Merkle tree (not just a sorted-set hash) to generate non-membership proofs efficiently, a distribution mechanism for the current root (e.g. published on-chain by the same oracle that publishes the sanctions root), and a policy for how fresh a client's cached root is allowed to be.

## References

- "zkToken: Empowering Holders to Limit Revocation Checks for Verifiable Credentials" (arXiv 2509.11934).
- "Public Key Accumulators for Revocation of Non-Anonymous Credentials" (IACR ePrint 2025/549).
