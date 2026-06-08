import time
import uuid

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import SESSIONS, TOURS_DB
from .schemas import CallStatusRequest, ChatRequest, ChatResponse, InitRequest
from .yandex_gpt import LLMResponseError, call_yandex_gpt


app = FastAPI(title="v19 Tour Consultant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def offer_call(session: dict, reason: str) -> None:
    session["call_status"] = "offered"
    session["escalation_reason"] = reason


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat/init", response_model=ChatResponse)
def init_chat(req: InitRequest) -> ChatResponse:
    tour_data = TOURS_DB.get(req.tour_id)
    if tour_data is None:
        raise HTTPException(status_code=404, detail="Tour not found")

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "tour_id": req.tour_id,
        "tour_data": tour_data,
        "lead_score": 0,
        "unclear_count": 0,
        "history": [],
        "call_status": "not_offered",
        "call_events": [],
        "escalation_reason": None,
    }
    return ChatResponse(
        session_id=session_id,
        reply="Здравствуйте! Чем помочь?",
        show_call_button=False,
        lead_score=0,
    )


@app.post("/api/chat/message", response_model=ChatResponse)
def process_message(req: ChatRequest) -> ChatResponse:
    session = SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")

    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be blank")

    user_msg = message.casefold()
    session["history"].append({"user": message})

    manager_keywords = ("менеджер", "оператор", "позвон", "связаться", "человек")
    if any(keyword in user_msg for keyword in manager_keywords):
        session["lead_score"] = min(session["lead_score"] + 3, 10)
        offer_call(session, "user_asked")
        reply = "Соединяю вас с менеджером. Звонок пройдет прямо в браузере."
        session["history"].append(
            {"bot": reply, "button_shown": True, "reason": "user_asked"}
        )
        return ChatResponse(
            session_id=req.session_id,
            reply=reply,
            show_call_button=True,
            lead_score=session["lead_score"],
            call_reason="user_asked",
        )

    commercial_keywords = (
        "цен",
        "дат",
        "отел",
        "бронь",
        "оплат",
        "мест",
        "налич",
        "номер",
        "вылет",
        "аэропорт",
        "ребен",
        "ребён",
        "дет",
        "куп",
        "оформ",
    )
    if any(keyword in user_msg for keyword in commercial_keywords):
        session["lead_score"] = min(session["lead_score"] + 1, 10)

    try:
        llm_response = call_yandex_gpt(session["tour_data"], message)
        status = llm_response.status
        reply_text = llm_response.reply.strip()
    except requests.RequestException:
        offer_call(session, "api_error")
        reply = "Произошла техническая заминка. Лучше соединю вас с менеджером."
        session["history"].append(
            {"bot": reply, "button_shown": True, "reason": "api_error"}
        )
        return ChatResponse(
            session_id=req.session_id,
            reply=reply,
            show_call_button=True,
            lead_score=session["lead_score"],
            call_reason="api_error",
        )
    except LLMResponseError:
        status = "UNCLEAR"
        reply_text = ""

    response = ChatResponse(
        session_id=req.session_id,
        reply="",
        show_call_button=False,
        lead_score=session["lead_score"],
    )

    if status == "UNCLEAR":
        session["unclear_count"] += 1
        unclear_count = session["unclear_count"]
        if unclear_count == 1:
            response.reply = "Можете переформулировать вопрос?"
        elif unclear_count == 2:
            response.reply = (
                "Не понимаю. Уточните, вас интересует цена, даты, отель "
                "или бронирование?"
            )
        elif unclear_count == 3:
            response.reply = (
                "Все ещё не пойму. Я могу соединить вас с менеджером. Соединить?"
            )
            response.show_call_button = True
            response.call_reason = "unclear_3"
            offer_call(session, response.call_reason)
        else:
            response.reply = "Лучше соединю вас с менеджером, он лучше поймёт."
            response.show_call_button = True
            response.call_reason = "unclear_4+"
            offer_call(session, response.call_reason)
    elif status == "NO_DATA":
        response.reply = (
            "Это лучше уточнить у менеджера. Хотите пообщаться голосом? "
            "Звонок будет прямо в браузере."
        )
        response.show_call_button = True
        response.call_reason = "no_data"
        offer_call(session, response.call_reason)
    else:
        session["unclear_count"] = 0
        if not reply_text:
            response.reply = "Лучше уточнить это у менеджера."
            response.show_call_button = True
            response.call_reason = "empty_llm_reply"
            offer_call(session, response.call_reason)
        elif session["lead_score"] >= 2:
            response.reply = (
                f"{reply_text}\n\nПохоже, вам интересен этот тур. "
                "Соединить вас с менеджером прямо сейчас?"
            )
            response.show_call_button = True
            response.call_reason = "high_lead_score"
            offer_call(session, response.call_reason)
        else:
            response.reply = reply_text

    session["history"].append(
        {
            "bot": response.reply,
            "button_shown": response.show_call_button,
            "reason": response.call_reason,
        }
    )
    return response


@app.post("/api/chat/call_status")
def update_call_status(req: CallStatusRequest) -> dict[str, str]:
    session = SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session["call_status"] = req.status
    session["call_events"].append({"status": req.status, "ts": time.time()})
    return {"status": "ok"}


@app.get("/api/demo-web-call-config")
def get_demo_call_config() -> dict[str, str]:
    settings = get_settings()
    if not settings.exolve_is_configured():
        raise HTTPException(status_code=503, detail="Exolve is not configured")

    return {
        "LOGIN": settings.EXOLVE_SIP_LOGIN,
        "PASSWORD": settings.EXOLVE_SIP_PASSWORD,
        "MANAGER_NUMBER": settings.EXOLVE_MANAGER_NUMBER,
    }

