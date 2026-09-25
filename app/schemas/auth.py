import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import UserRole

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LoginRequest(BaseModel):
    """Credentials submitted to the JSON login endpoint."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email

    @field_validator("password")
    @classmethod
    def limit_bcrypt_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes for bcrypt.")
        return value


class RegisterRequest(BaseModel):
    """Hackathon registration fields, including the desired test-user scope."""

    email: str
    password: str = Field(min_length=8, max_length=72)
    role: UserRole
    organization_id: int = Field(gt=0)
    site_id: int | None = Field(default=None, gt=0)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email

    @field_validator("password")
    @classmethod
    def limit_bcrypt_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes for bcrypt.")
        return value

    @model_validator(mode="after")
    def validate_role_scope(self) -> "RegisterRequest":
        if self.role is UserRole.UPPER_MANAGEMENT and self.site_id is not None:
            raise ValueError("upper_management users must not have a site_id.")
        if self.role is not UserRole.UPPER_MANAGEMENT and self.site_id is None:
            raise ValueError(f"{self.role.value} users must have a site_id.")
        return self


class UserResponse(BaseModel):
    """Safe public representation of a registered or authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: UserRole
    organization_id: int
    site_id: int | None


class TokenResponse(BaseModel):
    """Bearer access token returned by login and registration."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
