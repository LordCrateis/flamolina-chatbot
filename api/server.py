import os
from typing import Any
import traceback
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

from api.router import get_flamolina_response
from prompts.persona import FLAMOLINA_SYSTEM_PROMPT

load_dotenv()

configured_origins = os.getenv('FLAMOLINA_ALLOWED_ORIGINS', '')
allowed_origins = [origin.strip() for origin in configured_origins.split(',') if origin.strip()]
allowed_origins.extend(['http://localhost:5173', 'http://127.0.0.1:5173'])

app = FastAPI(title="Flamolina API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(allowed_origins )),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1 ):\d+",
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)



class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    history: list[dict[str, Any]]


def normalize_history(history: list[ChatMessage]) -> list[dict[str, str]]:
    clean_history = [
        {"role": item.role, "content": item.content}
        for item in history
        if item.role in {"user", "assistant"} and item.content.strip()
    ]
    return [{"role": "system", "content": FLAMOLINA_SYSTEM_PROMPT}, *clean_history]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "flamolina"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        answer, updated_history = get_flamolina_response(
            payload.message.strip(),
            normalize_history(payload.history),
        )
    except Exception as error:
        print("FLAMOLINA ERROR:", repr(error))
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Flamolina could not complete that request."
        ) from error

    return ChatResponse(answer=answer or "I have nothing useful to add to that.", history=updated_history)
