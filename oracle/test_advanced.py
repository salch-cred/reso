import urllib.request
import json
import time

API_BASE = "http://127.0.0.1:8000"

def post_json(endpoint, data):
    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def get_json(endpoint):
    with urllib.request.urlopen(f"{API_BASE}{endpoint}") as res:
        return json.loads(res.read().decode())

def test_advanced():
    print("--- 1. Paillier Key Generation & FHE Summing ---")
    keygen = post_json("/api/crypto/paillier/keygen", {})
    print("Generated Paillier Public Modulus (n):", keygen["public_key"]["n"])
    
    # Encrypt two values
    c1 = post_json("/api/crypto/paillier/encrypt", {"message": 8000})["ciphertext"]
    c2 = post_json("/api/crypto/paillier/encrypt", {"message": 9500})["ciphertext"]
    print("Ciphertext 1 (8000):", c1[:32] + "...")
    print("Ciphertext 2 (9500):", c2[:32] + "...")
    
    # Check limit check on sum
    sum_res = post_json("/api/crypto/paillier/sum-and-check", {
        "ciphertexts": [c1, c2],
        "limit": 25000
    })
    print("Decrypted Running Total (Expected 17500):", sum_res["decrypted_sum"])
    print("Within daily limit (Expected True)?", sum_res["within_limit"])
    
    print("\n--- 2. Shamir Secret Sharing & Time-locked Disclosure ---")
    # Open request with 1 second delay
    open_req = post_json("/api/crypto/disclosure/open", {
        "identity_commitment": 9876543210,
        "threshold": 3,
        "n": 5,
        "delay_sec": 1
    })
    print("Opened request, unlocks at:", open_req["unlock_at"])
    
    # Attempt immediate decryption (should fail because of time lock)
    decrypt_fail_time = post_json("/api/crypto/disclosure/decrypt", {})
    print("Immediate Decrypt Success?", decrypt_fail_time["success"])
    print("Reason (Expected Time lock active):", decrypt_fail_time["reason"])
    
    # Wait for time lock to expire
    print("Waiting 1.5 seconds for time lock...")
    time.sleep(1.5)
    
    # Attempt decryption with no approvals (should fail because of threshold)
    decrypt_fail_shares = post_json("/api/crypto/disclosure/decrypt", {})
    print("Decrypt with 0 Approvals Success?", decrypt_fail_shares["success"])
    print("Reason (Expected Insufficient approvals):", decrypt_fail_shares["reason"])
    
    # Approve with 2 trustees (still not enough)
    post_json("/api/crypto/disclosure/approve", {"trustee_id": 1})
    post_json("/api/crypto/disclosure/approve", {"trustee_id": 2})
    decrypt_fail_shares2 = post_json("/api/crypto/disclosure/decrypt", {})
    print("Decrypt with 2 Approvals Success?", decrypt_fail_shares2["success"])
    print("Reason (Expected Insufficient approvals):", decrypt_fail_shares2["reason"])
    
    # Approve with 3rd trustee (should succeed)
    post_json("/api/crypto/disclosure/approve", {"trustee_id": 3})
    decrypt_ok = post_json("/api/crypto/disclosure/decrypt", {})
    print("Decrypt with 3 Approvals Success?", decrypt_ok["success"])
    print("Decrypted Identity Commitment:", decrypt_ok.get("decrypted_identity"))
    
    print("\n--- 3. Dynamic Revocation Registry ---")
    init_rev = get_json("/api/crypto/revocation")
    print("Initial Revocation Root:", init_rev["revocation_root"])
    
    # Revoke a clean user
    rev_res = post_json("/api/crypto/revocation/revoke", {"wallet": "GCLEANUSERADDRESSTHATISFINE00099"})
    print("Updated Revocation Root:", rev_res["revocation_root"])
    
    # Verify transaction simulation gets blocked immediately
    sim_res = post_json("/api/simulate-transfer", {
        "sender": "GCLEANUSERADDRESSTHATISFINE00099",
        "amount": 500
    })
    print("Compliant?", sim_res["compliant"])
    print("Rule checked:", sim_res["event"]["rule_checked"])
    print("Reason:", sim_res["reason"])
    
    print("\n--- 4. Recursive Proof Folding ---")
    init_fold = get_json("/api/crypto/folding")
    print("Genesis Folding Accumulator:", init_fold["accumulator"])
    
    fold_res = post_json("/api/crypto/folding/fold", {"witness": "step_1_verification"})
    print("Folded Step Accumulator:", fold_res["accumulator"])

if __name__ == "__main__":
    test_advanced()
