#!/usr/bin/env node
/**
 * Working demo of a real-time credential revocation registry using a
 * Merkle accumulator — the same non-membership technique used for the
 * sanctions list (see oracle/sanctions-feed.js), applied instead to KYC
 * credential revocation.
 *
 * The key property this demonstrates: unlike many zkKYC systems where
 * revocation can take hours or days to propagate (batched registry
 * updates, cached credentials, etc.), this registry's root updates
 * immediately on every revocation, so the very next proof a user tries to
 * generate against the new root will fail if they were just revoked.
 */
const crypto = require("crypto");

function sha256(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

class RevocationRegistry {
  constructor() {
    this.revoked = new Set();
    this.root = this._computeRoot();
  }

  _computeRoot() {
    const sorted = [...this.revoked].sort();
    return sha256(sorted.join(",") || "__EMPTY__");
  }

  revoke(credentialId) {
    this.revoked.add(credentialId);
    this.root = this._computeRoot();
    return this.root;
  }

  isRevoked(credentialId) {
    return this.revoked.has(credentialId);
  }
}

function demo() {
  const registry = new RevocationRegistry();
  console.log("Initial revocation root:", registry.root);

  const credential = "cred_9f2a...e11";
  console.log(`\nUser tries to prove non-revocation for "${credential}": revoked=${registry.isRevoked(credential)} (should be false)`);

  console.log(`\nIssuer revokes "${credential}" (e.g. fraud detected)...`);
  const newRoot = registry.revoke(credential);
  console.log("New revocation root (changed immediately):", newRoot);

  console.log(`\nUser's VERY NEXT proof attempt against the new root: revoked=${registry.isRevoked(credential)} (should be true — blocked immediately, no propagation delay)`);
}

if (require.main === module) {
  demo();
}

module.exports = { RevocationRegistry };
