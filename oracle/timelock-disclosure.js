#!/usr/bin/env node
/**
 * Working demo of a time-locked, threshold-gated disclosure scheme, built
 * on top of the Shamir secret sharing primitive in
 * oracle/threshold-secret-sharing.js.
 *
 * Design: a specific flagged transaction's real identity can only be
 * decrypted if BOTH conditions hold:
 *   1. At least `threshold` independent authorized parties contribute
 *      their share (no single regulator or admin can unilaterally deanonymize
 *      a user), AND
 *   2. A minimum time delay has passed since the disclosure request was
 *      opened (giving the user/issuer a window to contest it).
 *
 * Production note: real timelock encryption (e.g. drand/tlock, using
 * threshold BLS over a public randomness beacon) removes the need for the
 * trustees to be online at the exact unlock time. This demo instead
 * enforces the time gate at the reconstruction step in application logic,
 * which is simpler but requires the verifying code path to be trusted to
 * check the clock honestly — a real deployment should prefer drand/tlock
 * or an equivalent verifiable-time construction.
 */
const { splitSecret, reconstructSecret } = require("./threshold-secret-sharing");

function openDisclosureRequest({ secret, threshold, n, unlockAfterMs }) {
  return {
    shares: splitSecret(secret, threshold, n),
    threshold,
    requestedAt: Date.now(),
    unlockAt: Date.now() + unlockAfterMs,
  };
}

function attemptDisclosure(request, providedShares, nowMs = Date.now()) {
  if (nowMs < request.unlockAt) {
    return { ok: false, reason: `Time lock not yet expired (unlocks in ${request.unlockAt - nowMs}ms)` };
  }
  if (providedShares.length < request.threshold) {
    return { ok: false, reason: `Not enough trustee approvals (${providedShares.length}/${request.threshold})` };
  }
  return { ok: true, secret: reconstructSecret(providedShares) };
}

function demo() {
  const trueIdentityCommitment = 123456789012345n;
  const request = openDisclosureRequest({
    secret: trueIdentityCommitment,
    threshold: 3,
    n: 5,
    unlockAfterMs: 200,
  });

  console.log("Disclosure request opened. Attempting immediate disclosure (should fail, time lock active)...");
  const tooEarly = attemptDisclosure(request, request.shares.slice(0, 3), Date.now());
  console.log(" →", tooEarly);

  console.log("\nAttempting disclosure with only 2 of 5 trustee approvals after time passes (should fail, below threshold)...");
  setTimeout(() => {
    const belowThreshold = attemptDisclosure(request, request.shares.slice(0, 2));
    console.log(" →", belowThreshold);

    console.log("\nAttempting disclosure with 3 of 5 trustee approvals after time passes (should succeed)...");
    const success = attemptDisclosure(request, request.shares.slice(0, 3));
    console.log(" → ok:", success.ok, success.ok ? `recovered=${success.secret === trueIdentityCommitment}` : success.reason);
  }, 250);
}

if (require.main === module) {
  demo();
}

module.exports = { openDisclosureRequest, attemptDisclosure };
