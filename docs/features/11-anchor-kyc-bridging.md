# 11. Anchor-network KYC bridging (SEP-6 / SEP-12)

## The problem

Ordinary people — especially unbanked or underbanked users in the 170+ countries Stellar's anchor network already reaches — often complete KYC verification once at a local cash-in/cash-out anchor, then have to redo it from scratch for every new platform or asset they touch. This is the feature most directly about solving a problem for people, not institutions.

## The idea

Bridge the KYC data anchors already collect via **SEP-12** (the standard for exchanging KYC/AML info with an anchor) directly into Reso's zero-knowledge identity commitment — so a user who verified once at any participating anchor can generate a valid Reso compliance proof without a second, redundant verification process.

## Why this is the most "for people" feature in this set

- It removes real, repeated friction for people who are often the least equipped to deal with it (no smartphone, limited documentation, distrust of yet-another-form).
- It reuses infrastructure that already exists at scale (anchors, SEP-12 flows) instead of asking people to adopt something new.
- It directly serves the "reach a billion people" goal from this project's original ideation — not through a new consumer product, but by removing a barrier in infrastructure people already use.

## Working demo

`../../oracle/anchor-kyc-bridge-demo.js` takes a mock SEP-12 KYC payload (the fields a real anchor would collect: name, birth date, address, ID document hash) and deterministically derives a Reso identity commitment from it — the same kind of commitment used by the sanctions/revocation Merkle trees elsewhere in this repo — without ever exposing the underlying personal fields on-chain.

**Production gap:** this demo hashes mock SEP-12 fields directly. A production bridge needs a real integration with an anchor's SEP-12 endpoint (authenticated via SEP-10 web auth), a clear data-retention/consent policy (the anchor already holds this data under its own compliance obligations — Reso should not become a second copy of sensitive PII), and a Poseidon-based commitment (matching the ZK circuit spec in `circuits/sanctions_proof/CIRCUIT_SPEC.md`) rather than a plain SHA-256 hash.

## References

- SEP-12: KYC API — https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md
- SEP-6: Deposit and Withdrawal API — https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md
