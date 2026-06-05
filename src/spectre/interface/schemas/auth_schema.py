"""Auth schemas — register, login, TOTP, token models."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=255)


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    message: str = "Registration successful."


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    display_name: str | None = None
    totp_required: bool = False


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
