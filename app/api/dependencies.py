from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import Asset, Site, User
from app.models.enums import UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode a bearer JWT and load its current user record from the database."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["user_id"])
        organization_id = int(claims["organization_id"])
        role = UserRole(claims["role"])
        site_id = claims.get("site_id")
        if site_id is not None:
            site_id = int(site_id)
        if claims.get("sub") != str(user_id):
            raise ValueError("JWT subject does not match user_id.")
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized

    # The database is authoritative so role or scope changes take effect without
    # waiting for an old token to expire. The signed token still carries the
    # complete identity/scope claims for clients and downstream services.
    if (
        user.organization_id != organization_id
        or user.role != role
        or user.site_id != site_id
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is stale; log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: UserRole | str) -> Callable[..., User]:
    """Create a dependency that permits listed roles and rejects all others."""
    allowed_roles = {UserRole(role) for role in roles}

    def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role is UserRole.TECHNICIAN and UserRole.TECHNICIAN in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Technician endpoints are not yet implemented.",
            )
        if user.role not in allowed_roles:
            names = ", ".join(sorted(role.value for role in allowed_roles))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' is not allowed. Required role(s): {names}.",
            )
        return user

    return check_role


def ensure_site_access(site_id: int, db: Session, user: User) -> Site:
    """Load a site and enforce organization/site-level access for management users."""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site was not found.")
    if user.role is UserRole.SITE_MANAGEMENT and user.site_id != site.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your assigned site.",
        )
    if user.role is UserRole.UPPER_MANAGEMENT and user.organization_id != site.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access sites within your organization.",
        )
    return site


def get_authorized_site(
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.UPPER_MANAGEMENT, UserRole.SITE_MANAGEMENT)),
) -> Site:
    """Dependency for endpoints that operate on a site management can access."""
    return ensure_site_access(site_id, db, user)


@dataclass(frozen=True)
class SiteScope:
    """Reusable SQL scope for a user's organization or assigned site."""

    organization_id: int
    site_id: int | None

    def for_site_column(self, site_column: Any) -> Any:
        """Return a SQL expression limiting a site_id column to this user's scope."""
        if self.site_id is not None:
            return site_column == self.site_id
        return site_column.in_(select(Site.id).where(Site.organization_id == self.organization_id))

    def for_asset_column(self, asset_id_column: Any) -> Any:
        """Return a SQL expression limiting an asset_id column to this user's sites."""
        return asset_id_column.in_(
            select(Asset.id).where(self.for_site_column(Asset.site_id))
        )


def get_site_scope(user: User = Depends(get_current_user)) -> SiteScope:
    """Provide org-wide scope for upper management and one-site scope for site staff."""
    if user.role is UserRole.TECHNICIAN:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Technician endpoints are not yet implemented.",
        )
    return SiteScope(organization_id=user.organization_id, site_id=user.site_id)


def apply_site_scope(statement: Select, model: Any, scope: SiteScope) -> Select:
    """Apply a SiteScope to a SELECT targeting a site-owned or asset-owned model."""
    if hasattr(model, "site_id"):
        return statement.where(scope.for_site_column(model.site_id))
    if hasattr(model, "asset_id"):
        return statement.where(scope.for_asset_column(model.asset_id))
    raise ValueError(f"{model!r} has no site_id or asset_id column to scope.")


__all__ = [
    "SiteScope",
    "apply_site_scope",
    "ensure_site_access",
    "get_authorized_site",
    "get_current_user",
    "get_site_scope",
    "require_role",
]
