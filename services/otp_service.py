import hashlib
import os
import re
import secrets
import time

from services.database_service import open_database_connection
from services.email_service import send_email

OTP_TTL_SECONDS = 300
OTP_RESEND_SECONDS = 45
OTP_MAX_ATTEMPTS = 5
ACCESS_TOKEN_TTL_SECONDS = 600
IP_WINDOW_SECONDS = 600
IP_MAX_REQUESTS = 10
ACCOUNT_WINDOW_SECONDS = 3600
ACCOUNT_MAX_REQUESTS = 6


def normalize_email(value):
    return str(value or "").strip().lower()


def is_valid_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalize_email(value)))


def _digest(value):
    pepper = os.getenv("OTP_SECRET", "").strip()
    if len(pepper) < 16:
        raise RuntimeError("OTP_SECRET must be configured with at least 16 characters.")
    return hashlib.sha256(f"{value}:{pepper}".encode()).hexdigest()


def hash_otp(email, code):
    return _digest(f"{email}:{code}")


def _ensure_store(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS email_otp_records (
            email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at REAL NOT NULL,
            sent_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS email_access_tokens (
            token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS otp_request_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
            client_ip TEXT NOT NULL, requested_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_otp_audit_ip_time ON otp_request_audit(client_ip, requested_at);
        CREATE INDEX IF NOT EXISTS idx_otp_audit_email_time ON otp_request_audit(email, requested_at);
    """)


def cleanup_expired_records(conn, now):
    conn.execute("DELETE FROM email_otp_records WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM email_access_tokens WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM otp_request_audit WHERE requested_at <= ?", (now - ACCOUNT_WINDOW_SECONDS,))


def request_email_otp(email, client_ip="unknown"):
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        raise ValueError("Enter a valid email address.")
    now = time.time()
    conn = open_database_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_store(conn)
        cleanup_expired_records(conn, now)
        existing = conn.execute("SELECT sent_at FROM email_otp_records WHERE email = ?", (normalized_email,)).fetchone()
        if existing and now - float(existing[0]) < OTP_RESEND_SECONDS:
            retry_after = max(1, int(OTP_RESEND_SECONDS - (now - float(existing[0]))))
            raise ValueError(f"Please wait {retry_after} seconds before requesting another code.")
        ip_count = conn.execute(
            "SELECT COUNT(*) FROM otp_request_audit WHERE client_ip = ? AND requested_at > ?",
            (str(client_ip), now - IP_WINDOW_SECONDS)).fetchone()[0]
        account_count = conn.execute(
            "SELECT COUNT(*) FROM otp_request_audit WHERE email = ? AND requested_at > ?",
            (normalized_email, now - ACCOUNT_WINDOW_SECONDS)).fetchone()[0]
        if ip_count >= IP_MAX_REQUESTS or account_count >= ACCOUNT_MAX_REQUESTS:
            raise ValueError("Too many verification requests. Try again later.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        send_email(normalized_email, "Your Acrobuild verification code", (
            f"Your Acrobuild project support verification code is {code}.\n\n"
            "This code expires in 5 minutes. Do not share it with anyone."))
        conn.execute(
            "INSERT INTO email_otp_records(email,code_hash,expires_at,sent_at,attempts) VALUES(?,?,?,?,0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,sent_at=excluded.sent_at,attempts=0",
            (normalized_email, hash_otp(normalized_email, code), now + OTP_TTL_SECONDS, now))
        conn.execute("INSERT INTO otp_request_audit(email,client_ip,requested_at) VALUES(?,?,?)", (normalized_email, str(client_ip), now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"expires_in": OTP_TTL_SECONDS, "resend_after": OTP_RESEND_SECONDS}


def verify_email_otp(email, code):
    normalized_email = normalize_email(email)
    normalized_code = re.sub(r"\D", "", str(code or ""))
    if len(normalized_code) != 6:
        raise ValueError("Enter the six-digit verification code.")
    now = time.time()
    conn = open_database_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_store(conn)
        cleanup_expired_records(conn, now)
        record = conn.execute("SELECT code_hash,attempts FROM email_otp_records WHERE email = ?", (normalized_email,)).fetchone()
        if not record:
            raise ValueError("The code has expired. Request a new verification code.")
        if int(record[1]) >= OTP_MAX_ATTEMPTS:
            conn.execute("DELETE FROM email_otp_records WHERE email = ?", (normalized_email,))
            conn.commit()
            raise ValueError("Too many incorrect attempts. Request a new verification code.")
        if not secrets.compare_digest(record[0], hash_otp(normalized_email, normalized_code)):
            attempts = int(record[1]) + 1
            conn.execute("UPDATE email_otp_records SET attempts = ? WHERE email = ?", (attempts, normalized_email))
            conn.commit()
            raise ValueError(f"Incorrect verification code. {OTP_MAX_ATTEMPTS - attempts} attempts remaining.")
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM email_otp_records WHERE email = ?", (normalized_email,))
        conn.execute("INSERT INTO email_access_tokens(token_hash,email,expires_at) VALUES(?,?,?)", (_digest(token), normalized_email, now + ACCESS_TOKEN_TTL_SECONDS))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"access_token": token, "expires_in": ACCESS_TOKEN_TTL_SECONDS}


def validate_email_access_token(email, access_token):
    if not access_token:
        return False
    now = time.time()
    conn = open_database_connection()
    try:
        _ensure_store(conn)
        cleanup_expired_records(conn, now)
        row = conn.execute("SELECT email FROM email_access_tokens WHERE token_hash = ? AND expires_at > ?", (_digest(str(access_token)), now)).fetchone()
        conn.commit()
        return bool(row and row[0] == normalize_email(email))
    finally:
        conn.close()
