"""Revocable browser sessions with single-use refresh tokens."""
import hashlib
import secrets
import time
from contextlib import closing

from services.auth_service import create_access_token, decode_access_token
from services.database_service import open_database_connection, get_support_user


def digest_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(user, family=None):
    family = family or secrets.token_hex(24)
    access = create_access_token({"sub": str(user["id"]), "role": user["role"], "family": family})
    claims = decode_access_token(access)
    refresh = secrets.token_urlsafe(48)
    with closing(open_database_connection()) as conn, conn:
        conn.execute("INSERT INTO security_sessions(jti,user_id,expires_at) VALUES(?,?,?)", (claims["jti"], user["id"], claims["exp"]))
        conn.execute("INSERT INTO refresh_sessions(digest,user_id,family,expires_at) VALUES(?,?,?,?)", (digest_token(refresh), user["id"], family, time.time() + 7 * 86400))
    return access, refresh


def active_session(claims):
    with closing(open_database_connection()) as conn:
        row = conn.execute("SELECT user_id FROM security_sessions WHERE jti=? AND revoked=0 AND expires_at>?", (claims["jti"], time.time())).fetchone()
    if not row:
        raise ValueError("Session expired or revoked")
    user = get_support_user(row[0])
    if not user or user["status"] != "Active":
        raise ValueError("Account unavailable")
    return {**claims, "role": user["role"], "name": user["name"], "team": user.get("team", "")}


def rotate_session(refresh):
    replay = False
    with closing(open_database_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT user_id,family,expires_at,used FROM refresh_sessions WHERE digest=?", (digest_token(refresh),)).fetchone()
        if not row or row[2] <= time.time():
            raise ValueError("Refresh session expired")
        if row[3]:
            conn.execute("UPDATE refresh_sessions SET used=1 WHERE family=?", (row[1],))
            conn.execute("UPDATE security_sessions SET revoked=1 WHERE user_id=?", (row[0],))
            replay = True
        else:
            conn.execute("UPDATE refresh_sessions SET used=1 WHERE digest=?", (digest_token(refresh),))
    if replay:
        raise ValueError("Refresh token reused; sign in again")
    user = get_support_user(row[0])
    if not user or user["status"] != "Active":
        raise ValueError("Account unavailable")
    return user, issue_session(user, row[1])


def revoke_session(access, refresh):
    with closing(open_database_connection()) as conn, conn:
        if refresh:
            conn.execute("UPDATE refresh_sessions SET used=1 WHERE family IN (SELECT family FROM refresh_sessions WHERE digest=?)", (digest_token(refresh),))
        if access:
            try:
                claims = decode_access_token(access)
                conn.execute("UPDATE security_sessions SET revoked=1 WHERE jti=?", (claims["jti"],))
            except ValueError:
                pass
