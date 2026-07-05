#!/usr/bin/env node
/**
 * Working simulation of a compliance-gated Stellar claimable balance.
 *
 * Real Stellar claimable balances support predicate trees (and/or/not,
 * time bounds, unconditional). This demo adds one more predicate type on
 * top of that model: "claimable only if the recipient currently has a
 * valid Reso compliance proof" — meaning BOTH (a) they have completed
 * verification at all, and (b) they are not sanctioned or revoked.
 *
 * Run with: node oracle/claimable-balance-predicate-demo.js
 */
const { buildSanctionsRoot, addressHash } = require("./sanctions-feed");
const { RevocationRegistry } = require("./revocation-registry");

const sanctionsTree = buildSanctionsRoot(["GABC1SANCTIONEDEXAMPLEADDRESS0001"]);
const revocationRegistry = new RevocationRegistry();

// Accounts that have actually completed KYC verification. An account NOT in
// this set has no compliance proof at all yet, regardless of whether it's
// sanctioned — this is what makes "not yet verified" a real, distinct state
// from "verified and clean."
const verifiedAccounts = new Set();

function completeVerification(account) {
  verifiedAccounts.add(account);
}

function hasValidComplianceProof(account) {
  if (!verifiedAccounts.has(account)) return false; // no credential issued yet
  if (sanctionsTree.isMember(addressHash(account))) return false;
  if (revocationRegistry.isRevoked(`cred_for_${account}`)) return false;
  return true;
}

/** Mirrors Stellar's predicate tree shape: { and: [...] } | { or: [...] } | { not: ... } | { beforeMs } | { unconditional: true } */
function evaluatePredicate(predicate, ctx) {
  if (predicate.unconditional) return true;
  if (predicate.and) return predicate.and.every((p) => evaluatePredicate(p, ctx));
  if (predicate.or) return predicate.or.some((p) => evaluatePredicate(p, ctx));
  if (predicate.not) return !evaluatePredicate(predicate.not, ctx);
  if (predicate.beforeMs !== undefined) return ctx.nowMs < predicate.beforeMs;
  if (predicate.resoComplianceProof) return hasValidComplianceProof(ctx.claimant);
  throw new Error("Unknown predicate shape");
}

function createClaimableBalance({ sender, claimant, amount, expiresInMs }) {
  return {
    sender,
    claimant,
    amount,
    createdAt: Date.now(),
    predicate: {
      and: [{ beforeMs: Date.now() + expiresInMs }, { resoComplianceProof: true }],
    },
  };
}

function attemptClaim(balance, nowMs = Date.now()) {
  const ok = evaluatePredicate(balance.predicate, { claimant: balance.claimant, nowMs });
  return ok
    ? { claimed: true, amount: balance.amount }
    : { claimed: false, reason: "Predicate not satisfied (expired, not yet verified, or sanctioned/revoked)" };
}

function demo() {
  console.log("Sender pays an unverified recipient; funds go into escrow instead of failing outright.");
  const claimant = "GNEWFREELANCERACCOUNT00042";
  const balance = createClaimableBalance({
    sender: "GSENDERBUSINESSACCOUNT0001",
    claimant,
    amount: 1200,
    expiresInMs: 5000,
  });
  console.log("Escrowed balance:", balance);

  console.log("\nRecipient tries to claim before completing verification (should FAIL — no credential yet)...");
  console.log(" →", attemptClaim(balance));

  console.log("\nRecipient completes KYC at an anchor; a compliance credential is now issued...");
  completeVerification(claimant);

  console.log("Claim again now that verification is complete (should SUCCEED)...");
  console.log(" →", attemptClaim(balance));

  console.log("\nCompare: a verified BUT sanctioned recipient can never successfully claim:");
  const sanctionedClaimant = "GABC1SANCTIONEDEXAMPLEADDRESS0001";
  completeVerification(sanctionedClaimant);
  const badBalance = createClaimableBalance({
    sender: "GSENDERBUSINESSACCOUNT0001",
    claimant: sanctionedClaimant,
    amount: 1200,
    expiresInMs: 5000,
  });
  console.log(" →", attemptClaim(badBalance));
}

if (require.main === module) {
  demo();
}

module.exports = { createClaimableBalance, attemptClaim, evaluatePredicate, completeVerification };
