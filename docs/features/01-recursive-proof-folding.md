# 1. Recursive proof folding (Nova-style IVC)

## The problem

In the base design, every transaction requires generating and verifying a fresh zero-knowledge proof from scratch. For a user with a long transaction history, that's wasted work — the same eligibility facts get re-proven over and over.

## The idea

Use a folding scheme (as introduced in Nova, Kothapalli/Setty/Braun, 2021) to fold each new compliance proof into a single running proof, so that verifying a user's entire history costs the same as verifying one step, no matter how many transactions they've made. This is called Incrementally Verifiable Computation (IVC).

## Why it's genuinely hard

- Folding schemes are 2021-era research; production tooling (e.g. Nova, SuperNova, HyperNova) is still immature and mostly used by specialized rollup/proving teams, not typical dApp developers.
- Integrating a folding-based prover with Soroban's native BN254/Poseidon host functions (rather than a general-purpose curve) is unexplored territory — most existing Nova implementations target different curve cycles (e.g. Pallas/Vesta).
- Folding is not itself zero-knowledge by default (per the original paper); achieving ZK IVC requires an additional wrapping SNARK, adding engineering complexity.

## Reso's approach

1. Each transaction's compliance witness (sanctions non-membership, KYC tier, limit check) becomes one step function `F` in an IVC scheme.
2. The wallet/prover folds the new step into the previous running instance instead of proving from scratch.
3. Only the final folded proof is ever verified on-chain — verification cost stays constant (O(1)) regardless of a user's transaction count.

## Illustrative simulation (not real folding-scheme math)

`../../folding/fold-simulation.js` demonstrates the *shape* of the pattern — a running accumulator hash that "absorbs" each new step, so that a single value represents the validity of the whole chain — using plain hashing instead of real folding-scheme algebra. This is for illustrating the IVC concept only; it is **not** cryptographically equivalent to Nova/HyperNova and provides none of their soundness guarantees. A real implementation would require a folding-scheme library (e.g. a Rust port of Nova) wired to Soroban's native curve operations.

## References

- Kothapalli, Setty, Braun. "Nova: Recursive Zero-Knowledge Arguments from Folding Schemes." 2021.
