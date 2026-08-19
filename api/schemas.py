from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator


class SessionCreateRequest(BaseModel):
    user_id: str | None = Field(...)
    log_consent: StrictBool


class MessageResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatMessage(BaseModel):
    role: Literal["assistant", "user"]
    content: str

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)


class ChatResponse(BaseModel):
    message: MessageResponse


class SessionCreateResponse(BaseModel):
    user_id: str
    session_id: str
    message: MessageResponse


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
