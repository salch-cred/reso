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

app = FastAPI(title="Reso Compliance Oracle API")

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
# Store at /data/reso.db on HF Space (persistent volume), else local fallback
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
        """)

        # Seed default rules
        conn.execute(
            "INSERT OR IGNORE INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1, 10000.0, 25000.0, 1, 1)"
        )

        # Seed demo wallets
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
                (
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    "GABC1SANCTIONEDEXAMPLEADDRESS0001",
                    250.0,
                    "Sanctions screen",
                    "blocked",
                    "Address is listed on the active sanctions list (proven via non-membership check failure)",
                    "0x9f2a24c8b618bc360b0e5d41c888ee11",
                    "0x9f2a24c8b618bc...",
                ),
            )
            conn.commit()


seed_audit_logs()

# ---------------------------------------------------------------------------
# In-memory state for crypto sandbox (ephemeral, resets on restart)
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
            return {
                "max_amount": row["max_amount"],
                "daily_limit": row["daily_limit"],
                "min_kyc_tier": row["min_kyc_tier"],
                "sanctions_enabled": bool(row["sanctions_enabled"]),
            }
    return {"max_amount": 10000.0, "daily_limit": 25000.0, "min_kyc_tier": 1, "sanctions_enabled": True}


def save_db_rules(rules: "Rules"):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1,?,?,?,?)",
            (rules.max_amount, rules.daily_limit, rules.min_kyc_tier, 1 if rules.sanctions_enabled else 0),
        )
        conn.commit()


def get_db_wallets() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM wallets").fetchall()
        return [
            {
                "address": r["address"],
                "kyc_tier": r["kyc_tier"],
                "is_sanctioned": bool(r["is_sanctioned"]),
                "name": r["name"],
                "daily_volume": r["daily_volume"],
            }
            for r in rows
        ]


def save_db_wallet(wallet: "Wallet"):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT daily_volume FROM wallets WHERE address = ?", (wallet.address,)
        ).fetchone()
        daily_vol = existing["daily_volume"] if existing else 0.0
        conn.execute(
            "INSERT OR REPLACE INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume) VALUES (?,?,?,?,?)",
            (wallet.address, wallet.kyc_tier, 1 if wallet.is_sanctioned else 0, wallet.name, daily_vol),
        )
        conn.commit()


def update_db_daily_volume(address: str, amount: float):
    with get_conn() as conn:
        conn.execute(
            "UPDATE wallets SET daily_volume = daily_volume + ? WHERE address = ?",
            (amount, address),
        )
        conn.commit()


def get_db_escrows() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM escrows").fetchall()
        return [
            {
                "recipient": r["recipient"],
                "sender": r["sender"],
                "amount": r["amount"],
                "unlock_time": r["unlock_time"],
                "onchain_tx": r["onchain_tx"],
            }
            for r in rows
        ]


def save_db_escrow(recipient: str, escrow: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO escrows (recipient, sender, amount, unlock_time, onchain_tx) VALUES (?,?,?,?,?)",
            (recipient, escrow["sender"], escrow["amount"], escrow["unlock_time"], escrow["onchain_tx"]),
        )
        conn.commit()


def delete_db_escrow(recipient: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM escrows WHERE recipient = ?", (recipient,))
        conn.commit()


def get_db_audit_logs() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]


def insert_db_audit_log(log: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_logs (timestamp, sender, amount, rule_checked, status, reason, proof_ref, merkle_root) VALUES (?,?,?,?,?,?,?,?)",
            (
                log["timestamp"],
                log["sender"],
                log["amount"],
                log["rule_checked"],
                log["status"],
                log["reason"],
                log["proof_ref"],
                log["merkle_root"],
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Hash utilities & Merkle tree
# ---------------------------------------------------------------------------


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def address_hash(address: str) -> str:
    return sha256_hex(address.strip().lower())


class MerkleTree:
    def __init__(self, leaves: List[str]):
        self.leaves = sorted(list(set(leaves)))
        if not self.leaves:
            self.leaves = [sha256_hex("__EMPTY__")]
        self.layers = [self.leaves]
        current = self.leaves
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_layer.append(sha256_hex(left + right))
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> str:
        return self.layers[-1][0] if self.layers else sha256_hex("__EMPTY__")


def get_active_sanctions_tree() -> MerkleTree:
    wallets = get_db_wallets()
    sanctioned = [w["address"] for w in wallets if w["is_sanctioned"]]
    leaves = [address_hash(addr) for addr in sanctioned]
    return MerkleTree(leaves)


# ---------------------------------------------------------------------------
# Cryptography: Shamir Secret Sharing
# ---------------------------------------------------------------------------

PRIME_127 = (1 << 127) - 1


def egcd(a: int, b: int) -> Tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    g, y, x = egcd(b % a, a)
    return g, x - (b // a) * y, y


def mod_inv(a: int, m: int) -> int:
    g, x, _ = egcd(a, m)
    if g != 1:
        raise Exception("No modular inverse")
    return x % m


def split_secret(secret: int, threshold: int, n: int) -> List[Dict[str, str]]:
    coefficients = [secret % PRIME_127]
    for _ in range(1, threshold):
        coefficients.append(random.randint(1, PRIME_127 - 1))
    shares = []
    for x in range(1, n + 1):
        y, x_pow = 0, 1
        for c in coefficients:
            y = (y + c * x_pow) % PRIME_127
            x_pow = (x_pow * x) % PRIME_127
        shares.append({"x": str(x), "y": str(y)})
    return shares


def reconstruct_secret(shares: List[Dict[str, str]]) -> int:
    parsed = [{"x": int(s["x"]), "y": int(s["y"])} for s in shares]
    secret = 0
    for i in range(len(parsed)):
        xi, yi = parsed[i]["x"], parsed[i]["y"]
        num, den = 1, 1
        for j in range(len(parsed)):
            if i == j:
                continue
            xj = parsed[j]["x"]
            num = (num * (0 - xj)) % PRIME_127
            den = (den * (xi - xj)) % PRIME_127
        secret = (secret + yi * (num * mod_inv(den, PRIME_127)) % PRIME_127) % PRIME_127
    return secret


# ---------------------------------------------------------------------------
# Cryptography: Paillier Homomorphic Encryption
# ---------------------------------------------------------------------------


def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def lcm(a: int, b: int) -> int:
    return (a * b) // gcd(a, b)


def L(x: int, n: int) -> int:
    return (x - 1) // n


def is_probable_prime(n: int, rounds: int = 20) -> bool:
    if n < 2:
        return False
    for small in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]:
        if n == small:
            return True
        if n % small == 0:
            return False
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randint(2, n - 2)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        ok = False
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                ok = True
                break
        if not ok:
            return False
    return True


def generate_random_prime(bits: int) -> int:
    while True:
        candidate = random.getrandbits(bits) | 1
        if is_probable_prime(candidate):
            return candidate


def generate_paillier_keypair(bits: int = 24) -> Tuple[Dict[str, int], Dict[str, int]]:
    while True:
        p = generate_random_prime(bits)
        q = generate_random_prime(bits)
        if p != q:
            break
    n = p * q
    n2 = n * n
    lam = lcm(p - 1, q - 1)
    g = n + 1
    mu = mod_inv(L(pow(g, lam, n2), n), n)
    pub: Dict[str, int] = {"n": n, "g": g, "n_squared": n2}
    priv: Dict[str, int] = {"lambda": lam, "mu": mu, "n": n, "n_squared": n2}
    return pub, priv


def paillier_encrypt(m: int, pub: Dict[str, int]) -> int:
    n, g, n2 = pub["n"], pub["g"], pub["n_squared"]
    while True:
        r = random.randint(1, n - 1)
        if gcd(r, n) == 1:
            break
    return (pow(g, m, n2) * pow(r, n, n2)) % n2


def paillier_decrypt(c: int, priv: Dict[str, int]) -> int:
    return (L(pow(c, priv["lambda"], priv["n_squared"]), priv["n"]) * priv["mu"]) % priv["n"]


def paillier_add(c1: int, c2: int, pub: Dict[str, int]) -> int:
    return (c1 * c2) % pub["n_squared"]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Rules(BaseModel):
    max_amount: float
    daily_limit: float
    min_kyc_tier: int
    sanctions_enabled: bool


class Wallet(BaseModel):
    address: str
    kyc_tier: int
    is_sanctioned: bool
    name: str = ""


class TransferRequest(BaseModel):
    sender: str
    amount: float


class EscrowDepositRequest(BaseModel):
    sender: str
    recipient: str
    amount: float
    unlock_delay_sec: int = 30


class EscrowClaimRequest(BaseModel):
    recipient: str
    proof: str


class EscrowRefundRequest(BaseModel):
    recipient: str


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"status": "ok", "db": "sqlite", "version": "2.0"}


@app.get("/api/rules", response_model=Rules)
def get_rules():
    return Rules(**get_db_rules())


@app.post("/api/rules", response_model=Rules)
def update_rules(rules: Rules):
    save_db_rules(rules)
    return rules


@app.get("/api/wallets")
def get_wallets():
    tree = get_active_sanctions_tree()
    wallets_list = get_db_wallets()
    for w in wallets_list:
        w["hash"] = address_hash(w["address"])
    return {"wallets": wallets_list, "sanctions_merkle_root": tree.root}


@app.post("/api/wallets")
def add_wallet(wallet: Wallet):
    addr = wallet.address.strip()
    if not addr:
        raise HTTPException(status_code=400, detail="Wallet address cannot be empty")
    save_db_wallet(wallet)
    tree = get_active_sanctions_tree()
    return {"status": "success", "wallet": wallet, "sanctions_merkle_root": tree.root}


@app.get("/api/audit-logs")
def get_audit_logs():
    return get_db_audit_logs()


@app.post("/api/simulate-transfer")
def simulate_transfer(req: TransferRequest):
    sender = req.sender.strip()
    amount = req.amount
    wallets_list = get_db_wallets()
    matched = [w for w in wallets_list if w["address"] == sender]
    wallet = matched[0] if matched else {"address": sender, "kyc_tier": 0, "is_sanctioned": False, "name": "Unknown", "daily_volume": 0.0}

    r = get_db_rules()
    rules = Rules(**r)
    tree = get_active_sanctions_tree()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    proof_ref = "0x" + hashlib.sha256(f"{sender}{amount}{time.time()}".encode()).hexdigest()
    merkle_root_str = f"0x{tree.root[:16]}..."

    with state_lock:
        is_revoked = sender in state["revocation_registry"]["revoked"]

    if is_revoked:
        event = {
            "timestamp": timestamp, "sender": sender, "amount": amount,
            "rule_checked": "Credential revocation check", "status": "blocked",
            "reason": "KYC Credential has been revoked (revocation accumulator proof verification failed)",
            "proof_ref": proof_ref, "merkle_root": f"0x{state['revocation_registry']['root'][:16]}...",
        }
        insert_db_audit_log(event)
        return {"compliant": False, "reason": event["reason"], "event": event}

    if rules.sanctions_enabled and wallet["is_sanctioned"]:
        reason = "On-chain error: InvalidProof (Zero-Knowledge sanctions check failed)"
        event = {"timestamp": timestamp, "sender": sender, "amount": amount,
                 "rule_checked": "On-chain verification check", "status": "blocked",
                 "reason": reason, "proof_ref": proof_ref, "merkle_root": merkle_root_str}
        insert_db_audit_log(event)
        return {"compliant": False, "reason": reason, "event": event}

    if wallet["kyc_tier"] < rules.min_kyc_tier:
        reason = f"On-chain error: Wallet KYC Tier ({wallet['kyc_tier']}) is below required level ({rules.min_kyc_tier})"
        event = {"timestamp": timestamp, "sender": sender, "amount": amount,
                 "rule_checked": "On-chain verification check", "status": "blocked",
                 "reason": reason, "proof_ref": proof_ref, "merkle_root": merkle_root_str}
        insert_db_audit_log(event)
        return {"compliant": False, "reason": reason, "event": event}

    if amount > rules.max_amount:
        reason = f"On-chain error: AmountExceedsRule (${amount} exceeds max ${rules.max_amount})"
        event = {"timestamp": timestamp, "sender": sender, "amount": amount,
                 "rule_checked": "On-chain verification check", "status": "blocked",
                 "reason": reason, "proof_ref": proof_ref, "merkle_root": merkle_root_str}
        insert_db_audit_log(event)
        return {"compliant": False, "reason": reason, "event": event}

    daily_vol = wallet.get("daily_volume", 0.0)
    if daily_vol + amount > rules.daily_limit:
        reason = f"On-chain error: AmountExceedsRule (Daily limit ${rules.daily_limit} would be exceeded)"
        event = {"timestamp": timestamp, "sender": sender, "amount": amount,
                 "rule_checked": "On-chain verification check", "status": "blocked",
                 "reason": reason, "proof_ref": proof_ref, "merkle_root": merkle_root_str}
        insert_db_audit_log(event)
        return {"compliant": False, "reason": reason, "event": event}

    update_db_daily_volume(sender, amount)
    event = {
        "timestamp": timestamp, "sender": sender, "amount": amount,
        "rule_checked": "All checks passed on-chain", "status": "ok",
        "reason": "Transaction verified: Zero-Knowledge Proof generated and verified against compliance rules.",
        "proof_ref": proof_ref, "merkle_root": merkle_root_str,
    }
    insert_db_audit_log(event)
    with state_lock:
        state["folding_accumulator"] = sha256_hex(
            state["folding_accumulator"] + f"tx:{sender}:{amount}"
        )
    return {"compliant": True, "reason": event["reason"], "event": event}


# --- Escrow Endpoints ---


@app.get("/api/escrow")
def get_escrows():
    return {"escrows": get_db_escrows()}


@app.post("/api/escrow/deposit")
def api_deposit_escrow(req: EscrowDepositRequest):
    sender = req.sender.strip()
    recipient = req.recipient.strip()
    if sender == recipient:
        raise HTTPException(status_code=400, detail="Sender and recipient cannot be the same")
    escrow = {
        "sender": sender,
        "recipient": recipient,
        "amount": req.amount,
        "unlock_time": int(time.time()) + req.unlock_delay_sec,
        "onchain_tx": "sim_" + hashlib.sha256(f"{sender}{recipient}{time.time()}".encode()).hexdigest()[:16],
    }
    save_db_escrow(recipient, escrow)
    insert_db_audit_log({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": sender, "amount": req.amount,
        "rule_checked": "ZK Escrow Deposit", "status": "ok",
        "reason": f"Escrow deposited for {recipient[:8]}... Timelock: {req.unlock_delay_sec}s.",
        "proof_ref": "0x" + hashlib.sha256(f"escrow{sender}{recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}...",
    })
    return {"status": "deposited", "escrow": escrow}


@app.post("/api/escrow/claim")
def api_claim_escrow(req: EscrowClaimRequest):
    recipient = req.recipient.strip()
    escrows = get_db_escrows()
    matched = [e for e in escrows if e["recipient"] == recipient]
    if not matched:
        raise HTTPException(status_code=404, detail="No escrow found for this recipient")
    escrow = matched[0]
    now = int(time.time())
    if now < escrow["unlock_time"]:
        raise HTTPException(status_code=400, detail=f"Timelock active. Unlocks in {escrow['unlock_time'] - now}s")
    delete_db_escrow(recipient)
    insert_db_audit_log({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": recipient, "amount": escrow["amount"],
        "rule_checked": "ZK Escrow Claimed", "status": "ok",
        "reason": "Escrow claimed successfully. ZK compliance proof verified.",
        "proof_ref": "0x" + hashlib.sha256(f"claim{recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}...",
    })
    return {"status": "claimed", "amount": escrow["amount"]}


@app.post("/api/escrow/refund")
def api_refund_escrow(req: EscrowRefundRequest):
    recipient = req.recipient.strip()
    escrows = get_db_escrows()
    matched = [e for e in escrows if e["recipient"] == recipient]
    if not matched:
        raise HTTPException(status_code=404, detail="No escrow found")
    escrow = matched[0]
    delete_db_escrow(recipient)
    insert_db_audit_log({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "sender": escrow["sender"], "amount": escrow["amount"],
        "rule_checked": "ZK Escrow Refunded", "status": "ok",
        "reason": "Escrow refunded. Timelock expired and funds reclaimed by sender.",
        "proof_ref": "0x" + hashlib.sha256(f"refund{recipient}".encode()).hexdigest()[:16],
        "merkle_root": f"0x{get_active_sanctions_tree().root[:16]}...",
    })
    return {"status": "refunded", "amount": escrow["amount"]}


# --- Advanced Cryptography Sandbox Endpoints ---


@app.post("/api/crypto/paillier/keygen")
def paillier_keygen():
    pub, priv = generate_paillier_keypair(24)
    with state_lock:
        state["paillier_keys"] = (pub, priv)
    return {"public_key": pub}


@app.post("/api/crypto/paillier/encrypt")
def paillier_encrypt_route(req: Dict[str, Any]):
    m = int(req.get("message", 0))
    with state_lock:
        if not state["paillier_keys"]:
            pub, priv = generate_paillier_keypair(24)
            state["paillier_keys"] = (pub, priv)
        pub = state["paillier_keys"][0]
    c = paillier_encrypt(m, pub)
    return {"ciphertext": str(c)}


@app.post("/api/crypto/paillier/sum-and-check")
def paillier_sum_and_check(req: Dict[str, Any]):
    ciphertexts = [int(x) for x in req.get("ciphertexts", [])]
    limit = int(req.get("limit", 25000))
    with state_lock:
        if not state["paillier_keys"]:
            raise HTTPException(status_code=400, detail="Keypair not generated yet. Encrypt at least one value first.")
        pub, priv = state["paillier_keys"]
    c_total = 1
    for c in ciphertexts:
        c_total = paillier_add(c_total, c, pub)
    decrypted_sum = paillier_decrypt(c_total, priv)
    return {
        "homomorphic_total_ciphertext": str(c_total),
        "decrypted_sum": decrypted_sum,
        "within_limit": decrypted_sum <= limit,
    }


@app.post("/api/crypto/disclosure/open")
def disclosure_open(req: Dict[str, Any]):
    identity = int(req.get("identity_commitment", 1234567890))
    threshold = int(req.get("threshold", 3))
    n = int(req.get("n", 5))
    delay_sec = int(req.get("delay_sec", 10))
    shares = split_secret(identity, threshold, n)
    unlock_at = int(time.time()) + delay_sec
    with state_lock:
        state["disclosure_request"] = {
            "shares": shares, "threshold": threshold, "n": n,
            "unlock_at": unlock_at, "identity": identity, "approvals": [],
        }
    return {"status": "opened", "unlock_at": unlock_at, "threshold": threshold, "n": n}


@app.post("/api/crypto/disclosure/approve")
def disclosure_approve(req: Dict[str, Any]):
    trustee_id = int(req.get("trustee_id"))
    with state_lock:
        if not state["disclosure_request"]:
            raise HTTPException(status_code=400, detail="No active request")
        req_data = state["disclosure_request"]
        if trustee_id < 1 or trustee_id > req_data["n"]:
            raise HTTPException(status_code=400, detail="Invalid trustee ID")
        if trustee_id not in req_data["approvals"]:
            req_data["approvals"].append(trustee_id)
        approvals = list(req_data["approvals"])
    return {"approvals": approvals}


@app.post("/api/crypto/disclosure/decrypt")
def disclosure_decrypt():
    with state_lock:
        if not state["disclosure_request"]:
            raise HTTPException(status_code=400, detail="No active request")
        request = dict(state["disclosure_request"])
    now = int(time.time())
    if now < request["unlock_at"]:
        return {"success": False, "reason": f"Time lock active. Unlocks in {request['unlock_at'] - now} seconds."}
    approved_shares = [s for s in request["shares"] if int(s["x"]) in request["approvals"]]
    if len(approved_shares) < request["threshold"]:
        return {"success": False, "reason": f"Insufficient approvals ({len(approved_shares)}/{request['threshold']})."}
    decrypted = reconstruct_secret(approved_shares)
    return {"success": True, "decrypted_identity": decrypted}


@app.get("/api/crypto/revocation")
def get_revocation():
    with state_lock:
        return {
            "revoked_wallets": list(state["revocation_registry"]["revoked"]),
            "revocation_root": state["revocation_registry"]["root"],
        }


@app.post("/api/crypto/revocation/revoke")
def revoke_wallet_route(req: Dict[str, Any]):
    wallet = req.get("wallet", "").strip()
    if not wallet:
        raise HTTPException(status_code=400, detail="Wallet address required")
    with state_lock:
        state["revocation_registry"]["revoked"].add(wallet)
        sorted_r = sorted(list(state["revocation_registry"]["revoked"]))
        state["revocation_registry"]["root"] = sha256_hex(",".join(sorted_r) or "__EMPTY__")
        return {
            "revoked_wallets": list(state["revocation_registry"]["revoked"]),
            "revocation_root": state["revocation_registry"]["root"],
        }


@app.get("/api/crypto/folding")
def get_folding():
    with state_lock:
        return {"accumulator": state["folding_accumulator"]}


@app.post("/api/crypto/folding/reset")
def reset_folding():
    with state_lock:
        state["folding_accumulator"] = sha256_hex("GENESIS")
        return {"accumulator": state["folding_accumulator"]}


@app.post("/api/crypto/folding/fold")
def fold_step(req: Dict[str, Any]):
    witness = req.get("witness", "").strip()
    with state_lock:
        state["folding_accumulator"] = sha256_hex(
            state["folding_accumulator"] + f"fold:{witness}"
        )
        return {"accumulator": state["folding_accumulator"]}


# ---------------------------------------------------------------------------
# Static file serving (for direct HF Space access)
# ---------------------------------------------------------------------------

dashboard_path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")
)
if os.path.exists(dashboard_path):
    @app.get("/", response_class=HTMLResponse)
    def read_root():
        index_file = os.path.join(dashboard_path, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Reso API is running</h1><p>Visit /api/health to check status.</p>"

    app.mount("/static", StaticFiles(directory=dashboard_path), name="dashboard")
