# 2. Threshold sanctions oracle

## The problem

In the base design, a single admin key publishes the sanctions-list Merkle root that every compliance proof checks against. That's a single point of failure: whoever holds that key could censor a user, insert a false entry, or go offline and freeze the whole system.

## The idea

Distribute trust over the root-publishing authority using a **(t, n) threshold scheme**: at least `t` of `n` independent trustees (e.g. the issuer, an independent auditor, a regulator-nominated party, a Stellar ecosystem multisig) must cooperate to publish a new sanctions root. No single party can unilaterally change what counts as "sanctioned."

## Why it's genuinely hard

- Real threshold cryptography requires either a trusted dealer (simpler, but reintroduces a temporary single point of trust during setup) or a full **distributed key generation (DKG)** ceremony (harder, but avoids that weakness entirely).
- Coordinating `t`-of-`n` signing/decryption in a way that's fast enough for a live oracle (not just a one-time ceremony) is an operational engineering problem, not just a math problem.
- Choosing `t` and `n` involves real governance tradeoffs (liveness vs. censorship-resistance) that have to be designed with actual stakeholders, not just cryptographers.

## Working demo

`../../oracle/threshold-secret-sharing.js` implements real, correct (t,n) Shamir secret sharing over a large prime field with native BigInt — run it directly with `node oracle/threshold-secret-sharing.js`. It demonstrates splitting a secret among trustees and reconstructing it only when the threshold is met.

**Production gap:** this demo uses a single dealer to split the secret, which is fine for illustrating the math but not for production trust distribution. Production would need a proper DKG protocol and an audited threshold-signature library (e.g. FROST, or a BLS threshold scheme), plus real trustee infrastructure.

## References

- NIST Multi-Party Threshold Cryptography (MPTC) project.
- Wikipedia: Threshold cryptosystem.
