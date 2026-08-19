from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class SessionCreateRequest(BaseModel):
    user_id: str | None = Field(...)
    log_consent: StrictBool


class MessageResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class SessionCreateResponse(BaseModel):
    user_id: str
    session_id: str
    message: MessageResponse


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
