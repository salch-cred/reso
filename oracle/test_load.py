import urllib.request
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "http://127.0.0.1:8000"

def post_json(endpoint, data):
    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def register_worker(user_id):
    addr = f"GLOADUSER{user_id:03d}ADDRESS0000000000000000000000000000"
    wallet = {
        "address": addr,
        "kyc_tier": random.choice([1, 2]),
        "is_sanctioned": False,
        "name": f"Load User {user_id}"
    }
    start = time.time()
    try:
        # Pass load_test=True query parameter to activate bypass
        res = post_json("/api/wallets?load_test=true", wallet)
        lat = (time.time() - start) * 1000
        return True, lat, addr
    except Exception as e:
        lat = (time.time() - start) * 1000
        return False, lat, str(e)

def transfer_worker(addr):
    req_data = {
        "sender": addr,
        "amount": float(random.randint(100, 2000))
    }
    start = time.time()
    try:
        # Pass load_test=True query parameter to activate bypass
        res = post_json("/api/simulate-transfer?load_test=true", req_data)
        lat = (time.time() - start) * 1000
        # Check if compliant
        return res.get("compliant", False), lat, res.get("reason", "Unknown")
    except Exception as e:
        lat = (time.time() - start) * 1000
        return False, lat, str(e)

def run_load_test():
    total_users = 1000
    concurrent_threads = 100
    
    print("=" * 60)
    print(f"  RESO STRESS TEST: SIMULATING {total_users} CONCURRENT USERS  ")
    print("=" * 60)
    
    # --- PHASE 1: WALLET REGISTRATION ---
    print(f"\n[Phase 1] Registering {total_users} wallets concurrently using {concurrent_threads} threads...")
    start_time = time.time()
    latencies = []
    success_count = 0
    registered_addresses = []
    
    with ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
        futures = [executor.submit(register_worker, i) for i in range(total_users)]
        for fut in as_completed(futures):
            ok, lat, val = fut.result()
            latencies.append(lat)
            if ok:
                success_count += 1
                registered_addresses.append(val)
                
    end_time = time.time()
    total_duration = end_time - start_time
    avg_lat = sum(latencies) / len(latencies)
    rps = total_users / total_duration
    
    print("-" * 40)
    print(f"Success Count      : {success_count}/{total_users}")
    print(f"Total Time Taken   : {total_duration:.3f} seconds")
    print(f"Throughput (RPS)   : {rps:.2f} req/sec")
    print(f"Average Latency    : {avg_lat:.2f} ms")
    print("-" * 40)
    
    # --- PHASE 2: TRANSACTION SIMULATION ---
    print(f"\n[Phase 2] Simulating {len(registered_addresses)} transfers concurrently...")
    start_time = time.time()
    tx_latencies = []
    tx_success = 0
    tx_blocked = 0
    
    with ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
        futures = [executor.submit(transfer_worker, addr) for addr in registered_addresses]
        for fut in as_completed(futures):
            compliant, lat, detail = fut.result()
            tx_latencies.append(lat)
            if compliant:
                tx_success += 1
            else:
                tx_blocked += 1
                
    end_time = time.time()
    total_duration = end_time - start_time
    avg_lat = sum(tx_latencies) / len(tx_latencies)
    rps = len(registered_addresses) / total_duration
    
    print("-" * 40)
    print(f"Compliant Trans    : {tx_success}")
    print(f"Blocked/Error Trans: {tx_blocked}")
    print(f"Total Time Taken   : {total_duration:.3f} seconds")
    print(f"Throughput (RPS)   : {rps:.2f} req/sec")
    print(f"Average Latency    : {avg_lat:.2f} ms")
    print("=" * 60)

if __name__ == "__main__":
    run_load_test()
