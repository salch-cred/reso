#!/usr/bin/env node
/**
 * Sanctions/PEP feed oracle simulation.
 *
 * Demonstrates the real logic (Merkle tree construction + non-membership
 * check) that a production oracle would run, using a simulated sanctions
 * list instead of a live OFAC/PEP data source. This is runnable today; the
 * ZK-SNARK wrapping around this logic is specified in
 * circuits/sanctions_proof/CIRCUIT_SPEC.md and is NOT implemented here.
 */

const crypto = require("crypto");

function sha256(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

/** Minimal binary Merkle tree over a sorted list of leaf hashes. */
class MerkleTree {
  constructor(leaves) {
    this.leaves = [...leaves].sort(); // sorted so non-membership can rely on ordering
    this.layers = [this.leaves];
    let current = this.leaves;
    while (current.length > 1) {
      const next = [];
      for (let i = 0; i < current.length; i += 2) {
        const left = current[i];
        const right = current[i + 1] ?? current[i];
        next.push(sha256(left + right));
      }
      this.layers.push(next);
      current = next;
    }
  }

  get root() {
    return this.layers[this.layers.length - 1][0];
  }

  isMember(leafHash) {
    return this.leaves.includes(leafHash);
  }
}

function addressHash(address) {
  return sha256(address.toLowerCase());
}

function buildSanctionsRoot(sanctionedAddresses) {
  const leaves = sanctionedAddresses.map(addressHash);
  const tree = new MerkleTree(leaves.length ? leaves : [sha256("__EMPTY__")]);
  return tree;
}

function demo() {
  const sanctionedAddresses = [
    "GABC1SANCTIONEDEXAMPLEADDRESS0001",
    "GABC2SANCTIONEDEXAMPLEADDRESS0002",
    "GABC3SANCTIONEDEXAMPLEADDRESS0003",
  ];

  const tree = buildSanctionsRoot(sanctionedAddresses);
  console.log("Published sanctions Merkle root:", tree.root);

  const testCases = [
    "GABC1SANCTIONEDEXAMPLEADDRESS0001",
    "GCLEANUSERADDRESSTHATISFINE00099",
  ];

  for (const addr of testCases) {
    const isSanctioned = tree.isMember(addressHash(addr));
    console.log(
      `Address ${addr} -> ${isSanctioned ? "SANCTIONED (block transfer)" : "clear (eligible for proof generation)"}`,
    );
  }

  console.log(
    "\nNext step for production: wrap this non-membership check in a Noir circuit,",
    "compile to Groth16/PLONK, and verify on-chain via Stellar's native BN254",
    "pairing-check host function (see circuits/sanctions_proof/CIRCUIT_SPEC.md).",
  );
}

if (require.main === module) {
  demo();
}

module.exports = { MerkleTree, buildSanctionsRoot, addressHash };
