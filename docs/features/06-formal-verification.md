# 6. Formally verified compliance contract

## The problem

Most crypto compliance products stop at a security audit — a human review that can still miss edge cases. For a contract whose entire purpose is "never let a non-compliant transfer through," that's a meaningfully weaker guarantee than a mathematical proof.

## The idea

Use a formal verification tool (Kani, a bit-precise model checker for Rust) to prove — for *all* possible input values within realistic bounds, not just hand-written test cases — that certain safety properties always hold, e.g.:

- The contract never returns success when the transfer amount exceeds the per-transaction limit.
- The rolling daily limit can never be exceeded across a sequence of individually-valid transactions.
- A transfer is never accepted when the sanctions non-membership proof is invalid.

## Why it's genuinely hard

- Formal verification requires restructuring code so the properties you care about are expressed as pure, `Env`-free functions that a model checker can reason about — Soroban contract entrypoints take an `Env` object that doesn't fit Kani's symbolic execution model directly, so the compliance-checking logic needs to be factored out.
- Writing *useful* proof harnesses (not just ones that happen to pass) requires genuinely understanding all the edge cases and invariants of the system — it's easy to write a harness that technically runs but doesn't actually constrain the interesting cases.
- Very few teams in the crypto compliance space do this at all; it's much more common (and much weaker) to rely solely on manual audits.

## What's here

`../../contracts/compliance_hook/src/verification.rs` contains Kani proof harness **specifications** for the two most important safety properties. They are not yet runnable: this sandbox has no Rust toolchain, and the harnesses reference pseudocode for functions that don't exist yet (the compliance logic needs to be extracted into `Env`-free helper functions first, which is real refactoring work). Comments in the file explain exactly what's missing.

**Production gap:** install `cargo-kani` locally, extract the pure compliance-checking logic out of `check_transfer` into standalone functions, wire the harnesses to call them, and run `cargo kani` to get real proof results.

## References

- Kani Rust Verifier: https://model-checking.github.io/kani/
