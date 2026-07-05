# 3. Time-locked, threshold-gated regulator disclosure

## The problem

Most zkKYC/compliance systems are all-or-nothing: either a transaction is fully anonymous forever, or an admin/regulator can see everything at will. Neither matches how lawful disclosure is actually supposed to work (e.g. a warrant, a fraud investigation) — which requires due process, not a permanent backdoor.

## The idea

A regulator can request disclosure of one *specific* flagged transaction's real identity, but the request can only succeed if:

1. A **threshold** of independent authorized parties (not just the regulator alone) approve, and
2. A **mandatory time delay** passes first, giving the user or issuer a real window to contest the request.

This is closer to how a legal warrant process works than a typical "compliance backdoor."

## Why it's genuinely hard

- Combining threshold cryptography with a verifiable time constraint is an active research area (see: timelock encryption / drand's `tlock`, built on threshold BLS over a public randomness beacon).
- Getting the trust model right is as much a governance problem as a cryptography problem: who counts as an "authorized party," and how is that set changed over time without reintroducing a single point of control?
- Real timelock encryption (rather than an application-level clock check) requires a public randomness beacon and pairing-based cryptography that isn't trivial to integrate with Soroban today.

## Working demo

`../../oracle/timelock-disclosure.js` builds on the Shamir secret-sharing primitive to demonstrate both gates working together: a disclosure attempt fails if the time lock hasn't expired, and separately fails if too few trustees approve, and only succeeds when both conditions are met. Run with `node oracle/timelock-disclosure.js`.

**Production gap:** this demo enforces the time gate in application logic (checking `Date.now()`), which requires trusting the code path to check the clock honestly. Production should use a verifiable-time construction like `tlock` (threshold BLS over a public randomness beacon such as `drand`), so the time constraint is cryptographically enforced, not just checked in software.

## References

- Drand / Protocol Labs Research: "tlock: Practical Timelock Encryption Based on Threshold BLS."
- "SeDe: Balancing Blockchain Privacy and Regulatory Compliance By Selective De-Anonymization" (arXiv 2311.08167).
