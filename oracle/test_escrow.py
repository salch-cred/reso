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

def test_escrow_flow():
    print("--- 1. Depositing Escrow on Stellar Testnet ---")
    dep_res = post_json("/api/escrow/deposit", {
        "sender": "GCLEANUSERADDRESSTHATISFINE00099",
        "recipient": "GBASICKYCUSERADDRESS00000000001",
        "amount": 2500,
        "unlock_delay_sec": 30
    })
    print("Deposit Result Status:", dep_res["status"])
    print("On-Chain TX Result:", dep_res["escrow"]["onchain_tx"])
    
    print("\n--- 2. Fetching Active Escrows ---")
    active = get_json("/api/escrow")
    print(f"Total active escrows: {len(active['escrows'])}")
    print("Active Escrow:", json.dumps(active["escrows"][0], indent=2))
    
    print("\n--- 3. Claiming Escrow with ZK Proof ---")
    claim_res = post_json("/api/escrow/claim", {
        "recipient": "GBASICKYCUSERADDRESS00000000001",
        "proof": "99aa88bb77cc" # non-empty proof
    })
    print("Claim Result Status:", claim_res["status"])
    print("Claimed Amount:", claim_res["amount"])
    
    print("\n--- 4. Confirming Escrow is Deleted ---")
    active_after = get_json("/api/escrow")
    print(f"Total active escrows: {len(active_after['escrows'])}")
    
    print("\n--- 5. Testing Timelock and Refund Flow ---")
    # Deposit with 7 seconds delay
    dep_res2 = post_json("/api/escrow/deposit", {
        "sender": "GCLEANUSERADDRESSTHATISFINE00099",
        "recipient": "GNOKYCUSERADDRESS000000000000002",
        "amount": 1000,
        "unlock_delay_sec": 7
    })
    print("Timelock Escrow Deposited.")
    
    # Attempt immediate refund (should fail as lock is active)
    try:
        post_json("/api/escrow/refund", {
            "recipient": "GNOKYCUSERADDRESS000000000000002"
        })
        print("Error: Immediate refund succeeded but should have failed!")
    except urllib.error.HTTPError as e:
        print("Refund blocked (Expected):", e.read().decode('utf-8', errors='ignore').encode('ascii', errors='replace').decode())
        
    # Wait for timelock to expire
    print("Waiting 7.5 seconds...")
    time.sleep(7.5)
    
    # Attempt refund again (should succeed)
    refund_res = post_json("/api/escrow/refund", {
        "recipient": "GNOKYCUSERADDRESS000000000000002"
    })
    print("Refund Result Status (Expected refunded):", refund_res["status"])
    print("Refunded Amount:", refund_res["amount"])

if __name__ == "__main__":
    test_escrow_flow()
