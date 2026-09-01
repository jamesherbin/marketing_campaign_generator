from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth, credentials

from .config import get_settings


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str | None
    name: str | None
    roles: tuple[str, ...]

    @property
    def audit_actor(self) -> str:
        return self.email or self.name or self.uid


@lru_cache
def initialize_firebase() -> firebase_admin.App:
    """Initialize Firebase Admin with Application Default Credentials once."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        settings = get_settings()
        options = {"projectId": settings.google_cloud_project} if settings.google_cloud_project else None
        return firebase_admin.initialize_app(credentials.ApplicationDefault(), options)


def require_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """Verify the Firebase session cookie forwarded by the trusted frontend."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    scheme, separator, session_cookie = authorization.partition(" ")
    if separator != " " or scheme.lower() != "firebasesession" or not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication scheme")

    try:
        claims = auth.verify_session_cookie(
            session_cookie,
            check_revoked=True,
            app=initialize_firebase(),
        )
    except (auth.InvalidSessionCookieError, auth.RevokedSessionCookieError, auth.UserDisabledError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from None
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to verify session") from None

    raw_roles = claims.get("roles")
    roles = tuple(role for role in raw_roles if isinstance(role, str)) if isinstance(raw_roles, list) else ()
    return AuthenticatedUser(
        uid=claims["uid"],
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
        name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        roles=roles,
    )
