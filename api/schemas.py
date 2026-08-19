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


class MatchRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)


class AnalysisResponse(BaseModel):
    personality: str
    values: str
    hidden_needs: str
    communication_style: str
    ideal_partner_type: str
    summary: str


class CandidateResponse(BaseModel):
    id: str
    name: str
    age: int
    personality: str
    values: str
    hobbies: str
    communication_style: str
    relationship_style: str
    description: str


class MatchResultResponse(BaseModel):
    matched_candidate: CandidateResponse
    match_score: int
    match_label: str
    match_reason: str
    possible_concern: str
    recommended_first_message: str


class TopCandidateResponse(BaseModel):
    candidate: CandidateResponse
    similarity: float


class AfterMatchSupportResponse(BaseModel):
    first_message_today: str
    question_in_3days: str
    avoid_phrase: str
    slow_reply_action: str


class MatchResponse(BaseModel):
    analysis: AnalysisResponse
    match: MatchResultResponse
    top_candidates: list[TopCandidateResponse]
    after_match_support: AfterMatchSupportResponse | None
    profile_updated: bool


class SessionEndRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    messages: list[ChatMessage]
    analysis: AnalysisResponse | None = None
    match: MatchResultResponse | None = None
    top_candidates: list[TopCandidateResponse] = Field(default_factory=list)
    after_match_support: AfterMatchSupportResponse | None = None


class SessionEndResponse(BaseModel):
    status: Literal["completed"] = "completed"


class SessionCreateResponse(BaseModel):
    user_id: str
    session_id: str
    message: MessageResponse


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
