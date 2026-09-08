from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

# =========================
# SECRET KEY
# =========================

SECRET_KEY = "MY_SUPER_SECRET_KEY"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60

# =========================
# PASSWORD HASHING
# =========================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# =========================
# HASH PASSWORD
# =========================

def hash_password(password):

    return pwd_context.hash(password)

# =========================
# VERIFY PASSWORD
# =========================

def verify_password(
    plain_password,
    hashed_password
):

    return pwd_context.verify(
        plain_password,
        hashed_password
    )

# =========================
# CREATE JWT TOKEN
# =========================

def create_access_token(data):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )