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

def test_flow():
    print("--- 1. Getting current rules ---")
    rules = get_json("/api/rules")
    print("Current rules:", json.dumps(rules, indent=2))

    print("\n--- 2. Registering a new wallet (Test User) ---")
    new_wallet = {
        "address": "GTEST1234567890",
        "kyc_tier": 1,
        "is_sanctioned": False,
        "name": "Test User"
    }
    reg_res = post_json("/api/wallets", new_wallet)
    print("Registration response (Merkle root updated):", reg_res["sanctions_merkle_root"])

    print("\n--- 3. Simulating a compliant transfer (500 USD) ---")
    sim_res = post_json("/api/simulate-transfer", {
        "sender": "GTEST1234567890",
        "amount": 500.0
    })
    print("Compliant?", sim_res["compliant"])
    print("Reason:", sim_res["reason"])

    print("\n--- 4. Registering a sanctioned wallet (Blocked Entity) ---")
    blocked_wallet = {
        "address": "GBLOCKED987654",
        "kyc_tier": 1,
        "is_sanctioned": True,
        "name": "Blocked Entity"
    }
    reg_res_2 = post_json("/api/wallets", blocked_wallet)
    print("New Merkle root:", reg_res_2["sanctions_merkle_root"])

    print("\n--- 5. Simulating a transfer from sanctioned wallet (should be blocked) ---")
    sim_res_2 = post_json("/api/simulate-transfer", {
        "sender": "GBLOCKED987654",
        "amount": 100.0
    })
    print("Compliant?", sim_res_2["compliant"])
    print("Rule checked:", sim_res_2["event"]["rule_checked"])
    print("Reason:", sim_res_2["reason"])

    print("\n--- 6. Updating rules to require KYC Tier 2 ---")
    rules["min_kyc_tier"] = 2
    updated_rules = post_json("/api/rules", rules)
    print("Updated rules:", json.dumps(updated_rules, indent=2))

    print("\n--- 7. Simulating transfer with Test User (Tier 1) again (should be blocked due to KYC) ---")
    sim_res_3 = post_json("/api/simulate-transfer", {
        "sender": "GTEST1234567890",
        "amount": 500.0
    })
    print("Compliant?", sim_res_3["compliant"])
    print("Rule checked:", sim_res_3["event"]["rule_checked"])
    print("Reason:", sim_res_3["reason"])

    print("\n--- 8. Fetching audit logs ---")
    logs = get_json("/api/audit-logs")
    print(f"Total audit logs fetched: {len(logs)}")
    print("Latest log entry:")
    print(json.dumps(logs[0], indent=2))

if __name__ == "__main__":
    # Wait a second for server to initialize if needed
    time.sleep(1)
    test_flow()
