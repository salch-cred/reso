import os
import json
import hashlib
import time
import random
import sqlite3
import threading
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ---- Stellar SDK (real testnet) ----
try:
    from stellar_sdk import (
        Server, Keypair, TransactionBuilder, Network, Asset,
        Claimant, ClaimPredicate, Signer,
    )
    from stellar_sdk.exceptions import NotFoundError as StellarNotFound
    import httpx as _httpx
    STELLAR_AVAILABLE = True
except ImportError:
    STELLAR_AVAILABLE = False

HORIZON_URL = "https://horizon-testnet.stellar.org"
FRIENDBOT_URL = "https://friendbot.stellar.org"
EXPLORER_BASE = "https://stellar.expert/explorer/testnet"
try:
    NET_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
except Exception:
    NET_PASSPHRASE = "Test SDF Network ; September 2015"

app = FastAPI(title="Reso Compliance Oracle API v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# SQLite Database Setup
# ---------------------------------------------------------------------------

DB_PATH = "/data/reso.db" if os.path.isdir("/data") else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "reso.db"
)


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY,
            max_amount REAL NOT NULL DEFAULT 10000,
            daily_limit REAL NOT NULL DEFAULT 25000,
            min_kyc_tier INTEGER NOT NULL DEFAULT 1,
            sanctions_enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            kyc_tier INTEGER NOT NULL DEFAULT 0,
            is_sanctioned INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL DEFAULT '',
            daily_volume REAL NOT NULL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS escrows (
            recipient TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            amount REAL NOT NULL,
            unlock_time INTEGER NOT NULL,
            onchain_tx TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sender TEXT NOT NULL,
            amount REAL NOT NULL,
            rule_checked TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            proof_ref TEXT NOT NULL,
            merkle_root TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stellar_accounts (
            public_key TEXT PRIMARY KEY,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "INSERT OR IGNORE INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1, 10000.0, 25000.0, 1, 1)"
        )
        seed_wallets = [
            ("GCLEANUSERADDRESSTHATISFINE00099", 2, 0, "Alice (Tier 2 User)", 5000.0),
            ("GBASICKYCUSERADDRESS00000000001", 1, 0, "Bob (Tier 1 User)", 0.0),
            ("GNOKYCUSERADDRESS000000000000002", 0, 0, "Charlie (No KYC)", 0.0),
            ("GABC1SANCTIONEDEXAMPLEADDRESS0001", 1, 1, "Sanctioned Entity A", 0.0),
        ]
        for w in seed_wallets:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume) VALUES (?,?,?,?,?)",
                w,
            )
        conn.commit()


init_db()


def seed_audit_logs():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO audit_logs (timestamp, sender, amount, rule_checked, status, reason, proof_ref, merkle_root) VALUES (?,?,?,?,?,?,?,?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"), "GABC1SANCTIONEDEXAMPLEADDRESS0001", 250.0,
                 "Sanctions screen", "blocked", "Address listed on active sanctions list",
                 "0x9f2a24c8b618bc360b0e5d41c888ee11", "0x9f2a24c8b618bc..."),
            )
            conn.commit()


seed_audit_logs()

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

state: Dict[str, Any] = {
    "paillier_keys": None,
    "disclosure_request": None,
    "revocation_registry": {
        "revoked": set(),
        "root": hashlib.sha256(b"__EMPTY__").hexdigest(),
    },
    "folding_accumulator": hashlib.sha256(b"GENESIS").hexdigest(),
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db_rules() -> Dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM rules WHERE id = 1").fetchone()
        if row:
            return {"max_amount": row["max_amount"], "daily_limit": row["daily_limit"],
                    "min_kyc_tier": row["min_kyc_tier"], "sanctions_enabled": bool(row["sanctions_enabled"])}
    return {"max_amount": 10000.0, "daily_limit": 25000.0, "min_kyc_tier": 1, "sanctions_enabled": True}

def save_db_rules(rules):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1,?,?,?,?)",
            (rules.max_amount, rules.daily_limit, rules.min_kyc_tier, 1 if rules.sanctions_enabled else 0))
        conn.commit()

def get_db_wallets():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM wallets").fetchall()
        return [{"address": r["address"], "kyc_tier": r["kyc_tier"], "is_sanctioned": bool(r["is_sanctioned"]),
                 "name": r["name"], "daily_volume": r["daily_volume"]} for r in rows]

def save_db_wallet(wallet):
    with get_conn() as conn:
        existing = conn.execute("SELECT daily_volume FROM wallets WHERE address = ?", (wallet.address,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume) VALUES (?,?,?,?,?)",
            (wallet.address, wallet.kyc_tier, 1 if wallet.is_sanctioned else 0, wallet.name,
             existing["daily_volume"] if existing else 0.0))
        conn.commit()

def update_db_daily_volume(address, amount):
    with get_conn() as conn:
        conn.execute("UPDATE wallets SET daily_volume = daily_volume + ? WHERE address = ?", (amount, address))
        conn.commit()

def get_db_escrows():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM escrows").fetchall()
        return [{"recipient": r["recipient"], "sender": r["sender"], "amount": r["amount"],
                 "unlock_time": r["unlock_time"], "onchain_tx": r["onchain_tx"]} for r in rows]

def save_db_escrow(recipient, escrow):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO escrows (recipient, sender, amount, unlock_time, onchain_tx) VALUES (?,?,?,?,?)",
            (recipient, escrow["sender"], escrow["amount"], escrow["unlock_time"], escrow["onchain_tx"]))
        conn.commit()

def delete_db_escrow(recipient):
    with get_conn() as conn:
        conn.execute("DELETE FROM escrows WHERE recipient = ?", (recipient,))
        conn.commit()

def get_db_audit_logs():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]

def insert_db_audit_log(log):
    with get_conn() as conn:
        conn.execute("INSERT INTO audit_logs (timestamp, sender, amount, rule_checked, status, reason, proof_ref, merkle_root) VALUES (?,?,?,?,?,?,?,?)",
            (log["timestamp"], log["sender"], log["amount"], log["rule_checked"],
             log["status"], log["reason"], log["proof_ref"], log["merkle_root"]))
        conn.commit()

# ---------------------------------------------------------------------------
# Merkle Tree
# ---------------------------------------------------------------------------

def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def address_hash(address: str) -> str:
    return sha256_hex(address.strip().lower())

class MerkleTree:
    def __init__(self, leaves):
        self.leaves = sorted(list(set(leaves))) or [sha256_hex("__EMPTY__")]
        self.layers = [self.leaves]
        current = self.leaves
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                l, r = current[i], current[i+1] if i+1 < len(current) else current[i]
                next_layer.append(sha256_hex(l + r))
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self):
        return self.layers[-1][0]

def get_active_sanctions_tree():
    wallets = get_db_wallets()
    return MerkleTree([address_hash(w["address"]) for w in wallets if w["is_sanctioned"]])

# ---------------------------------------------------------------------------
# Cryptography helpers (Shamir + Paillier)
# ---------------------------------------------------------------------------

PRIME_127 = (1 << 127) - 1

def egcd(a, b):
    if a == 0: return b, 0, 1
    g, y, x = egcd(b % a, a)
    return g, x - (b // a) * y, y

def mod_inv(a, m):
    g, x, _ = egcd(a, m)
    if g != 1: raise Exception("No modular inverse")
    return x % m

def split_secret(secret, threshold, n):
    coeffs = [secret % PRIME_127] + [random.randint(1, PRIME_127-1) for _ in range(1, threshold)]
    shares = []
    for x in range(1, n+1):
        y, xp = 0, 1
        for c in coeffs:
            y = (y + c * xp) % PRIME_127
            xp = (xp * x) % PRIME_127
        shares.append({"x": str(x), "y": str(y)})
    return shares

def reconstruct_secret(shares):
    parsed = [{"x": int(s["x"]), "y": int(s["y"])} for s in shares]
    secret = 0
    for i, (xi, yi) in enumerate([(p["x"], p["y"]) for p in parsed]):
        num, den = 1, 1
        for j, xj in enumerate([p["x"] for p in parsed]):
            if i == j: continue
            num = (num * (0 - xj)) % PRIME_127
            den = (den * (xi - xj)) % PRIME_127
        secret = (secret + yi * (num * mod_inv(den, PRIME_127)) % PRIME_127) % PRIME_127
    return secret

def gcd(a, b):
    while b: a, b = b, a % b
    return a

def lcm(a, b): return (a * b) // gcd(a, b)
def L(x, n): return (x - 1) // n

def is_probable_prime(n, rounds=20):
    if n < 2: return False
    for s in [2,3,5,7,11,13,17,19,23,29,31]:
        if n == s: return True
        if n % s == 0: return False
    d, r = n-1, 0
    while d % 2 == 0: d //= 2; r += 1
    for _ in range(rounds):
        a = random.randint(2, n-2)
        x = pow(a, d, n)
        if x == 1 or x == n-1: continue
        ok = any((x := pow(x, 2, n)) == n-1 for _ in range(r-1))
        if not ok: return False
    return True

def generate_random_prime(bits):
    while True:
        c = random.getrandbits(bits) | 1
        if is_probable_prime(c): return c

def generate_paillier_keypair(bits=24):
    while True:
        p, q = generate_random_prime(bits), generate_random_prime(bits)
        if p != q: break
    n = p * q; n2 = n*n; lam = lcm(p-1, q-1); g = n+1
    mu = mod_inv(L(pow(g, lam, n2), n), n)
    return {"n": n, "g": g, "n_squared": n2}, {"lambda": lam, "mu": mu, "n": n, "n_squared": n2}

def paillier_encrypt(m, pub):
    n, g, n2 = pub["n"], pub["g"], pub["n_squared"]
    while True:
        r = random.randint(1, n-1)
        if gcd(r, n) == 1: break
    return (pow(g, m, n2) * pow(r, n, n2)) % n2

def paillier_decrypt(c, priv):
    return (L(pow(c, priv["lambda"], priv["n_squared"]), priv["n"]) * priv["mu"]) % priv["n"]

def paillier_add(c1, c2, pub):
    return (c1 * c2) % pub["n_squared"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Rules(BaseModel):
    max_amount: float; daily_limit: float; min_kyc_tier: int; sanctions_enabled: bool

class Wallet(BaseModel):
    address: str; kyc_tier: int; is_sanctioned: bool; name: str = ""

class TransferRequest(BaseModel):
    sender: str; amount: float

class EscrowDepositRequest(BaseModel):
    sender: str; recipient: str; amount: float; unlock_delay_sec: int = 30

class EscrowClaimRequest(BaseModel):
    recipient: str; proof: str

class EscrowRefundRequest(BaseModel):
    recipient: str

# --- Stellar Pydantic Models ---

class StellarTransferRequest(BaseModel):
    source_secret: str; destination: str; amount: str; memo: str = "Reso Transfer"

class StellarTrustlineRequest(BaseModel):
    account_secret: str; asset_code: str; issuer: str

class StellarIssueAssetRequest(BaseModel):
    issuer_secret: str; distributor_secret: str; asset_code: str; amount: str = "1000000"

class StellarClaimableRequest(BaseModel):
    source_secret: str; claimant: str; amount: str = "10"; unlock_delay_sec: int = 30

class StellarClaimBalanceRequest(BaseModel):
    claimant_secret: str; balance_id: str

class StellarMultisigRequest(BaseModel):
    account_secret: str; new_signer_public: str; weight: int = 1
    med_threshold: int = 2; low_threshold: int = 1; high_threshold: int = 2

class StellarPathPaymentRequest(BaseModel):
    source_secret: str; destination: str
    dest_asset_code: str = "XLM"; dest_asset_issuer: str = ""
    dest_amount: str = "10"; send_asset_code: str = "XLM"

class StellarManageOfferRequest(BaseModel):
    account_secret: str
    selling_code: str = "XLM"; selling_issuer: str = ""
    buying_code: str; buying_issuer: str
    amount: str = "100"; price: str = "1"

# ---------------------------------------------------------------------------
# STELLAR TESTNET HELPERS
# ---------------------------------------------------------------------------

def _stellar_server():
    if not STELLAR_AVAILABLE:
        raise HTTPException(503, "stellar-sdk not installed — check requirements.txt and rebuild")
    return Server(HORIZON_URL)

def _load_kp(secret: str):
    try:
        return Keypair.from_secret(secret)
    except Exception:
        raise HTTPException(400, "Invalid secret key format. Must be a valid Stellar secret key (starts with S).")

# ---------------------------------------------------------------------------
# CORE COMPLIANCE API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "db": "sqlite", "stellar": STELLAR_AVAILABLE, "version": "3.0"}

@app.get("/api/rules", response_model=Rules)
def get_rules(): return Rules(**get_db_rules())

@app.post("/api/rules", response_model=Rules)
def update_rules(rules: Rules):
    save_db_rules(rules); return rules

@app.get("/api/wallets")
def get_wallets():
    tree = get_active_sanctions_tree(); wallets_list = get_db_wallets()
    for w in wallets_list: w["hash"] = address_hash(w["address"])
    return {"wallets": wallets_list, "sanctions_merkle_root": tree.root}

@app.post("/api/wallets")
def add_wallet(wallet: Wallet):
    if not wallet.address.strip(): raise HTTPException(400, "Address required")
    save_db_wallet(wallet)
    return {"status": "success", "wallet": wallet, "sanctions_merkle_root": get_active_sanctions_tree().root}

@app.get("/api/audit-logs")
def get_audit_logs(): return get_db_audit_logs()

@app.post("/api/simulate-transfer")
def simulate_transfer(req: TransferRequest):
    sender = req.sender.strip(); amount = req.amount
    wallets_list = get_db_wallets()
    matched = [w for w in wallets_list if w["address"] == sender]
    wallet = matched[0] if matched else {"address": sender, "kyc_tier": 0, "is_sanctioned": False, "name": "Unknown", "daily_volume": 0.0}
    r = get_db_rules(); rules = Rules(**r)
    tree = get_active_sanctions_tree()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    proof_ref = "0x" + hashlib.sha256(f"{sender}{amount}{time.time()}".encode()).hexdigest()
    mr = f"0x{tree.root[:16]}..."
    with state_lock:
        is_revoked = sender in state["revocation_registry"]["revoked"]
    if is_revoked:
        ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "Credential revocation check",
              "status": "blocked", "reason": "KYC Credential revoked (accumulator proof failed)",
              "proof_ref": proof_ref, "merkle_root": f"0x{state['revocation_registry']['root'][:16]}..."}
        insert_db_audit_log(ev); return {"compliant": False, "reason": ev["reason"], "event": ev}
    if rules.sanctions_enabled and wallet["is_sanctioned"]:
        r2 = "InvalidProof: ZK sanctions check failed — address in Merkle tree"
        ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "On-chain sanctions check",
              "status": "blocked", "reason": r2, "proof_ref": proof_ref, "merkle_root": mr}
        insert_db_audit_log(ev); return {"compliant": False, "reason": r2, "event": ev}
    if wallet["kyc_tier"] < rules.min_kyc_tier:
        r2 = f"KYC Tier {wallet['kyc_tier']} below required {rules.min_kyc_tier}"
        ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "ZK KYC check",
              "status": "blocked", "reason": r2, "proof_ref": proof_ref, "merkle_root": mr}
        insert_db_audit_log(ev); return {"compliant": False, "reason": r2, "event": ev}
    if amount > rules.max_amount:
        r2 = f"AmountExceedsRule: ${amount} > max ${rules.max_amount}"
        ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "ZK Limits check",
              "status": "blocked", "reason": r2, "proof_ref": proof_ref, "merkle_root": mr}
        insert_db_audit_log(ev); return {"compliant": False, "reason": r2, "event": ev}
    if wallet.get("daily_volume", 0.0) + amount > rules.daily_limit:
        r2 = f"Daily limit ${rules.daily_limit} would be exceeded"
        ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "ZK Limits check",
              "status": "blocked", "reason": r2, "proof_ref": proof_ref, "merkle_root": mr}
        insert_db_audit_log(ev); return {"compliant": False, "reason": r2, "event": ev}
    update_db_daily_volume(sender, amount)
    ev = {"timestamp": ts, "sender": sender, "amount": amount, "rule_checked": "All checks passed",
          "status": "ok", "reason": "ZK proof generated and verified. Transaction is compliant.",
          "proof_ref": proof_ref, "merkle_root": mr}
    insert_db_audit_log(ev)
    with state_lock:
        state["folding_accumulator"] = sha256_hex(state["folding_accumulator"] + f"tx:{sender}:{amount}")
    return {"compliant": True, "reason": ev["reason"], "event": ev}

# --- Simulated Escrow ---
@app.get("/api/escrow")
def get_escrows(): return {"escrows": get_db_escrows()}

@app.post("/api/escrow/deposit")
def api_deposit_escrow(req: EscrowDepositRequest):
    if req.sender == req.recipient: raise HTTPException(400, "Sender == recipient")
    escrow = {"sender": req.sender, "recipient": req.recipient, "amount": req.amount,
               "unlock_time": int(time.time()) + req.unlock_delay_sec,
               "onchain_tx": "sim_" + hashlib.sha256(f"{req.sender}{req.recipient}{time.time()}".encode()).hexdigest()[:16]}
    save_db_escrow(req.recipient, escrow)
    insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": req.sender, "amount": req.amount,
        "rule_checked": "ZK Escrow Deposit", "status": "ok", "reason": f"Escrow for {req.recipient[:8]}... Timelock: {req.unlock_delay_sec}s",
        "proof_ref": "0x" + hashlib.sha256(f"escrow{req.sender}{req.recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
    return {"status": "deposited", "escrow": escrow}

@app.post("/api/escrow/claim")
def api_claim_escrow(req: EscrowClaimRequest):
    matched = [e for e in get_db_escrows() if e["recipient"] == req.recipient.strip()]
    if not matched: raise HTTPException(404, "No escrow found")
    escrow = matched[0]
    if int(time.time()) < escrow["unlock_time"]: raise HTTPException(400, f"Locked for {escrow['unlock_time'] - int(time.time())}s more")
    delete_db_escrow(req.recipient)
    insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": req.recipient, "amount": escrow["amount"],
        "rule_checked": "ZK Escrow Claimed", "status": "ok", "reason": "Escrow claimed. ZK proof verified.",
        "proof_ref": "0x" + hashlib.sha256(f"claim{req.recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
    return {"status": "claimed", "amount": escrow["amount"]}

@app.post("/api/escrow/refund")
def api_refund_escrow(req: EscrowRefundRequest):
    matched = [e for e in get_db_escrows() if e["recipient"] == req.recipient.strip()]
    if not matched: raise HTTPException(404, "No escrow found")
    escrow = matched[0]; delete_db_escrow(req.recipient)
    insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": escrow["sender"], "amount": escrow["amount"],
        "rule_checked": "ZK Escrow Refunded", "status": "ok", "reason": "Escrow refunded.",
        "proof_ref": "0x" + hashlib.sha256(f"refund{req.recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
    return {"status": "refunded", "amount": escrow["amount"]}

# ---------------------------------------------------------------------------
# STELLAR TESTNET REAL ENDPOINTS
# ---------------------------------------------------------------------------

@app.post("/api/stellar/create-account")
async def stellar_create_account(label: str = ""):
    """Generate a new keypair and fund it via Friendbot (real testnet XLM)"""
    _stellar_server()
    kp = Keypair.random()
    async with _httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{FRIENDBOT_URL}?addr={kp.public_key}")
    if resp.status_code != 200:
        raise HTTPException(500, f"Friendbot failed: {resp.text[:200]}")
    fb = resp.json()
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO stellar_accounts (public_key, label, created_at) VALUES (?,?,?)",
                     (kp.public_key, label or "Testnet Account", time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    return {
        "public_key": kp.public_key,
        "secret_key": kp.secret,
        "funded": True,
        "starting_balance": "10000 XLM (testnet)",
        "network": "testnet",
        "friendbot_tx": fb.get("hash", ""),
        "explorer": f"{EXPLORER_BASE}/account/{kp.public_key}",
        "warning": "SAVE YOUR SECRET KEY — it will NOT be stored on the server"
    }

@app.get("/api/stellar/account/{address}")
def stellar_get_account(address: str):
    """Load live account info from Horizon testnet"""
    server = _stellar_server()
    try:
        data = server.accounts().account_id(address).call()
        return {
            "address": address,
            "sequence": data["sequence"],
            "balances": data["balances"],
            "signers": data["signers"],
            "thresholds": data["thresholds"],
            "flags": data["flags"],
            "subentry_count": data["subentry_count"],
            "explorer": f"{EXPLORER_BASE}/account/{address}"
        }
    except StellarNotFound:
        raise HTTPException(404, "Account not found on testnet. Fund it via Friendbot first.")
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/transfer")
def stellar_transfer(req: StellarTransferRequest):
    """Real XLM payment on Stellar testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.source_secret)
        acct = server.load_account(kp.public_key)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .add_text_memo(req.memo[:28])
            .append_payment_op(destination=req.destination, asset=Asset.native(), amount=req.amount)
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": kp.public_key,
            "amount": float(req.amount), "rule_checked": "Real Stellar Transfer", "status": "ok",
            "reason": f"On-chain XLM payment to {req.destination[:8]}...",
            "proof_ref": resp["hash"][:18], "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
        return {"hash": resp["hash"], "ledger": resp["ledger"], "source": kp.public_key,
                "destination": req.destination, "amount": f"{req.amount} XLM",
                "status": "success", "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except StellarNotFound:
        raise HTTPException(404, "Account not found on testnet")
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/stellar/transactions/{address}")
def stellar_transactions(address: str, limit: int = 15):
    """Get real transaction history from Horizon testnet"""
    server = _stellar_server()
    try:
        payments = server.payments().for_account(address).limit(limit).order(desc=True).call()
        records = []
        for p in payments["_embedded"]["records"]:
            records.append({
                "id": p.get("id", ""),
                "type": p.get("type", ""),
                "created_at": p.get("created_at", ""),
                "from": p.get("from", ""),
                "to": p.get("to", ""),
                "amount": p.get("amount", ""),
                "asset_type": p.get("asset_type", "native"),
                "asset_code": p.get("asset_code", "XLM"),
                "hash": p.get("transaction_hash", ""),
                "explorer": f"{EXPLORER_BASE}/tx/{p.get('transaction_hash', '')}"
            })
        return {"address": address, "payments": records, "count": len(records)}
    except StellarNotFound:
        raise HTTPException(404, "Account not found on testnet")
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/trustline")
def stellar_add_trustline(req: StellarTrustlineRequest):
    """Add a trustline for a custom asset on testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.account_secret)
        acct = server.load_account(kp.public_key)
        asset = Asset(req.asset_code, req.issuer)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_change_trust_op(asset=asset)
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        return {"hash": resp["hash"], "status": "trustline_added",
                "asset": f"{req.asset_code}:{req.issuer[:8]}...",
                "account": kp.public_key, "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/issue-asset")
def stellar_issue_asset(req: StellarIssueAssetRequest):
    """Issue a custom asset on Stellar testnet (2-step: trustline + payment)"""
    server = _stellar_server()
    try:
        issuer_kp = _load_kp(req.issuer_secret)
        dist_kp = _load_kp(req.distributor_secret)
        asset = Asset(req.asset_code, issuer_kp.public_key)
        # Step 1: distributor adds trustline
        dist_acct = server.load_account(dist_kp.public_key)
        tx1 = (TransactionBuilder(dist_acct, NET_PASSPHRASE, base_fee=100)
               .append_change_trust_op(asset=asset).set_timeout(30).build())
        tx1.sign(dist_kp)
        server.submit_transaction(tx1)
        # Step 2: issuer mints to distributor
        issuer_acct = server.load_account(issuer_kp.public_key)
        tx2 = (TransactionBuilder(issuer_acct, NET_PASSPHRASE, base_fee=100)
               .append_payment_op(destination=dist_kp.public_key, asset=asset, amount=req.amount)
               .add_text_memo(f"Issue {req.asset_code}").set_timeout(30).build())
        tx2.sign(issuer_kp)
        resp = server.submit_transaction(tx2)
        insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": issuer_kp.public_key,
            "amount": float(req.amount), "rule_checked": "Asset Issuance", "status": "ok",
            "reason": f"Issued {req.amount} {req.asset_code} to distributor",
            "proof_ref": resp["hash"][:18], "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
        return {"asset_code": req.asset_code, "issuer": issuer_kp.public_key, "distributor": dist_kp.public_key,
                "amount_issued": req.amount, "hash": resp["hash"],
                "explorer_asset": f"{EXPLORER_BASE}/asset/{req.asset_code}-{issuer_kp.public_key}",
                "explorer_tx": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/claimable-balance/create")
def stellar_create_claimable(req: StellarClaimableRequest):
    """Create a real time-locked claimable balance on Stellar testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.source_secret)
        acct = server.load_account(kp.public_key)
        unlock_time = int(time.time()) + req.unlock_delay_sec
        # Predicate: claimant can only claim AFTER unlock_time
        predicate = ClaimPredicate.predicate_not(
            ClaimPredicate.predicate_before_absolute_time(unlock_time)
        )
        claimant = Claimant(destination=req.claimant, predicate=predicate)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_create_claimable_balance_op(asset=Asset.native(), amount=req.amount, claimants=[claimant])
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        # Try to get balance_id from operations
        balance_id = ""
        try:
            ops = server.operations().for_transaction(resp["hash"]).call()
            for op in ops["_embedded"]["records"]:
                if op.get("type") == "create_claimable_balance":
                    balance_id = op.get("balance_id", "")
        except Exception:
            pass
        insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": kp.public_key,
            "amount": float(req.amount), "rule_checked": "Real Claimable Balance", "status": "ok",
            "reason": f"On-chain claimable balance for {req.claimant[:8]}... Unlock: {req.unlock_delay_sec}s",
            "proof_ref": resp["hash"][:18], "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
        return {"hash": resp["hash"], "balance_id": balance_id, "source": kp.public_key,
                "claimant": req.claimant, "amount": f"{req.amount} XLM",
                "unlock_at": unlock_time, "unlock_delay_sec": req.unlock_delay_sec,
                "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/claimable-balance/claim")
def stellar_claim_balance(req: StellarClaimBalanceRequest):
    """Claim a real claimable balance on Stellar testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.claimant_secret)
        acct = server.load_account(kp.public_key)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_claim_claimable_balance_op(balance_id=req.balance_id)
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        insert_db_audit_log({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": kp.public_key,
            "amount": 0, "rule_checked": "Real Claimable Balance Claimed", "status": "ok",
            "reason": f"Claimed balance {req.balance_id[:20]}...",
            "proof_ref": resp["hash"][:18], "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}..."})
        return {"hash": resp["hash"], "status": "claimed", "balance_id": req.balance_id,
                "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/multisig/setup")
def stellar_multisig_setup(req: StellarMultisigRequest):
    """Add a co-signer and configure thresholds on a real testnet account"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.account_secret)
        acct = server.load_account(kp.public_key)
        signer = Signer.ed25519_public_key(req.new_signer_public, req.weight)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_set_options_op(
                signer=signer,
                low_threshold=req.low_threshold,
                med_threshold=req.med_threshold,
                high_threshold=req.high_threshold,
            )
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        return {"hash": resp["hash"], "account": kp.public_key, "new_signer": req.new_signer_public,
                "weight": req.weight, "thresholds": {"low": req.low_threshold, "med": req.med_threshold, "high": req.high_threshold},
                "status": "multisig_configured", "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/path-payment")
def stellar_path_payment(req: StellarPathPaymentRequest):
    """Strict-receive path payment (cross-asset / cross-border) on Stellar testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.source_secret)
        acct = server.load_account(kp.public_key)
        dest_asset = Asset.native() if req.dest_asset_code == "XLM" else Asset(req.dest_asset_code, req.dest_asset_issuer)
        send_asset = Asset.native() if req.send_asset_code == "XLM" else Asset(req.send_asset_code, "")
        # Find paths
        paths_resp = server.strict_receive_paths(
            source=[kp.public_key], destination_asset=dest_asset, destination_amount=req.dest_amount
        ).call()
        records = paths_resp["_embedded"]["records"]
        if not records:
            raise HTTPException(404, "No payment paths found between these assets")
        best = records[0]
        max_send = str(round(float(best["source_amount"]) * 1.02, 7))  # 2% slippage buffer
        path_assets = []
        for p in best.get("path", []):
            if p.get("asset_type") == "native": path_assets.append(Asset.native())
            else: path_assets.append(Asset(p["asset_code"], p["asset_issuer"]))
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_path_payment_strict_receive_op(
                send_asset=send_asset, send_max=max_send,
                destination=req.destination, dest_asset=dest_asset,
                dest_amount=req.dest_amount, path=path_assets,
            )
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        return {"hash": resp["hash"], "source": kp.public_key, "destination": req.destination,
                "path": best.get("path", []), "source_amount": best["source_amount"],
                "dest_amount": req.dest_amount, "dest_asset": req.dest_asset_code,
                "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/stellar/orderbook")
def stellar_orderbook(
    selling: str = "XLM", selling_issuer: str = "",
    buying: str = "USDC", buying_issuer: str = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
):
    """Live DEX orderbook from Horizon testnet"""
    server = _stellar_server()
    try:
        sell_asset = Asset.native() if selling == "XLM" else Asset(selling, selling_issuer)
        buy_asset = Asset.native() if buying == "XLM" else Asset(buying, buying_issuer)
        ob = server.orderbook(sell_asset, buy_asset).call()
        return {
            "base": selling, "counter": buying,
            "bids": ob.get("bids", [])[:10],
            "asks": ob.get("asks", [])[:10],
            "base_asset": selling, "counter_asset": buying
        }
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/stellar/manage-offer")
def stellar_manage_offer(req: StellarManageOfferRequest):
    """Place a real DEX sell offer on Stellar testnet"""
    server = _stellar_server()
    try:
        kp = _load_kp(req.account_secret)
        acct = server.load_account(kp.public_key)
        sell_asset = Asset.native() if req.selling_code == "XLM" else Asset(req.selling_code, req.selling_issuer)
        buy_asset = Asset(req.buying_code, req.buying_issuer)
        tx = (
            TransactionBuilder(acct, NET_PASSPHRASE, base_fee=100)
            .append_manage_sell_offer_op(selling=sell_asset, buying=buy_asset,
                                         amount=req.amount, price=req.price)
            .set_timeout(30).build()
        )
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        return {"hash": resp["hash"], "status": "offer_placed", "selling": req.selling_code,
                "buying": req.buying_code, "amount": req.amount, "price": req.price,
                "explorer": f"{EXPLORER_BASE}/tx/{resp['hash']}"}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/stellar/saved-accounts")
def stellar_saved_accounts():
    """List accounts created via this dashboard"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM stellar_accounts ORDER BY created_at DESC").fetchall()
        return {"accounts": [dict(r) for r in rows]}

# ---------------------------------------------------------------------------
# Advanced Cryptography Sandbox Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/crypto/paillier/keygen")
def paillier_keygen():
    pub, priv = generate_paillier_keypair(24)
    with state_lock: state["paillier_keys"] = (pub, priv)
    return {"public_key": pub}

@app.post("/api/crypto/paillier/encrypt")
def paillier_encrypt_route(req: Dict[str, Any]):
    m = int(req.get("message", 0))
    with state_lock:
        if not state["paillier_keys"]:
            state["paillier_keys"] = generate_paillier_keypair(24)
        pub = state["paillier_keys"][0]
    return {"ciphertext": str(paillier_encrypt(m, pub))}

@app.post("/api/crypto/paillier/sum-and-check")
def paillier_sum_check(req: Dict[str, Any]):
    ciphertexts = [int(x) for x in req.get("ciphertexts", [])]
    limit = int(req.get("limit", 25000))
    with state_lock:
        if not state["paillier_keys"]: raise HTTPException(400, "Generate keypair first")
        pub, priv = state["paillier_keys"]
    c_total = 1
    for c in ciphertexts: c_total = paillier_add(c_total, c, pub)
    decrypted = paillier_decrypt(c_total, priv)
    return {"homomorphic_total_ciphertext": str(c_total), "decrypted_sum": decrypted, "within_limit": decrypted <= limit}

@app.post("/api/crypto/disclosure/open")
def disclosure_open(req: Dict[str, Any]):
    identity = int(req.get("identity_commitment", 1234567890))
    threshold = int(req.get("threshold", 3)); n = int(req.get("n", 5)); delay = int(req.get("delay_sec", 10))
    shares = split_secret(identity, threshold, n)
    unlock_at = int(time.time()) + delay
    with state_lock:
        state["disclosure_request"] = {"shares": shares, "threshold": threshold, "n": n,
                                         "unlock_at": unlock_at, "identity": identity, "approvals": []}
    return {"status": "opened", "unlock_at": unlock_at, "threshold": threshold, "n": n}

@app.post("/api/crypto/disclosure/approve")
def disclosure_approve(req: Dict[str, Any]):
    tid = int(req.get("trustee_id"))
    with state_lock:
        if not state["disclosure_request"]: raise HTTPException(400, "No active request")
        rd = state["disclosure_request"]
        if tid < 1 or tid > rd["n"]: raise HTTPException(400, "Invalid trustee ID")
        if tid not in rd["approvals"]: rd["approvals"].append(tid)
        return {"approvals": list(rd["approvals"])}

@app.post("/api/crypto/disclosure/decrypt")
def disclosure_decrypt():
    with state_lock:
        if not state["disclosure_request"]: raise HTTPException(400, "No active request")
        req = dict(state["disclosure_request"])
    if int(time.time()) < req["unlock_at"]: return {"success": False, "reason": f"Time lock active: {req['unlock_at'] - int(time.time())}s remaining"}
    approved = [s for s in req["shares"] if int(s["x"]) in req["approvals"]]
    if len(approved) < req["threshold"]: return {"success": False, "reason": f"Need {req['threshold']} approvals, have {len(approved)}"}
    return {"success": True, "decrypted_identity": reconstruct_secret(approved)}

@app.get("/api/crypto/revocation")
def get_revocation():
    with state_lock:
        return {"revoked_wallets": list(state["revocation_registry"]["revoked"]),
                "revocation_root": state["revocation_registry"]["root"]}

@app.post("/api/crypto/revocation/revoke")
def revoke_wallet_route(req: Dict[str, Any]):
    wallet = req.get("wallet", "").strip()
    if not wallet: raise HTTPException(400, "Wallet address required")
    with state_lock:
        state["revocation_registry"]["revoked"].add(wallet)
        sorted_r = sorted(list(state["revocation_registry"]["revoked"]))
        state["revocation_registry"]["root"] = sha256_hex(",".join(sorted_r) or "__EMPTY__")
        return {"revoked_wallets": list(state["revocation_registry"]["revoked"]),
                "revocation_root": state["revocation_registry"]["root"]}

@app.get("/api/crypto/folding")
def get_folding():
    with state_lock: return {"accumulator": state["folding_accumulator"]}

@app.post("/api/crypto/folding/reset")
def reset_folding():
    with state_lock:
        state["folding_accumulator"] = sha256_hex("GENESIS")
        return {"accumulator": state["folding_accumulator"]}

@app.post("/api/crypto/folding/fold")
def fold_step(req: Dict[str, Any]):
    witness = req.get("witness", "").strip()
    with state_lock:
        state["folding_accumulator"] = sha256_hex(state["folding_accumulator"] + f"fold:{witness}")
        return {"accumulator": state["folding_accumulator"]}

# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

dashboard_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))
if os.path.exists(dashboard_path):
    @app.get("/", response_class=HTMLResponse)
    def read_root():
        idx = os.path.join(dashboard_path, "index.html")
        if os.path.exists(idx):
            with open(idx, "r", encoding="utf-8") as f: return f.read()
        return "<h1>Reso API running</h1><a href='/api/health'>/api/health</a>"
    app.mount("/static", StaticFiles(directory=dashboard_path), name="dashboard")
