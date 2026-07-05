#!/usr/bin/env node
/**
 * Working demo of a SAFEGUARDED clawback trigger wired to the revocation
 * registry: revocation does NOT immediately trigger clawback. It opens a
 * contest window first, and clawback only fires if nobody contests within
 * that window — mirroring the time-locked disclosure design (feature #3)
 * so this powerful operation isn't instant and unilateral.
 *
 * Run with: node oracle/clawback-trigger-demo.js
 */
const { RevocationRegistry } = require("./revocation-registry");

class SafeguardedClawbackTrigger {
  constructor({ contestWindowMs }) {
    this.registry = new RevocationRegistry();
    this.contestWindowMs = contestWindowMs;
    this.pending = new Map();
    this.executedClawbacks = [];
  }

  revoke(credentialId) {
    this.registry.revoke(credentialId);
    this.pending.set(credentialId, { revokedAt: Date.now(), contested: false });
    console.log(`Revoked "${credentialId}". Clawback pending, contest window ${this.contestWindowMs}ms.`);
  }

  contest(credentialId) {
    const entry = this.pending.get(credentialId);
    if (entry) {
      entry.contested = true;
      console.log(`"${credentialId}" revocation CONTESTED — clawback will not execute automatically.`);
    }
  }

  processPending(nowMs = Date.now()) {
    for (const [credentialId, entry] of this.pending.entries()) {
      if (entry.contested) continue;
      if (nowMs - entry.revokedAt >= this.contestWindowMs) {
        this.executedClawbacks.push(credentialId);
        this.pending.delete(credentialId);
        console.log(`Contest window elapsed uncontested — executing clawback for "${credentialId}" (mock).`);
      }
    }
  }
}

function demo() {
  const trigger = new SafeguardedClawbackTrigger({ contestWindowMs: 200 });

  trigger.revoke("cred_fraud_case_001");
  trigger.revoke("cred_disputed_case_002");

  console.log("\nAccount for case 002 disputes the revocation before the window elapses...");
  trigger.contest("cred_disputed_case_002");

  setTimeout(() => {
    console.log("\nContest window has now elapsed. Processing pending clawbacks...");
    trigger.processPending();
    console.log("\nExecuted clawbacks:", trigger.executedClawbacks, "(case 002 correctly excluded)");
  }, 250);
}

if (require.main === module) {
  demo();
}

module.exports = { SafeguardedClawbackTrigger };
