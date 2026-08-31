from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

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
    MatchRequest,
    MatchResponse,
    MatchStreamErrorEvent,
    MatchStreamProgressEvent,
    MatchStreamResultEvent,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionEndRequest,
    SessionEndResponse,
)
from api.match_service import (
    AnalysisFailed,
    InsufficientMessages,
    MatchOutcome,
    MatchProgress,
    MatchingFailed,
    iter_match_pipeline,
    run_match,
    validate_match_input,
)
from api.session_end_service import SessionEndFailed, end_session
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


@app.post("/match", response_model=MatchResponse)
def match(payload: MatchRequest):
    try:
        result = run_match(payload.user_id, payload.session_id,
                           [message.model_dump() for message in payload.messages])
    except InvalidChatRequest as exc:
        return error_response(400, "INVALID_REQUEST", str(exc))
    except InsufficientMessages:
        return error_response(400, "INSUFFICIENT_MESSAGES", "分析には3件以上のユーザー発言が必要です。")
    except AnalysisFailed:
        return error_response(502, "ANALYSIS_FAILED", "人物分析に失敗しました。再試行してください。")
    except MatchingFailed:
        return error_response(502, "MATCHING_FAILED", "マッチングに失敗しました。再試行してください。")
    except Exception:
        return error_response(502, "MATCHING_FAILED", "マッチングに失敗しました。再試行してください。")
    return MatchResponse(**result.__dict__)


def _stream_error(code: str, message: str) -> str:
    return MatchStreamErrorEvent(
        error={"code": code, "message": message}
    ).model_dump_json() + "\n"


@app.post("/match/stream")
def match_stream(payload: MatchRequest):
    messages = [message.model_dump() for message in payload.messages]
    try:
        # Validate before StreamingResponse starts so known request errors retain
        # the same HTTP semantics as the backward-compatible JSON endpoint.
        validate_match_input(payload.user_id, payload.session_id, messages)
    except InvalidChatRequest as exc:
        return error_response(400, "INVALID_REQUEST", str(exc))
    except InsufficientMessages:
        return error_response(400, "INSUFFICIENT_MESSAGES", "分析には3件以上のユーザー発言が必要です。")

    def events():
        try:
            for event in iter_match_pipeline(
                payload.user_id,
                payload.session_id,
                messages,
                input_validated=True,
            ):
                if isinstance(event, MatchProgress):
                    yield MatchStreamProgressEvent(phase=event.phase).model_dump_json() + "\n"
                elif isinstance(event, MatchOutcome):
                    response = MatchResponse(**event.__dict__)
                    yield MatchStreamResultEvent(data=response).model_dump_json() + "\n"
        except AnalysisFailed:
            yield _stream_error("ANALYSIS_FAILED", "人物分析に失敗しました。再試行してください。")
        except MatchingFailed:
            yield _stream_error("MATCHING_FAILED", "マッチングに失敗しました。再試行してください。")
        except Exception:
            yield _stream_error("MATCHING_FAILED", "マッチングに失敗しました。再試行してください。")

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/sessions/{session_id}/end", response_model=SessionEndResponse)
def finish_session(session_id: str, payload: SessionEndRequest):
    try:
        end_session(session_id, payload.model_dump())
    except InvalidChatRequest as exc:
        return error_response(400, "INVALID_REQUEST", str(exc))
    except SessionEndFailed as exc:
        return error_response(500, "SESSION_END_FAILED", str(exc))
    except Exception:
        return error_response(500, "SESSION_END_FAILED", "セッションを終了できませんでした。")
    return SessionEndResponse()
