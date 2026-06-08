from typing import Literal

from pydantic import BaseModel, Field


class InitRequest(BaseModel):
    tour_id: str = Field(min_length=1, max_length=100)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    show_call_button: bool
    lead_score: int
    call_reason: str | None = None


CallStatus = Literal[
    "not_offered",
    "offered",
    "clicked",
    "started",
    "connected",
    "ended",
    "failed",
]


class CallStatusRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    status: CallStatus


class LLMResponse(BaseModel):
    status: Literal["ANSWER", "NO_DATA", "UNCLEAR"]
    reply: str = ""

