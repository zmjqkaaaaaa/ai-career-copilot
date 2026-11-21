from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    username: str = Field(min_length=2, max_length=64)

    @field_validator("username", mode="before")
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not (any(char.isalpha() for char in value) and any(not char.isalpha() and not char.isspace() for char in value)):
            raise ValueError("密码须包含字母以及数字或符号")
        return value

class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
