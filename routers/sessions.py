import os
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from services.auth_service import verify_password
from services.database_service import get_support_user_for_login
from services.request_security_service import audit_event
from services.session_service import issue_session, rotate_session, revoke_session

router = APIRouter(prefix="/auth", tags=["sessions"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)


def set_session_cookies(response, access, refresh):
    secure = os.getenv("ACROBUILD_ENV", "development") == "production"
    options = {"secure": secure, "samesite": "strict", "path": "/"}
    response.set_cookie("workspace_session", access, httponly=True, max_age=900, **options)
    response.set_cookie("workspace_refresh", refresh, httponly=True, max_age=604800, **options)
    response.set_cookie("workspace_csrf", secrets.token_urlsafe(32), httponly=False, max_age=604800, **options)


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    user = get_support_user_for_login(payload.email)
    if not user or user.get("status") != "Active" or not verify_password(payload.password, user.get("password", "")):
        audit_event("login_failed")
        raise HTTPException(401, "Invalid email or password.")
    set_session_cookies(response, *issue_session(user))
    audit_event("login_succeeded", actor=user["id"])
    return {"user": {key: value for key, value in user.items() if key != "password"}}


@router.post("/refresh")
def refresh(request: Request, response: Response):
    try:
        user, tokens = rotate_session(request.cookies.get("workspace_refresh", ""))
    except ValueError as error:
        raise HTTPException(401, "Sign in again.") from error
    set_session_cookies(response, *tokens)
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    revoke_session(request.cookies.get("workspace_session", ""), request.cookies.get("workspace_refresh", ""))
    for name in ("workspace_session", "workspace_refresh", "workspace_csrf"):
        response.delete_cookie(name, path="/")
    return {"logged_out": True}
