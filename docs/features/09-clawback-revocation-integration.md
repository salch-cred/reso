# 9. Clawback-triggered revocation enforcement

## The problem

Revoking someone's credential (feature #4) blocks *future* transfers, but doesn't recover funds a bad actor already received before being flagged.

## The idea

Wire the real-time revocation registry directly to Stellar's native **clawback** operation, so the moment an account is revoked (e.g. confirmed fraud), the issuer's already-configured clawback authority can reclaim the specific flagged funds, not just block future activity.

## Why this needs care, not just code

This is the most double-edged feature in the whole set. Clawback is powerful: it lets an issuer take funds from someone's account without their consent. Automating it off a revocation event is only responsible if:

- Revocation itself is gated by the threshold-approval design (feature #2), so no single party can trigger it unilaterally, and
- There's a real appeals/contest window (mirroring the time-locked disclosure design in feature #3) before clawback actually executes, so a mistaken or disputed revocation doesn't instantly and irreversibly seize someone's funds.

Without those safeguards, this feature stops being a fraud-prevention tool and becomes a risk to ordinary users. This doc exists to state that tradeoff explicitly, not to hide it.

## Working demo

`../../oracle/clawback-trigger-demo.js` wires the existing `RevocationRegistry` to a mock clawback trigger, but only fires after a simulated delay and only if the revocation hasn't been contested — illustrating the safeguard, not just the mechanism.

**Production gap:** a real integration calls Stellar's actual `Clawback`/`ClawbackClaimableBalance` operations via the Stellar SDK, which requires the issuer's asset to have been created with the `AUTH_CLAWBACK_ENABLED` flag set. This sandbox cannot install `stellar-sdk` to demonstrate that call for real.

## References

- Stellar Docs: Clawbacks — https://developers.stellar.org/docs/build/guides/transactions/clawbacks
- CAP-0035: Asset Clawback — https://github.com/stellar/stellar-protocol/blob/master/core/cap-0035.md
