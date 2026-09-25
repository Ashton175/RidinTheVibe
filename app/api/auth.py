from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Organization, Site, User
from app.models.enums import UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    expires_in = settings.access_token_expire_minutes * 60
    token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        organization_id=user.organization_id,
        site_id=user.site_id,
        expires_delta=timedelta(seconds=expires_in),
    )
    return TokenResponse(access_token=token, expires_in=expires_in, user=user)


@router.post("/login", response_model=TokenResponse, summary="Log in with email and password")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify credentials and return a scoped JWT access token."""
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a hackathon test user",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a test user without email verification and return an access token."""
    if db.scalar(select(Organization.id).where(Organization.id == payload.organization_id)) is None:
        raise HTTPException(status_code=404, detail="Organization was not found.")

    if payload.role is UserRole.UPPER_MANAGEMENT:
        if payload.site_id is not None:
            raise HTTPException(status_code=422, detail="upper_management users must not have a site_id.")
    else:
        site = db.get(Site, payload.site_id)
        if site is None or site.organization_id != payload.organization_id:
            raise HTTPException(
                status_code=422,
                detail="site_id must identify a site in the selected organization.",
            )

    if db.scalar(select(User.id).where(func.lower(User.email) == payload.email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        organization_id=payload.organization_id,
        site_id=payload.site_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None

    db.refresh(user)
    return _token_response(user)


@router.get("/me", response_model=UserResponse, summary="Return the current authenticated user")
def current_user(user: User = Depends(get_current_user)) -> User:
    """Return the signed-in user's public identity and scope."""
    return user
