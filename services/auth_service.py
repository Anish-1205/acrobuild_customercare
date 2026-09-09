import os
from uuid import uuid4

from jose import JWTError, jwt
import bcrypt
from datetime import datetime, timedelta, timezone

# =========================
# SECRET KEY
# =========================

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "").strip()

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
TOKEN_ISSUER = "acrobuild-support"
TOKEN_AUDIENCE = "acrobuild-workspace"

# =========================
# PASSWORD HASHING
# =========================

def hash_password(password):
    encoded = str(password or "").encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password is too long.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")

# =========================
# VERIFY PASSWORD
# =========================

def verify_password(
    plain_password,
    hashed_password
):

    try:
        return bcrypt.checkpw(str(plain_password or "").encode("utf-8"), str(hashed_password or "").encode("ascii"))
    except (ValueError, TypeError):
        return False

# =========================
# CREATE JWT TOKEN
# =========================

def create_access_token(data):

    if len(SECRET_KEY) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must be configured with at least 32 characters.")

    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "jti": uuid4().hex,
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def decode_access_token(token):
    if len(SECRET_KEY) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must be configured with at least 32 characters.")
    try:
        return jwt.decode(str(token or ""), SECRET_KEY, algorithms=[ALGORITHM],
                          audience=TOKEN_AUDIENCE, issuer=TOKEN_ISSUER,
                          options={"require_exp": True, "require_iat": True, "require_jti": True,
                                   "require_aud": True, "require_iss": True, "require_sub": True})
    except JWTError as error:
        raise ValueError("Invalid or expired access token.") from error
