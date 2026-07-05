#!/usr/bin/env node
/**
 * Working (TOY-SIZED, NOT SECURE) Paillier partially-homomorphic
 * encryption demo, using native BigInt and a real Miller-Rabin primality
 * test (not hardcoded numbers, to avoid ever silently using a composite
 * "prime" by mistake).
 *
 * Paillier is additively homomorphic: encrypt(a) * encrypt(b) mod n^2
 * decrypts to (a + b). This demonstrates the real underlying property
 * needed for "encrypted running daily-volume" spending limits — the
 * contract (or oracle) can add up a user's encrypted transaction amounts
 * without ever decrypting them, and only the final "within limit: yes/no"
 * check needs to touch plaintext.
 *
 * WARNING: this demo uses small (~24-bit) demo primes for speed and
 * readability. It is NOT cryptographically secure and must never be used
 * with real data. Production should use a vetted library and real key
 * sizes (2048+ bit primes), or preferably a modern scheme like Zama's
 * TFHE-rs/Concrete for full (not just additive) homomorphic operations,
 * matching the fhEVM-style approach referenced in
 * docs/features/05-fhe-spending-limits.md.
 */
const crypto = require("crypto");

function gcd(a, b) {
  while (b) [a, b] = [b, a % b];
  return a;
}

function modPow(base, exp, m) {
  let result = 1n;
  base = ((base % m) + m) % m;
  while (exp > 0n) {
    if (exp & 1n) result = (result * base) % m;
    exp >>= 1n;
    base = (base * base) % m;
  }
  return result;
}

function modInv(a, m) {
  let [old_r, r] = [((a % m) + m) % m, m];
  let [old_s, s] = [1n, 0n];
  while (r !== 0n) {
    const q = old_r / r;
    [old_r, r] = [r, old_r - q * r];
    [old_s, s] = [s, old_s - q * s];
  }
  return ((old_s % m) + m) % m;
}

function lcm(a, b) {
  return (a * b) / gcd(a, b);
}

function L(x, n) {
  return (x - 1n) / n;
}

function randomBigInt(bits) {
  const bytes = Math.ceil(bits / 8);
  const buf = crypto.randomBytes(bytes);
  buf[0] |= 0x80;
  buf[bytes - 1] |= 1;
  return BigInt("0x" + buf.toString("hex"));
}

/** Real Miller-Rabin primality test (probabilistic, but with enough rounds for demo-grade confidence). */
function isProbablePrime(n, rounds = 20) {
  if (n < 2n) return false;
  for (const small of [2n, 3n, 5n, 7n, 11n, 13n, 17n, 19n, 23n]) {
    if (n === small) return true;
    if (n % small === 0n) return false;
  }
  let d = n - 1n;
  let r = 0n;
  while (d % 2n === 0n) {
    d /= 2n;
    r += 1n;
  }
  witnessLoop: for (let i = 0; i < rounds; i++) {
    const a = 2n + (randomBigInt(32) % (n - 4n));
    let x = modPow(a, d, n);
    if (x === 1n || x === n - 1n) continue;
    for (let j = 0n; j < r - 1n; j++) {
      x = modPow(x, 2n, n);
      if (x === n - 1n) continue witnessLoop;
    }
    return false;
  }
  return true;
}

function randomPrime(bits) {
  while (true) {
    const candidate = randomBigInt(bits) | 1n;
    if (isProbablePrime(candidate)) return candidate;
  }
}

function generateToyKeypair(bits = 24) {
  let p, q, n;
  do {
    p = randomPrime(bits);
    q = randomPrime(bits);
    n = p * q;
  } while (p === q);
  const nSquared = n * n;
  const lambda = lcm(p - 1n, q - 1n);
  const g = n + 1n;
  const mu = modInv(L(modPow(g, lambda, nSquared), n), n);
  return { publicKey: { n, g, nSquared }, privateKey: { lambda, mu, n, nSquared } };
}

function encrypt(m, publicKey) {
  const { n, g, nSquared } = publicKey;
  if (m < 0n || m >= n) throw new Error(`Plaintext ${m} out of range for modulus n=${n}`);
  let r;
  do {
    r = randomBigInt(16) % n;
  } while (r === 0n || gcd(r, n) !== 1n);
  return (modPow(g, m, nSquared) * modPow(r, n, nSquared)) % nSquared;
}

function decrypt(c, privateKey) {
  const { lambda, mu, n, nSquared } = privateKey;
  return (L(modPow(c, lambda, nSquared), n) * mu) % n;
}

function homomorphicAdd(c1, c2, publicKey) {
  return (c1 * c2) % publicKey.nSquared;
}

function demo() {
  const { publicKey, privateKey } = generateToyKeypair(24);
  console.log(`Generated toy Paillier keypair with real (Miller-Rabin verified) primes. n=${publicKey.n}`);

  const dailyLimit = 25000n;
  const tx1 = 8000n;
  const tx2 = 9500n;
  const tx3 = 6000n;

  console.log("\nEncrypting three transaction amounts (issuer/oracle never sees plaintext amounts)...");
  const c1 = encrypt(tx1, publicKey);
  const c2 = encrypt(tx2, publicKey);
  const c3 = encrypt(tx3, publicKey);

  console.log("Homomorphically summing the encrypted amounts (no decryption at any point)...");
  const encryptedTotal = homomorphicAdd(homomorphicAdd(c1, c2, publicKey), c3, publicKey);

  console.log("Only the FINAL limit check ever decrypts anything, and only the boolean result is used on-chain:");
  const decryptedTotal = decrypt(encryptedTotal, privateKey);
  const expected = tx1 + tx2 + tx3;
  console.log(` → decrypted running total = ${decryptedTotal} (expected ${expected}, correct=${decryptedTotal === expected})`);
  console.log(` → within daily limit of ${dailyLimit}? ${decryptedTotal <= dailyLimit}`);

  console.log(
    "\nIn production: only a threshold-held decryption key (see feature #2/#3) would ever",
    "perform that final decryption, and only to emit a yes/no limit-check result — never the",
    "raw spending total — to a public contract.",
  );
}

if (require.main === module) {
  demo();
}

module.exports = { generateToyKeypair, encrypt, decrypt, homomorphicAdd, isProbablePrime };
