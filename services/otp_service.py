import hashlib
import os
import re
import secrets
import time
from threading import Lock

from services.email_service import send_email

# -----------------------------------
# OTP CONFIGURATION
# -----------------------------------

OTP_TTL_SECONDS = 300
OTP_RESEND_SECONDS = 45
OTP_MAX_ATTEMPTS = 5
ACCESS_TOKEN_TTL_SECONDS = 600
OTP_RECORDS = {}
ACCESS_TOKENS = {}
OTP_LOCK = Lock()


def normalize_email(value):
    return str(value or "").strip().lower()


def is_valid_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalize_email(value)))


def hash_otp(email, code):
    pepper = os.getenv("OTP_SECRET", "local-development-otp-secret")
    return hashlib.sha256(f"{email}:{code}:{pepper}".encode("utf-8")).hexdigest()


def cleanup_expired_records(now):
    for email in list(OTP_RECORDS):
        if OTP_RECORDS[email]["expires_at"] <= now:
            OTP_RECORDS.pop(email, None)

    for token in list(ACCESS_TOKENS):
        if ACCESS_TOKENS[token]["expires_at"] <= now:
            ACCESS_TOKENS.pop(token, None)


def request_email_otp(email):
    normalized_email = normalize_email(email)

    if not is_valid_email(normalized_email):
        raise ValueError("Enter a valid email address.")

    now = time.time()

    with OTP_LOCK:
        cleanup_expired_records(now)
        existing = OTP_RECORDS.get(normalized_email)

        if existing and now - existing["sent_at"] < OTP_RESEND_SECONDS:
            retry_after = max(1, int(OTP_RESEND_SECONDS - (now - existing["sent_at"])))
            raise ValueError(f"Please wait {retry_after} seconds before requesting another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    send_email(
        normalized_email,
        "Your Acrobuild verification code",
        chr(10).join([
            f"Your Acrobuild project support verification code is {code}.",
            "",
            "This code expires in 5 minutes. Do not share it with anyone.",
            "If you did not request this code, you can ignore this email.",
        ]),
    )

    with OTP_LOCK:
        OTP_RECORDS[normalized_email] = {
            "code_hash": hash_otp(normalized_email, code),
            "expires_at": now + OTP_TTL_SECONDS,
            "sent_at": now,
            "attempts": 0,
        }

    return {"expires_in": OTP_TTL_SECONDS, "resend_after": OTP_RESEND_SECONDS}


def verify_email_otp(email, code):
    normalized_email = normalize_email(email)
    normalized_code = re.sub(r"\D", "", str(code or ""))

    if len(normalized_code) != 6:
        raise ValueError("Enter the six-digit verification code.")

    now = time.time()

    with OTP_LOCK:
        cleanup_expired_records(now)
        record = OTP_RECORDS.get(normalized_email)

        if not record:
            raise ValueError("The code has expired. Request a new verification code.")

        if record["attempts"] >= OTP_MAX_ATTEMPTS:
            OTP_RECORDS.pop(normalized_email, None)
            raise ValueError("Too many incorrect attempts. Request a new verification code.")

        if not secrets.compare_digest(record["code_hash"], hash_otp(normalized_email, normalized_code)):
            record["attempts"] += 1
            remaining = OTP_MAX_ATTEMPTS - record["attempts"]
            raise ValueError(f"Incorrect verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.")

        OTP_RECORDS.pop(normalized_email, None)
        access_token = secrets.token_urlsafe(32)
        ACCESS_TOKENS[access_token] = {
            "email": normalized_email,
            "expires_at": now + ACCESS_TOKEN_TTL_SECONDS,
        }

    return {"access_token": access_token, "expires_in": ACCESS_TOKEN_TTL_SECONDS}


def validate_email_access_token(email, access_token):
    normalized_email = normalize_email(email)
    now = time.time()

    with OTP_LOCK:
        cleanup_expired_records(now)
        record = ACCESS_TOKENS.get(str(access_token or ""))

        if not record or record["email"] != normalized_email:
            return False

        return True