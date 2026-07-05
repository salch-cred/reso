# 5. FHE-encrypted spending limits

## The problem

Even in the base zero-knowledge design, the *pattern* of a wallet's spending (the running daily-volume counter) is tracked in the clear by the contract, so anyone who can read contract state can infer spending behavior over time, even without knowing identity.

## The idea

Keep the running daily-volume total fully encrypted using homomorphic encryption, so the contract can add up a user's transaction amounts and check them against a limit **without ever decrypting the running total**. Only a final "within limit: yes/no" bit is ever exposed — not the amounts, not the total.

## Why it's genuinely hard

- True fully homomorphic encryption (FHE) is computationally expensive and only recently became practical enough for real use (e.g. Zama's TFHE-rs/Concrete, fhEVM). Integrating it with Soroban (which has no native FHE host functions, unlike its native ZK primitives) means either running the homomorphic computation off-chain via an oracle/coprocessor, or waiting for/contributing to native support.
- Combining FHE with the threshold-disclosure design (#2/#3) so that *only* an authorized threshold can ever decrypt anything is its own layer of protocol design, not just "add a library."
- Performance: current FHE schemes are orders of magnitude slower than plaintext arithmetic, so real deployment requires careful engineering of what's actually computed under encryption vs. what can stay in zero-knowledge form.

## Working demo

`../../crypto/paillier-demo.js` implements a real (but toy-key-sized, NOT secure) Paillier partially-homomorphic scheme, which is additively homomorphic — exactly the operation needed here (summing transaction amounts). It uses a real Miller-Rabin primality test to generate its demo keys (not hardcoded numbers), and demonstrates encrypting several transaction amounts, summing them homomorphically without decrypting anything in between, and only decrypting the final total for a limit check. Run with `node crypto/paillier-demo.js`.

**Production gap:** this demo uses small (~24-bit) demo primes purely to keep the arithmetic fast and readable. Production should use either a vetted, properly-keyed Paillier implementation (if only additive homomorphism is needed) or a full FHE scheme like Zama's TFHE-rs/Concrete (if more complex encrypted logic is needed), run off-chain via an oracle/coprocessor pattern, with the decryption key itself threshold-held per feature #2.

## References

- Zama TFHE-rs / Concrete / fhEVM documentation.
- Paillier, P. "Public-Key Cryptosystems Based on Composite Degree Residuosity Classes." EUROCRYPT 1999.
