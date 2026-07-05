#!/usr/bin/env node
/**
 * Working demo of a SEP-8 ("Regulated Assets") approval server's core
 * decision logic, as a real Node.js HTTP server using only the built-in
 * `http` module.
 *
 * SEP-8 defines the response shape an approval server must return:
 *   - { status: "success", tx_signed }         -> approved as-is
 *   - { status: "revised", tx_revised, message } -> needs re-signing
 *   - { status: "pending", timeout, message }    -> needs manual review
 *   - { status: "rejected", error }              -> denied
 *
 * This demo reuses the sanctions and revocation registries already in
 * this repo to make the approve/reject decision, and returns a
 * spec-shaped response. Run with: node oracle/sep8-approval-server-demo.js
 * then in another terminal:
 *   curl -X POST localhost:8008/tx-approve -H 'content-type: application/json' \
 *     -d '{"account":"GCLEANUSERADDRESSTHATISFINE00099","amount":5000}'
 *
 * PRODUCTION GAP: a real approval server parses/signs actual Stellar
 * transaction XDR via the Stellar SDK. This demo operates on a simplified
 * mock transaction object (account + amount) instead, since this sandbox
 * has no internet access to install stellar-sdk.
 */
const http = require("http");
const { buildSanctionsRoot, addressHash } = require("./sanctions-feed");
const { RevocationRegistry } = require("./revocation-registry");

const sanctionsTree = buildSanctionsRoot([
  "GABC1SANCTIONEDEXAMPLEADDRESS0001",
  "GABC2SANCTIONEDEXAMPLEADDRESS0002",
]);
const revocationRegistry = new RevocationRegistry();
revocationRegistry.revoke("cred_for_GREVOKEDUSERADDRESS00042");

const MAX_AMOUNT = 10000;

function decide({ account, amount }) {
  if (!account || typeof amount !== "number") {
    return { status: "rejected", error: "Malformed request: account and numeric amount are required" };
  }
  if (sanctionsTree.isMember(addressHash(account))) {
    return { status: "rejected", error: `Account ${account} is on the sanctions list` };
  }
  if (revocationRegistry.isRevoked(`cred_for_${account}`)) {
    return { status: "rejected", error: `Credential for ${account} has been revoked` };
  }
  if (amount > MAX_AMOUNT) {
    return {
      status: "revised",
      message: `Amount exceeds the ${MAX_AMOUNT} limit for a single approval; split into multiple transactions`,
    };
  }
  return { status: "success", message: "Transaction approved by Reso compliance checks" };
}

function demo() {
  console.log("Running decision logic directly (no server) against three example accounts:\n");
  for (const req of [
    { account: "GCLEANUSERADDRESSTHATISFINE00099", amount: 5000 },
    { account: "GABC1SANCTIONEDEXAMPLEADDRESS0001", amount: 100 },
    { account: "GREVOKEDUSERADDRESS00042", amount: 100 },
    { account: "GCLEANUSERADDRESSTHATISFINE00099", amount: 50000 },
  ]) {
    console.log(JSON.stringify(req), "->", JSON.stringify(decide(req)));
  }
}

if (require.main === module) {
  if (process.argv.includes("--serve")) {
    const server = http.createServer((req, res) => {
      if (req.method === "POST" && req.url === "/tx-approve") {
        let body = "";
        req.on("data", (chunk) => (body += chunk));
        req.on("end", () => {
          try {
            const parsed = JSON.parse(body || "{}");
            const result = decide(parsed);
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify(result));
          } catch (e) {
            res.writeHead(400, { "content-type": "application/json" });
            res.end(JSON.stringify({ status: "rejected", error: "Invalid JSON" }));
          }
        });
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(8008, () => console.log("SEP-8 approval server demo listening on :8008"));
  } else {
    demo();
  }
}

module.exports = { decide };
