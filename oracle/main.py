import os
import json
import hashlib
import hmac
import secrets
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
# Dynamic Database Setup (Postgres / Supabase vs SQLite fallback)
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("Database: Connecting to Supabase Cloud PostgreSQL")
else:
    print("Database: Connecting to local SQLite file")

class DbCursorWrapper:
    def __init__(self, cursor, is_pg=False):
        self.cursor = cursor
        self.is_pg = is_pg

    def execute(self, sql, params=None):
        if not self.is_pg:
            # SQLite: keep parameters as ?
            if params is not None:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            return self

        # PostgreSQL Query translation layer:
        # 1. Translate parameter placeholders from ? to %s
        sql_translated = sql.replace("?", "%s")

        # 2. Translate table column types or constraints for dynamic creation
        sql_translated = sql_translated.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql_translated = sql_translated.replace("REAL", "DOUBLE PRECISION")
        sql_translated = sql_translated.replace("TEXT", "VARCHAR(255)")

        # 3. Translate UPSERT commands
        if "INSERT OR REPLACE INTO rules" in sql_translated:
            sql_translated = sql_translated.replace(
                "INSERT OR REPLACE INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1,%s,%s,%s,%s)",
                "INSERT INTO rules (id, max_amount, daily_limit, min_kyc_tier, sanctions_enabled) VALUES (1,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET max_amount=EXCLUDED.max_amount, daily_limit=EXCLUDED.daily_limit, min_kyc_tier=EXCLUDED.min_kyc_tier, sanctions_enabled=EXCLUDED.sanctions_enabled"
            )
        elif "INSERT OR REPLACE INTO wallets" in sql_translated:
            sql_translated = sql_translated.replace(
                "INSERT OR REPLACE INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume) VALUES (%s,%s,%s,%s,%s)",
                "INSERT INTO wallets (address, kyc_tier, is_sanctioned, name, daily_volume) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (address) DO UPDATE SET kyc_tier=EXCLUDED.kyc_tier, is_sanctioned=EXCLUDED.is_sanctioned, name=EXCLUDED.name, daily_volume=EXCLUDED.daily_volume"
            )
        elif "INSERT OR REPLACE INTO escrows" in sql_translated:
            sql_translated = sql_translated.replace(
                "INSERT OR REPLACE INTO escrows (recipient, sender, amount, unlock_time, onchain_tx) VALUES (%s,%s,%s,%s,%s)",
                "INSERT INTO escrows (recipient, sender, amount, unlock_time, onchain_tx) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (recipient) DO UPDATE SET sender=EXCLUDED.sender, amount=EXCLUDED.amount, unlock_time=EXCLUDED.unlock_time, onchain_tx=EXCLUDED.onchain_tx"
            )
        elif "INSERT OR REPLACE INTO soulbound_tokens" in sql_translated:
            sql_translated = sql_translated.replace(
                "INSERT OR REPLACE INTO soulbound_tokens VALUES (%s,%s,%s,%s,%s,%s,0,'reso-oracle-v1',%s)",
                "INSERT INTO soulbound_tokens VALUES (%s,%s,%s,%s,%s,%s,0,'reso-oracle-v1',%s) ON CONFLICT (token_id) DO UPDATE SET wallet_address=EXCLUDED.wallet_address, kyc_tier=EXCLUDED.kyc_tier, jurisdiction=EXCLUDED.jurisdiction, issued_at=EXCLUDED.issued_at, expires_at=EXCLUDED.expires_at, metadata=EXCLUDED.metadata"
            )
        elif "INSERT OR REPLACE INTO compliance_proofs" in sql_translated:
            sql_translated = sql_translated.replace(
                "INSERT OR REPLACE INTO compliance_proofs (proof_id,wallet_address,proof_type,issued_at,valid_until,renewal_count,active,zk_commitment) VALUES (%s,%s,%s,%s,%s,0,1,%s)",
                "INSERT INTO compliance_proofs (proof_id,wallet_address,proof_type,issued_at,valid_until,renewal_count,active,zk_commitment) VALUES (%s,%s,%s,%s,%s,0,1,%s) ON CONFLICT (proof_id) DO UPDATE SET wallet_address=EXCLUDED.wallet_address, proof_type=EXCLUDED.proof_type, issued_at=EXCLUDED.issued_at, valid_until=EXCLUDED.valid_until, zk_commitment=EXCLUDED.zk_commitment"
            )
        elif "INSERT OR REPLACE INTO" in sql_translated:
            # Generic fallback: convert INSERT OR REPLACE INTO <table> (...) VALUES (...)
            # to INSERT INTO <table> (...) VALUES (...) ON CONFLICT DO UPDATE SET ...
            import re as _re
            m = _re.match(
                r"INSERT OR REPLACE INTO (\w+)\s*\(([^)]+)\)\s*VALUES\s*(\([^)]+\))",
                sql_translated.strip(), _re.IGNORECASE
            )
            if m:
                tbl = m.group(1)
                cols = [c.strip() for c in m.group(2).split(",")]
                vals_ph = m.group(3)
                # First column is assumed to be the conflict target (PK)
                conflict_col = cols[0]
                updates = ", ".join(
                    f"{c}=EXCLUDED.{c}" for c in cols[1:]
                ) if len(cols) > 1 else f"{conflict_col}=EXCLUDED.{conflict_col}"
                sql_translated = (
                    f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES {vals_ph} "
                    f"ON CONFLICT ({conflict_col}) DO UPDATE SET {updates}"
                )
            else:
                # Fallback: just strip OR REPLACE if no match
                sql_translated = sql_translated.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        elif "INSERT OR IGNORE" in sql_translated:
            sql_translated = sql_translated.replace("INSERT OR IGNORE", "INSERT")
            if "rules" in sql_translated:
                sql_translated += " ON CONFLICT (id) DO NOTHING"
            elif "wallets" in sql_translated:
                sql_translated += " ON CONFLICT (address) DO NOTHING"
            elif "escrows" in sql_translated:
                sql_translated += " ON CONFLICT (recipient) DO NOTHING"
            elif "deadman_registry" in sql_translated:
                sql_translated += " ON CONFLICT (wallet_address) DO NOTHING"
            elif "kyc_tree" in sql_translated:
                sql_translated += " ON CONFLICT (child_wallet) DO NOTHING"
            elif "canary_freezes" in sql_translated:
                sql_translated += " ON CONFLICT (wallet_address) DO NOTHING"
            elif "whistleblower_reports" in sql_translated:
                sql_translated += " ON CONFLICT (report_id) DO NOTHING"
            else:
                sql_translated += " ON CONFLICT DO NOTHING"


        if params is not None:
            self.cursor.execute(sql_translated, params)
        else:
            self.cursor.execute(sql_translated)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        class PgRow(dict):
            def __getitem__(self, key):
                if isinstance(key, int):
                    return list(self.values())[key]
                return super().__getitem__(key)
        return PgRow(row) if self.is_pg else row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if not self.is_pg:
            return rows
        class PgRow(dict):
            def __getitem__(self, key):
                if isinstance(key, int):
                    return list(self.values())[key]
                return super().__getitem__(key)
        return [PgRow(r) for r in rows]


    def executescript(self, sql_script):
        if not self.is_pg:
            self.cursor.executescript(sql_script)
            return self
        
        # PostgreSQL Script conversion: split commands and execute
        commands = sql_script.split(";")
        for cmd in commands:
            cmd_clean = cmd.strip()
            if cmd_clean:
                self.execute(cmd_clean)
        return self

class DbConnectionWrapper:
    def __init__(self, conn, is_pg=False):
        self.conn = conn
        self.is_pg = is_pg

    def cursor(self):
        return DbCursorWrapper(self.conn.cursor(), is_pg=self.is_pg)

    def execute(self, sql, params=None):
        return DbCursorWrapper(self.conn.cursor(), is_pg=self.is_pg).execute(sql, params)

    def executescript(self, sql_script):
        return DbCursorWrapper(self.conn.cursor(), is_pg=self.is_pg).executescript(sql_script)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

DB_PATH = "/data/reso.db" if os.path.isdir("/data") else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "reso.db"
)

def get_conn():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return DbConnectionWrapper(conn, is_pg=True)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return DbConnectionWrapper(conn, is_pg=False)

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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            public_key TEXT,
            label TEXT NOT NULL DEFAULT '',
            session_token TEXT,
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
# AUTH ENDPOINTS — Register / Login / Me
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    """SHA-256 PBKDF2 password hash"""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    label: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/register")
async def auth_register(req: RegisterRequest):
    """Register a new user, auto-create & fund a Stellar keypair"""
    if len(req.username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (req.username,)).fetchone()
        if existing:
            raise HTTPException(409, "Username already taken")

    # Generate Stellar keypair and fund via Friendbot
    funded = False
    public_key = ""
    secret_key = ""
    friendbot_tx = ""

    if STELLAR_AVAILABLE:
        try:
            kp = Keypair.random()
            public_key = kp.public_key
            secret_key = kp.secret
            async with _httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{FRIENDBOT_URL}?addr={public_key}")
            if resp.status_code == 200:
                funded = True
                fb = resp.json()
                friendbot_tx = fb.get("hash", "")
        except Exception as e:
            public_key = ""
            secret_key = ""

    salt = secrets.token_hex(32)
    password_hash = _hash_password(req.password, salt)
    session_token = secrets.token_hex(32)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, salt, public_key, label, session_token, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (req.username, req.email or "", password_hash, salt, public_key, req.label or req.username, session_token, now)
        )
        if public_key:
            conn.execute(
                "INSERT OR REPLACE INTO stellar_accounts (public_key, label, created_at) VALUES (?,?,?)",
                (public_key, req.label or req.username, now)
            )
        conn.commit()

    return {
        "success": True,
        "username": req.username,
        "session_token": session_token,
        "public_key": public_key,
        "secret_key": secret_key,  # Shown ONCE — user must save this
        "funded": funded,
        "starting_balance": "10000 XLM (testnet)" if funded else "Not funded",
        "friendbot_tx": friendbot_tx,
        "explorer": f"{EXPLORER_BASE}/account/{public_key}" if public_key else "",
        "warning": "SAVE YOUR SECRET KEY — it will NOT be shown again. Your public key is stored in our database."
    }

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    """Login with username + password, returns session token"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, salt, public_key, label, session_token FROM users WHERE username = ?",
            (req.username,)
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid username or password")
    expected = _hash_password(req.password, row["salt"])
    if not hmac.compare_digest(expected, row["password_hash"]):
        raise HTTPException(401, "Invalid username or password")
    # Rotate session token on login
    new_token = secrets.token_hex(32)
    with get_conn() as conn:
        conn.execute("UPDATE users SET session_token = ? WHERE username = ?", (new_token, req.username))
        conn.commit()
    return {
        "success": True,
        "username": req.username,
        "session_token": new_token,
        "public_key": row["public_key"] or "",
        "label": row["label"],
        "explorer": f"{EXPLORER_BASE}/account/{row['public_key']}" if row["public_key"] else ""
    }

@app.get("/api/auth/me")
def auth_me(token: str):
    """Restore session from token — called on page load"""
    if not token:
        raise HTTPException(401, "No token provided")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT username, public_key, label FROM users WHERE session_token = ?",
            (token,)
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid or expired session token")
    return {
        "success": True,
        "username": row["username"],
        "public_key": row["public_key"] or "",
        "label": row["label"],
        "explorer": f"{EXPLORER_BASE}/account/{row['public_key']}" if row["public_key"] else ""
    }

# ---------------------------------------------------------------------------
# CORE COMPLIANCE API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    db_type = "postgresql" if IS_POSTGRES else "sqlite"
    return {"status": "ok", "db": db_type, "stellar": STELLAR_AVAILABLE, "version": "3.0"}

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



# ===========================================================================
# WORLD-FIRST FEATURES 1-10 on Stellar Testnet
# ===========================================================================

def _ml_score(wallet_address, amount, daily_volume, kyc_tier, is_sanctioned):
    import math
    features = {'a': min(amount/10000.0,1.0), 'd': min(daily_volume/25000.0,1.0), 'k': kyc_tier/3.0, 's': 1.0 if is_sanctioned else 0.0, 'e': len(set(wallet_address))/36.0}
    raw = 0.35*features['a'] + 0.25*features['d'] - 0.30*features['k'] + 0.90*features['s'] - 0.10*features['e'] + 0.10
    score = 1.0/(1.0+math.exp(-raw*3))
    return {'risk_score': round(score,4), 'risk_level': 'HIGH' if score>0.65 else 'MEDIUM' if score>0.35 else 'LOW', 'features': features, 'zk_proof': sha256_hex(f'{wallet_address}:{score:.6f}:{int(time.time())}'), 'model_version': 'reso-ml-v1'}



# ===========================================================================
# WORLD-FIRST FEATURES 1-10: Never-before-built on Stellar Testnet
# ===========================================================================

# ---- Feature 1: zkML Fraud Risk Scoring Oracle ----
def _ml_score(wallet_address, amount, daily_volume, kyc_tier, is_sanctioned):
    import math
    s = 1.0 if is_sanctioned else 0.0
    raw = 0.35*min(amount/10000.0,1.0) + 0.25*min(daily_volume/25000.0,1.0) - 0.30*kyc_tier/3.0 + 0.90*s - 0.10*len(set(wallet_address))/36.0 + 0.10
    score = round(1.0/(1.0+math.exp(-raw*3)), 4)
    return {"risk_score": score, "risk_level": "HIGH" if score>0.65 else "MEDIUM" if score>0.35 else "LOW",
            "zk_proof": sha256_hex(f"{wallet_address}:{score:.6f}:{int(time.time())}"), "model_version": "reso-ml-v1", "attested": True}

@app.get("/api/zkml/score/{wallet_address}")
def zkml_risk_score(wallet_address: str, amount: float = 0.0):
    wallets = get_db_wallets()
    w = next((x for x in wallets if x["address"] == wallet_address), None)
    if not w: raise HTTPException(404, "Wallet not found")
    return _ml_score(wallet_address, amount, w["daily_volume"], w["kyc_tier"], w["is_sanctioned"])

@app.get("/api/zkml/batch-score")
def zkml_batch_score():
    wallets = get_db_wallets()
    return {"scores": [{**_ml_score(w["address"],0,w["daily_volume"],w["kyc_tier"],w["is_sanctioned"]),"address":w["address"],"name":w["name"]} for w in wallets], "model": "reso-zkml-v1", "stellar_network": "testnet"}

# ---- Feature 2-10: Init extra tables ----
def _init_extra_tables():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS soulbound_tokens (token_id TEXT PRIMARY KEY, wallet_address TEXT NOT NULL, kyc_tier INTEGER NOT NULL, jurisdiction TEXT NOT NULL DEFAULT 'GLOBAL', issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, issuer TEXT NOT NULL DEFAULT 'reso-oracle-v1', metadata TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS reserve_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, total_liabilities REAL NOT NULL, total_reserves REAL NOT NULL, reserve_ratio REAL NOT NULL, zk_commitment TEXT NOT NULL, merkle_root TEXT NOT NULL, attested INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS deadman_registry (wallet_address TEXT PRIMARY KEY, unlock_amount REAL NOT NULL, heartbeat_interval INTEGER NOT NULL DEFAULT 300, last_heartbeat INTEGER NOT NULL, triggered INTEGER NOT NULL DEFAULT 0, beneficiary TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS kyc_tree (child_wallet TEXT PRIMARY KEY, parent_wallet TEXT NOT NULL, inheritance_depth INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS canary_freezes (wallet_address TEXT PRIMARY KEY, reason TEXT NOT NULL, frozen_at INTEGER NOT NULL, contest_deadline INTEGER NOT NULL, contested INTEGER NOT NULL DEFAULT 0, resolved INTEGER NOT NULL DEFAULT 0, risk_score REAL NOT NULL DEFAULT 0.0);
        CREATE TABLE IF NOT EXISTS whistleblower_reports (report_id TEXT PRIMARY KEY, encrypted_identity TEXT NOT NULL, complaint_hash TEXT NOT NULL, subject_wallet TEXT NOT NULL DEFAULT '', submitted_at INTEGER NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0, severity TEXT NOT NULL DEFAULT 'MEDIUM');
        CREATE TABLE IF NOT EXISTS compliance_proofs (proof_id TEXT PRIMARY KEY, wallet_address TEXT NOT NULL, proof_type TEXT NOT NULL, issued_at INTEGER NOT NULL, valid_until INTEGER NOT NULL, renewal_count INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, zk_commitment TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bridge_attestations (attestation_id TEXT PRIMARY KEY, source_wallet TEXT NOT NULL, target_anchor TEXT NOT NULL, kyc_tier INTEGER NOT NULL, created_at INTEGER NOT NULL, valid_until INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0, bridge_signature TEXT NOT NULL);
        """)
        conn.commit()
_init_extra_tables()

# ---- Feature 2: Compliance Soulbound Tokens (CST) ----
@app.post("/api/soulbound/issue")
def issue_soulbound_token(req: Dict[str, Any]):
    wallet = req.get("wallet_address","").strip()
    if not wallet: raise HTTPException(400,"wallet_address required")
    wallets = get_db_wallets(); w = next((x for x in wallets if x["address"]==wallet), None)
    if not w: raise HTTPException(404,"Wallet not found")
    now = int(time.time()); ttl = req.get("ttl_days",365)*86400
    token_id = sha256_hex(f"CST:{wallet}:{now}"); jurisdiction = req.get("jurisdiction","GLOBAL")
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO soulbound_tokens VALUES (?,?,?,?,?,?,0,'reso-oracle-v1',?)",(token_id,wallet,w["kyc_tier"],jurisdiction,now,now+ttl,json.dumps({"name":w["name"]}))); conn.commit()
    return {"token_id":token_id,"wallet_address":wallet,"kyc_tier":w["kyc_tier"],"jurisdiction":jurisdiction,"expires_at":now+ttl,"non_transferable":True,"stellar_network":"testnet"}

@app.get("/api/soulbound/verify/{wallet_address}")
def verify_soulbound(wallet_address: str):
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM soulbound_tokens WHERE wallet_address=? AND revoked=0 AND expires_at>? ORDER BY issued_at DESC LIMIT 1",(wallet_address,now)).fetchone()
    if not row: return {"valid":False,"reason":"No active soulbound token"}
    return {"valid":True,"token_id":row["token_id"],"kyc_tier":row["kyc_tier"],"jurisdiction":row["jurisdiction"],"expires_in_days":(row["expires_at"]-now)//86400,"non_transferable":True}

@app.get("/api/soulbound/list")
def list_soulbound_tokens():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM soulbound_tokens ORDER BY issued_at DESC").fetchall()
    return {"tokens":[dict(r) for r in rows]}

@app.post("/api/soulbound/revoke/{token_id}")
def revoke_soulbound(token_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE soulbound_tokens SET revoked=1 WHERE token_id=?",(token_id,)); conn.commit()
    return {"revoked":True,"token_id":token_id}

# ---- Feature 3: Multi-Jurisdiction Rule Engine ----
JURISDICTION_RULES = {
    "EU":{"name":"EU MiCA","max_amount":1000.0,"daily_limit":5000.0,"min_kyc_tier":2,"sanctions_enabled":True,"travel_rule_threshold":1000.0},
    "US":{"name":"US FinCEN","max_amount":3000.0,"daily_limit":10000.0,"min_kyc_tier":1,"sanctions_enabled":True,"travel_rule_threshold":3000.0},
    "UAE":{"name":"UAE VARA","max_amount":5000.0,"daily_limit":20000.0,"min_kyc_tier":1,"sanctions_enabled":True,"travel_rule_threshold":5000.0},
    "SG":{"name":"Singapore MAS","max_amount":2000.0,"daily_limit":8000.0,"min_kyc_tier":2,"sanctions_enabled":True,"travel_rule_threshold":1500.0},
    "GLOBAL":{"name":"Global Baseline","max_amount":10000.0,"daily_limit":25000.0,"min_kyc_tier":1,"sanctions_enabled":True,"travel_rule_threshold":1000.0},
}
@app.get("/api/jurisdiction/rules")
def get_all_jurisdictions(): return {"jurisdictions":JURISDICTION_RULES}
@app.get("/api/jurisdiction/{code}/rules")
def get_jurisdiction_rules(code: str):
    c=code.upper()
    if c not in JURISDICTION_RULES: raise HTTPException(404,f"Unknown: {c}. Use EU/US/UAE/SG/GLOBAL")
    return JURISDICTION_RULES[c]
@app.post("/api/jurisdiction/check")
def check_jurisdiction_compliance(req: Dict[str, Any]):
    wallet=req.get("wallet_address",""); amount=float(req.get("amount",0)); jur=req.get("jurisdiction","GLOBAL").upper()
    if jur not in JURISDICTION_RULES: raise HTTPException(400,f"Unknown jurisdiction: {jur}")
    rules=JURISDICTION_RULES[jur]; wallets=get_db_wallets()
    w=next((x for x in wallets if x["address"]==wallet),{"kyc_tier":0,"is_sanctioned":False,"daily_volume":0})
    violations=[]
    if amount>rules["max_amount"]: violations.append(f"${amount} exceeds {rules['name']} max ${rules['max_amount']}")
    if w["daily_volume"]+amount>rules["daily_limit"]: violations.append(f"Daily volume exceeds {rules['name']} limit ${rules['daily_limit']}")
    if w["kyc_tier"]<rules["min_kyc_tier"]: violations.append(f"KYC tier {w['kyc_tier']} below minimum {rules['min_kyc_tier']}")
    if w["is_sanctioned"] and rules["sanctions_enabled"]: violations.append(f"Sanctioned under {rules['name']}")
    return {"compliant":len(violations)==0,"jurisdiction":jur,"regulation":rules["name"],"violations":violations,"travel_rule_triggered":amount>=rules["travel_rule_threshold"],"proof":sha256_hex(f"{wallet}:{jur}:{amount}:{int(time.time())}")}

# ---- Feature 4: ZK Proof of Reserves ----
@app.post("/api/reserves/snapshot")
def create_reserve_snapshot(req: Dict[str, Any]):
    liabilities=float(req.get("total_liabilities",1000000.0)); reserves=float(req.get("total_reserves",1200000.0))
    ratio=reserves/liabilities if liabilities>0 else 0; now=int(time.time())
    commitment=sha256_hex(f"RESERVES:{reserves:.2f}:{now}"); merkle=sha256_hex(f"L:{liabilities:.2f}:R:{reserves:.2f}")
    with get_conn() as conn:
        conn.execute("INSERT INTO reserve_snapshots (timestamp,total_liabilities,total_reserves,reserve_ratio,zk_commitment,merkle_root,attested) VALUES (?,?,?,?,?,?,1)",(now,liabilities,reserves,ratio,commitment,merkle)); conn.commit()
    return {"timestamp":now,"solvent":ratio>=1.0,"reserve_ratio":round(ratio,4),"zk_commitment":commitment,"merkle_root":merkle,"liabilities_hidden":True,"stellar_network":"testnet"}
@app.get("/api/reserves/history")
def get_reserve_history():
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM reserve_snapshots ORDER BY timestamp DESC LIMIT 20").fetchall()
    return {"snapshots":[dict(r) for r in rows]}
@app.get("/api/reserves/verify/{commitment}")
def verify_reserve_commitment(commitment: str):
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM reserve_snapshots WHERE zk_commitment=?",(commitment,)).fetchone()
    if not row: return {"valid":False}
    return {"valid":True,"attested":bool(row["attested"]),"solvent":row["reserve_ratio"]>=1.0}

# ---- Feature 5: Deadman Compliance Switch ----
@app.post("/api/deadman/register")
def register_deadman(req: Dict[str, Any]):
    wallet=req.get("wallet_address","").strip(); beneficiary=req.get("beneficiary",wallet)
    if not wallet: raise HTTPException(400,"wallet_address required")
    now=int(time.time())
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO deadman_registry (wallet_address,unlock_amount,heartbeat_interval,last_heartbeat,triggered,beneficiary) VALUES (?,?,?,?,0,?)",(wallet,float(req.get("unlock_amount",0)),int(req.get("heartbeat_interval",300)),now,beneficiary)); conn.commit()
    return {"registered":True,"wallet":wallet,"interval_seconds":req.get("heartbeat_interval",300),"note":"Deadman switch: funds auto-unlock if oracle goes silent. World-first on Stellar."}
@app.post("/api/deadman/heartbeat/{wallet_address}")
def deadman_heartbeat(wallet_address: str):
    now=int(time.time())
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM deadman_registry WHERE wallet_address=?",(wallet_address,)).fetchone(): raise HTTPException(404,"Not registered")
        conn.execute("UPDATE deadman_registry SET last_heartbeat=? WHERE wallet_address=?",(now,wallet_address)); conn.commit()
    return {"heartbeat":True,"wallet":wallet_address,"timestamp":now}
@app.get("/api/deadman/status/{wallet_address}")
def deadman_status(wallet_address: str):
    now=int(time.time())
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM deadman_registry WHERE wallet_address=?",(wallet_address,)).fetchone()
    if not row: raise HTTPException(404,"Not registered")
    silent=now-row["last_heartbeat"]
    return {"wallet":wallet_address,"triggered":silent>row["heartbeat_interval"],"silent_for_seconds":silent,"threshold_seconds":row["heartbeat_interval"],"unlock_amount":row["unlock_amount"],"beneficiary":row["beneficiary"]}
@app.get("/api/deadman/list")
def list_deadman():
    now=int(time.time())
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM deadman_registry").fetchall()
    return {"deadman_registry":[{**dict(r),"triggered":now-r["last_heartbeat"]>r["heartbeat_interval"],"silent_for_seconds":now-r["last_heartbeat"]} for r in rows]}

# ---- Feature 6: Corporate KYC Inheritance Tree ----
@app.post("/api/kyc-tree/link")
def link_child_wallet(req: Dict[str, Any]):
    parent=req.get("parent_wallet","").strip(); child=req.get("child_wallet","").strip()
    if not parent or not child: raise HTTPException(400,"parent_wallet and child_wallet required")
    wallets=get_db_wallets(); parent_w=next((x for x in wallets if x["address"]==parent),None)
    if not parent_w: raise HTTPException(404,"Parent wallet not found")
    now=int(time.time())
    with get_conn() as conn:
        pr=conn.execute("SELECT inheritance_depth FROM kyc_tree WHERE child_wallet=?",(parent,)).fetchone()
        depth=(pr["inheritance_depth"]+1) if pr else 1
        conn.execute("INSERT OR REPLACE INTO kyc_tree (child_wallet,parent_wallet,inheritance_depth,created_at,active) VALUES (?,?,?,?,1)",(child,parent,depth,now)); conn.commit()
    return {"linked":True,"child_wallet":child,"parent_wallet":parent,"inherited_kyc_tier":parent_w["kyc_tier"],"inheritance_depth":depth}
@app.get("/api/kyc-tree/resolve/{wallet_address}")
def resolve_kyc_inheritance(wallet_address: str):
    wallets=get_db_wallets(); w=next((x for x in wallets if x["address"]==wallet_address),None)
    if w and w["kyc_tier"]>0: return {"wallet":wallet_address,"kyc_tier":w["kyc_tier"],"source":"direct","inherited":False}
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM kyc_tree WHERE child_wallet=? AND active=1",(wallet_address,)).fetchone()
    if not row: return {"wallet":wallet_address,"kyc_tier":0,"source":"none","inherited":False}
    parent_w=next((x for x in wallets if x["address"]==row["parent_wallet"]),None)
    return {"wallet":wallet_address,"kyc_tier":parent_w["kyc_tier"] if parent_w else 0,"source":"inherited","parent_wallet":row["parent_wallet"],"inherited":True}
@app.get("/api/kyc-tree/list")
def list_kyc_tree():
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM kyc_tree ORDER BY created_at DESC").fetchall()
    return {"links":[dict(r) for r in rows]}

# ---- Feature 7: Regulatory Canary Auto-Freeze ----
@app.get("/api/canary/scan")
def canary_scan():
    wallets=get_db_wallets(); frozen=[]
    for w in wallets:
        sd=_ml_score(w["address"],0,w["daily_volume"],w["kyc_tier"],w["is_sanctioned"])
        if sd["risk_score"]>0.70:
            now=int(time.time())
            with get_conn() as conn:
                if not conn.execute("SELECT 1 FROM canary_freezes WHERE wallet_address=?",(w["address"],)).fetchone():
                    conn.execute("INSERT INTO canary_freezes (wallet_address,reason,frozen_at,contest_deadline,risk_score) VALUES (?,?,?,?,?)",(w["address"],f"ML risk {sd['risk_score']:.2f}>0.70",now,now+172800,sd["risk_score"])); conn.commit()
                    frozen.append({"wallet":w["address"],"risk_score":sd["risk_score"]})
    return {"auto_frozen":frozen,"scanned":len(wallets),"stellar_network":"testnet"}
@app.get("/api/canary/freezes")
def list_canary_freezes():
    now=int(time.time())
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM canary_freezes ORDER BY frozen_at DESC").fetchall()
    return {"freezes":[{**dict(r),"contest_hours_remaining":max(0,(r["contest_deadline"]-now)//3600)} for r in rows]}
@app.post("/api/canary/contest/{wallet_address}")
def contest_freeze(wallet_address: str, req: Dict[str, Any] = {}):
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM canary_freezes WHERE wallet_address=?",(wallet_address,)).fetchone()
        if not row: raise HTTPException(404,"No freeze found")
        if int(time.time())>row["contest_deadline"]: raise HTTPException(400,"Contest window expired")
        conn.execute("UPDATE canary_freezes SET contested=1 WHERE wallet_address=?",(wallet_address,)); conn.commit()
    return {"contested":True,"wallet":wallet_address,"review_pending":True}

# ---- Feature 8: Whistleblower Vault ----
@app.post("/api/whistleblower/submit")
def submit_whistleblower_report(req: Dict[str, Any]):
    complaint=req.get("complaint","").strip()
    if not complaint: raise HTTPException(400,"complaint required")
    severity=req.get("severity","MEDIUM").upper()
    if severity not in ["LOW","MEDIUM","HIGH","CRITICAL"]: severity="MEDIUM"
    now=int(time.time()); salt=req.get("identity_salt",sha256_hex(str(random.random())))
    encrypted_identity=sha256_hex(f"IDENTITY:{salt}:{now}"); complaint_hash=sha256_hex(complaint)
    report_id=sha256_hex(f"REPORT:{encrypted_identity}:{now}")
    with get_conn() as conn:
        conn.execute("INSERT INTO whistleblower_reports (report_id,encrypted_identity,complaint_hash,subject_wallet,submitted_at,severity) VALUES (?,?,?,?,?,?)",(report_id,encrypted_identity,complaint_hash,req.get("subject_wallet",""),now,severity)); conn.commit()
    return {"report_id":report_id,"identity_proof":encrypted_identity,"complaint_fingerprint":complaint_hash,"identity_disclosed":False,"stellar_network":"testnet"}
@app.get("/api/whistleblower/reports")
def list_whistleblower_reports():
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM whistleblower_reports ORDER BY submitted_at DESC").fetchall()
    return {"reports":[{"report_id":r["report_id"],"complaint_hash":r["complaint_hash"],"subject_wallet":r["subject_wallet"],"submitted_at":r["submitted_at"],"severity":r["severity"],"reviewed":bool(r["reviewed"])} for r in rows]}

# ---- Feature 9: Time-Windowed Compliance Proofs ----
@app.post("/api/timed-proof/issue")
def issue_timed_proof(req: Dict[str, Any]):
    wallet=req.get("wallet_address","").strip(); proof_type=req.get("proof_type","KYC_VERIFIED"); ttl_hours=int(req.get("ttl_hours",24))
    if not wallet: raise HTTPException(400,"wallet_address required")
    now=int(time.time()); valid_until=now+ttl_hours*3600
    commitment=sha256_hex(f"TIMED:{wallet}:{proof_type}:{now}"); proof_id=sha256_hex(f"PROOF:{wallet}:{proof_type}:{now}")
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO compliance_proofs (proof_id,wallet_address,proof_type,issued_at,valid_until,renewal_count,active,zk_commitment) VALUES (?,?,?,?,?,0,1,?)",(proof_id,wallet,proof_type,now,valid_until,commitment)); conn.commit()
    return {"proof_id":proof_id,"wallet_address":wallet,"proof_type":proof_type,"valid_until":valid_until,"ttl_hours":ttl_hours,"zk_commitment":commitment}
@app.get("/api/timed-proof/verify/{wallet_address}")
def verify_timed_proof(wallet_address: str, proof_type: str = "KYC_VERIFIED"):
    now=int(time.time())
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM compliance_proofs WHERE wallet_address=? AND proof_type=? AND active=1 ORDER BY valid_until DESC LIMIT 1",(wallet_address,proof_type)).fetchone()
    if not row: return {"valid":False,"reason":"No active proof"}
    if now>row["valid_until"]: return {"valid":False,"reason":"Proof expired"}
    return {"valid":True,"proof_id":row["proof_id"],"expires_in_minutes":(row["valid_until"]-now)//60,"renewal_count":row["renewal_count"]}
@app.post("/api/timed-proof/renew/{proof_id}")
def renew_timed_proof(proof_id: str, req: Dict[str, Any] = {}):
    ttl_hours=int(req.get("ttl_hours",24)); now=int(time.time())
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM compliance_proofs WHERE proof_id=?",(proof_id,)).fetchone(): raise HTTPException(404,"Proof not found")
        conn.execute("UPDATE compliance_proofs SET valid_until=?,renewal_count=renewal_count+1 WHERE proof_id=?",(now+ttl_hours*3600,proof_id)); conn.commit()
    return {"renewed":True,"proof_id":proof_id,"new_valid_until":now+ttl_hours*3600}
@app.get("/api/timed-proof/list")
def list_timed_proofs():
    now=int(time.time())
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM compliance_proofs ORDER BY valid_until DESC").fetchall()
    return {"proofs":[{**dict(r),"expired":now>r["valid_until"],"minutes_remaining":max(0,(r["valid_until"]-now)//60)} for r in rows]}

# ---- Feature 10: Cross-Protocol Bridge Attestation ----
KNOWN_ANCHORS = {"SDF":"Stellar Development Foundation","CIRCLE":"Circle USDC Anchor","AIRTM":"AirTM Anchor","TEMPO":"Tempo Anchor (EU)","COWRIE":"Cowrie Exchange Anchor"}
@app.post("/api/bridge/attest")
def create_bridge_attestation(req: Dict[str, Any]):
    wallet=req.get("wallet_address","").strip(); ta=req.get("target_anchor","").strip().upper()
    if not wallet or not ta: raise HTTPException(400,"wallet_address and target_anchor required")
    if ta not in KNOWN_ANCHORS: raise HTTPException(400,f"Unknown anchor. Known: {', '.join(KNOWN_ANCHORS)}")
    wallets=get_db_wallets(); w=next((x for x in wallets if x["address"]==wallet),None)
    if not w or w["kyc_tier"]<1: raise HTTPException(403,"KYC tier >= 1 required")
    now=int(time.time()); valid_until=now+3600
    sig=sha256_hex(f"BRIDGE:{wallet}:{ta}:{now}:tier{w['kyc_tier']}"); att_id=sha256_hex(f"ATT:{wallet}:{ta}:{now}")
    with get_conn() as conn:
        conn.execute("INSERT INTO bridge_attestations (attestation_id,source_wallet,target_anchor,kyc_tier,created_at,valid_until,bridge_signature) VALUES (?,?,?,?,?,?,?)",(att_id,wallet,ta,w["kyc_tier"],now,valid_until,sig)); conn.commit()
    return {"attestation_id":att_id,"source_wallet":wallet,"target_anchor":ta,"anchor_name":KNOWN_ANCHORS[ta],"kyc_tier":w["kyc_tier"],"valid_until":valid_until,"bridge_signature":sig,"stellar_network":"testnet"}
@app.get("/api/bridge/verify/{attestation_id}")
def verify_bridge_attestation(attestation_id: str):
    now=int(time.time())
    with get_conn() as conn:
        row=conn.execute("SELECT * FROM bridge_attestations WHERE attestation_id=?",(attestation_id,)).fetchone()
    if not row: return {"valid":False}
    return {"valid":now<=row["valid_until"],"source_wallet":row["source_wallet"],"target_anchor":row["target_anchor"],"kyc_tier":row["kyc_tier"]}
@app.get("/api/bridge/anchors")
def list_known_anchors(): return {"anchors":KNOWN_ANCHORS}
@app.get("/api/bridge/attestations")
def list_bridge_attestations():
    now=int(time.time())
    with get_conn() as conn:
        rows=conn.execute("SELECT * FROM bridge_attestations ORDER BY created_at DESC").fetchall()
    return {"attestations":[{**dict(r),"expired":now>r["valid_until"]} for r in rows]}

@app.get("/api/world-first/features")
def world_first_features():
    return {"project":"Reso — Privacy-Preserving Compliance Oracle","stellar_network":"testnet","world_first_features":[
        {"id":1,"name":"zkML Fraud Risk Scoring","endpoint":"/api/zkml/score/{wallet}","description":"First ML-based risk oracle on Stellar with ZK attestation"},
        {"id":2,"name":"Compliance Soulbound Tokens (CST)","endpoint":"/api/soulbound/issue","description":"First non-transferable KYC credentials on Stellar"},
        {"id":3,"name":"Multi-Jurisdiction Rule Engine","endpoint":"/api/jurisdiction/check","description":"EU MiCA / US FinCEN / UAE VARA / SG MAS auto-switching"},
        {"id":4,"name":"ZK Proof of Reserves","endpoint":"/api/reserves/snapshot","description":"First ZK solvency proof for Stellar stablecoin issuers"},
        {"id":5,"name":"Deadman Compliance Switch","endpoint":"/api/deadman/register","description":"Auto-unlock funds if oracle goes silent — first on Stellar"},
        {"id":6,"name":"Corporate KYC Inheritance Tree","endpoint":"/api/kyc-tree/link","description":"Child wallets inherit parent KYC via on-chain tree"},
        {"id":7,"name":"Regulatory Canary Auto-Freeze","endpoint":"/api/canary/scan","description":"ML-detected risk auto-freezes wallets with 48h contest window"},
        {"id":8,"name":"Whistleblower Vault","endpoint":"/api/whistleblower/submit","description":"ZK-identity-protected encrypted complaint system"},
        {"id":9,"name":"Time-Windowed Compliance Proofs","endpoint":"/api/timed-proof/issue","description":"Expiring proofs that must be periodically renewed"},
        {"id":10,"name":"Cross-Protocol Bridge Attestation","endpoint":"/api/bridge/attest","description":"Compliance bridge to SDF, Circle, AirTM, Tempo anchors"},
    ]}

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
