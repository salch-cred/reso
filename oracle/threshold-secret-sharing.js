#!/usr/bin/env node
/**
 * Working (t,n) Shamir secret sharing over a large prime field, using
 * native BigInt. This is real, correct threshold-cryptography math (not a
 * simulation) — suitable as the trust-distribution primitive underneath
 * the threshold sanctions oracle (docs/features/02) and the time-locked
 * disclosure scheme (docs/features/03).
 *
 * Production note: this demo uses a fixed 127-bit Mersenne prime for
 * clarity. Production use should rely on an audited secret-sharing
 * library and a properly generated prime/curve group, plus a real
 * distributed key generation (DKG) ceremony instead of a single dealer
 * splitting the secret.
 */
const crypto = require("crypto");

// 2^127 - 1, a Mersenne prime, used as the field modulus for this demo.
const PRIME = (1n << 127n) - 1n;

function mod(a, m) {
  const r = a % m;
  return r >= 0n ? r : r + m;
}

function modPow(base, exp, m) {
  let result = 1n;
  base = mod(base, m);
  while (exp > 0n) {
    if (exp & 1n) result = mod(result * base, m);
    exp >>= 1n;
    base = mod(base * base, m);
  }
  return result;
}

function modInv(a, m) {
  let [old_r, r] = [mod(a, m), m];
  let [old_s, s] = [1n, 0n];
  while (r !== 0n) {
    const q = old_r / r;
    [old_r, r] = [r, old_r - q * r];
    [old_s, s] = [s, old_s - q * s];
  }
  return mod(old_s, m);
}

function randomFieldElement() {
  const bytes = crypto.randomBytes(16);
  return mod(BigInt("0x" + bytes.toString("hex")), PRIME);
}

/** Split `secret` into `n` shares such that any `threshold` of them can reconstruct it. */
function splitSecret(secret, threshold, n) {
  const coefficients = [mod(secret, PRIME)];
  for (let i = 1; i < threshold; i++) coefficients.push(randomFieldElement());

  const shares = [];
  for (let x = 1n; x <= BigInt(n); x++) {
    let y = 0n;
    let xPow = 1n;
    for (const c of coefficients) {
      y = mod(y + c * xPow, PRIME);
      xPow = mod(xPow * x, PRIME);
    }
    shares.push({ x, y });
  }
  return shares;
}

/** Reconstruct the secret from >= threshold shares via Lagrange interpolation at x=0. */
function reconstructSecret(shares) {
  let secret = 0n;
  for (let i = 0; i < shares.length; i++) {
    let { x: xi, y: yi } = shares[i];
    let num = 1n;
    let den = 1n;
    for (let j = 0; j < shares.length; j++) {
      if (i === j) continue;
      const xj = shares[j].x;
      num = mod(num * (0n - xj), PRIME);
      den = mod(den * (xi - xj), PRIME);
    }
    const lagrangeCoeff = mod(num * modInv(den, PRIME), PRIME);
    secret = mod(secret + yi * lagrangeCoeff, PRIME);
  }
  return secret;
}

function demo() {
  const trustees = 5;
  const threshold = 3;
  const secret = randomFieldElement();

  console.log(`Splitting a secret into ${trustees} trustee shares, threshold ${threshold}`);
  const shares = splitSecret(secret, threshold, trustees);
  shares.forEach((s) => console.log(`  Trustee ${s.x}: share=${s.y.toString().slice(0, 12)}...`));

  const belowThreshold = shares.slice(0, threshold - 1);
  const atThreshold = shares.slice(0, threshold);

  const reconstructedFromEnough = reconstructSecret(atThreshold);
  console.log(`\nReconstructed with ${threshold} shares matches original: ${reconstructedFromEnough === secret}`);

  const reconstructedFromTooFew = reconstructSecret(belowThreshold);
  console.log(`Reconstructed with ${threshold - 1} shares matches original: ${reconstructedFromTooFew === secret} (expected false — below threshold is mathematically insufficient)`);

  console.log(
    "\nApplication: no single trustee (e.g. issuer admin) can unilaterally",
    "publish a new sanctions Merkle root or approve a disclosure — at least",
    `${threshold} of ${trustees} independent parties must cooperate.`,
  );
}

if (require.main === module) {
  demo();
}

module.exports = { splitSecret, reconstructSecret, PRIME };
