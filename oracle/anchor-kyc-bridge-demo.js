#!/usr/bin/env node
/**
 * Working demo: bridge a mock SEP-12 KYC payload (the kind of data a
 * Stellar anchor already collects for cash-in/cash-out) into a Reso
 * identity commitment, without ever putting the underlying personal
 * fields on-chain.
 *
 * Run with: node oracle/anchor-kyc-bridge-demo.js
 */
const crypto = require("crypto");

function sha256(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

/**
 * Derives a stable identity commitment from SEP-12-shaped KYC fields.
 * PRODUCTION NOTE: real Reso circuits should use a Poseidon hash (to
 * stay efficient inside a ZK circuit, per circuits/sanctions_proof/CIRCUIT_SPEC.md)
 * rather than SHA-256, which is used here only because it's available
 * without external dependencies in this sandbox.
 */
function deriveIdentityCommitment(sep12Fields) {
  const canonical = [
    sep12Fields.first_name,
    sep12Fields.last_name,
    sep12Fields.birth_date,
    sep12Fields.address,
    sep12Fields.id_document_hash,
  ]
    .map((v) => (v || "").trim().toLowerCase())
    .join("|");
  return sha256(canonical);
}

function demo() {
  const mockSep12Payload = {
    first_name: "Amara",
    last_name: "Okafor",
    birth_date: "1994-03-12",
    address: "12 Market Rd, Lagos, NG",
    id_document_hash: sha256("mock-national-id-scan-bytes"),
  };

  console.log("Anchor already holds this KYC data from onboarding a cash-in/cash-out user:");
  console.log({ ...mockSep12Payload, id_document_hash: mockSep12Payload.id_document_hash.slice(0, 12) + "..." });

  const commitment = deriveIdentityCommitment(mockSep12Payload);
  console.log("\nDerived Reso identity commitment (this is the only thing that ever touches Reso/on-chain):");
  console.log(" →", commitment);

  console.log("\nSame person, verified at a different anchor with identical KYC fields, derives the SAME commitment:");
  const secondTimeCommitment = deriveIdentityCommitment({ ...mockSep12Payload });
  console.log(" →", secondTimeCommitment, "match:", secondTimeCommitment === commitment);

  console.log(
    "\nThis means a user who verified once at ANY participating anchor can prove",
    "eligibility to a Reso-protected asset without a second, redundant KYC process —",
    "the actual personal fields never need to be shared with Reso or put on-chain.",
  );
}

if (require.main === module) {
  demo();
}

module.exports = { deriveIdentityCommitment };
