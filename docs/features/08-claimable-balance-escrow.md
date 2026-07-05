# 8. Compliance-gated claimable balance escrow

## The problem

A compliance check that just rejects a payment outright is a bad experience: senders and recipients (often ordinary freelancers, remittance recipients, or gig workers) are left with a bounced payment and no clear path to resolve it.

## The idea

Use Stellar's native **claimable balance** primitive — a payment that sits in escrow until specific predicates are satisfied — so that instead of rejecting a payment to a not-yet-verified recipient, Reso holds the funds safely until the recipient completes verification and produces a valid compliance proof. This is one of the features most directly useful to ordinary people.

## Why it's genuinely useful, not just technical

- Real people lose money and time today when cross-border payments silently fail due to compliance mismatches. Escrow-until-verified turns a hard failure into a recoverable state.
- Stellar's claimable balances natively support predicate combinations (`and`, `or`, `not`, time bounds) — Reso adds one more predicate type: "claimable only with a valid Reso compliance proof," without needing to reinvent escrow logic from scratch.

## Working demo

`../../oracle/claimable-balance-predicate-demo.js` simulates Stellar's claimable balance predicate evaluation logic (time bounds + a custom "valid compliance proof" predicate that correctly distinguishes "not yet verified" from "verified and clean"), reusing the sanctions/revocation registries already in this repo, and shows a payment correctly failing to claim before verification and succeeding only after.

**Production gap:** this demo simulates predicate evaluation in plain JS. A real implementation would construct an actual `ClaimPredicate` structure via the Stellar SDK and submit a real `CreateClaimableBalanceOp`/`ClaimClaimableBalanceOp` transaction pair; this sandbox has no internet access to install `stellar-sdk` to do that for real.

## References

- Stellar Docs: Claimable Balances — https://developers.stellar.org/docs/build/guides/transactions/claimable-balances
