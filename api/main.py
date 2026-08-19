from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.chat_service import (
    AIContextTooLong,
    AIResponseFailed,
    AIResponseTruncated,
    InvalidChatRequest,
    generate_chat_reply,
)
from api.schemas import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from api.session_service import InvalidSessionRequest, SessionStartError, start_session

app = FastAPI(
    title="Fairies API",
    version="0.2.2",
)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(400, "INVALID_REQUEST", "リクエストの形式が不正です。")


@app.get("/")
def root():
    return {
        "app": "Fairies",
        "version": "0.2.2",
        "status": "ok",
    }


@app.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=201,
)
def create_session(payload: SessionCreateRequest):
    try:
        started = start_session(payload.user_id, payload.log_consent)
    except InvalidSessionRequest as exc:
        return error_response(400, "INVALID_REQUEST", str(exc))
    except SessionStartError as exc:
        return error_response(500, "SESSION_START_FAILED", str(exc))
    except Exception:
        return error_response(500, "SESSION_START_FAILED", "セッションを開始できませんでした。")

    return SessionCreateResponse(
        user_id=started.user_id,
        session_id=started.session_id,
        message=MessageResponse(content=started.greeting),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        reply = generate_chat_reply(
            payload.user_id,
            payload.session_id,
            [message.model_dump() for message in payload.messages],
        )
    except InvalidChatRequest as exc:
        return error_response(400, "INVALID_REQUEST", str(exc))
    except AIResponseTruncated as exc:
        return error_response(502, "AI_RESPONSE_TRUNCATED", str(exc))
    except AIContextTooLong as exc:
        return error_response(413, "AI_CONTEXT_TOO_LONG", str(exc))
    except AIResponseFailed as exc:
        return error_response(502, "AI_RESPONSE_FAILED", str(exc))
    except Exception:
        return error_response(502, "AI_RESPONSE_FAILED", "Fairyから応答を取得できませんでした。")

    return ChatResponse(message=MessageResponse(content=reply.content))
