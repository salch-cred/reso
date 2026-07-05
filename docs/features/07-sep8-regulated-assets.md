# 7. SEP-8 Regulated Assets integration

## The problem

Building a fully custom compliance-hook protocol means every wallet, exchange, and anchor that wants to support Reso-protected assets has to write custom integration code just for Reso.

## The idea

Stellar already has an official standard for this: **SEP-8, "Regulated Assets."** It defines an **approval server** — a single HTTP endpoint that receives a signed transaction, checks it for compliance, and either signs it (approved), revises it (e.g. adds a required compliance operation and asks the sender to re-sign), or rejects it. Wallets and exchanges that already support SEP-8 can work with a Reso-protected asset with no Reso-specific integration at all.

## Why it matters for real adoption

- SEP-8 is an existing, recognized standard (Active since 2018, used by real issuance platforms) — building Reso's proof verification *behind* a standard approval-server interface means wallets don't need to learn anything new to support it.
- This is squarely an ecosystem-interoperability feature, not a direct end-user benefit — see the honesty note in `docs/features/README.md` about which features solve problems for people vs. institutions.

## Working demo

`../../oracle/sep8-approval-server-demo.js` implements the core SEP-8 approval server *decision logic* as a real, runnable Node.js HTTP server (using only Node's built-in `http` module, no dependencies): it receives a mock transaction description, runs it through Reso's compliance checks (reusing the sanctions and revocation registries already in this repo), and returns a SEP-8-shaped response (`approved`, `revised`, `rejected`, or `pending`).

**Production gap:** a real SEP-8 server parses and re-signs actual Stellar transaction XDR envelopes using the Stellar SDK. This sandbox has no internet access to install `stellar-sdk`, so the demo operates on a simplified mock transaction object instead of real XDR. The decision logic and response shape are accurate to the spec; the transaction parsing/signing layer is not implemented.

## References

- SEP-8: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0008.md
