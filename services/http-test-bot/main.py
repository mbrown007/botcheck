from __future__ import annotations

import json
import logging
import os
from enum import StrEnum
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("http-test-bot")

app = FastAPI(title="BotCheck HTTP Test Bot")

class BotMode(StrEnum):
    ECHO = "echo"
    SCRIPTED = "scripted"
    AI = "ai"

# Configuration from environment
_raw_mode = os.getenv("HTTP_BOT_MODE", "scripted").lower()
try:
    MODE = BotMode(_raw_mode)
except ValueError:
    raise ValueError(
        f"Invalid HTTP_BOT_MODE={_raw_mode!r}. Valid values: {[m.value for m in BotMode]}"
    ) from None
RESPONSE_MAP_JSON = os.getenv("HTTP_BOT_RESPONSE_MAP_JSON", '{"billing": "You reached billing.", "support": "Technical support here."}')
DEFAULT_RESPONSE = os.getenv("HTTP_BOT_DEFAULT_RESPONSE", "I am a test bot. How can I help?")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Parsed response map
try:
    RESPONSE_MAP = json.loads(RESPONSE_MAP_JSON)
except Exception as e:
    logger.error(f"Failed to parse HTTP_BOT_RESPONSE_MAP_JSON: {e}")
    RESPONSE_MAP = {}

class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None

class ChatResponse(BaseModel):
    response: str

async def _get_ai_response(message: str, history: list[dict[str, Any]]) -> str:
    if not OPENAI_API_KEY:
        return "OpenAI API key missing. Please configure it."
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        messages = [{"role": "system", "content": "You are a helpful test assistant."}]
        for h in history[-5:]: # Last 5 turns for context
            role = "assistant" if h.get("speaker") == "bot" else "user"
            messages.append({"role": role, "content": h.get("text", "")})
        
        messages.append({"role": "user", "content": message})
        
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=150
        )
        return completion.choices[0].message.content or DEFAULT_RESPONSE
    except Exception as e:
        logger.error(f"AI response failed: {e}")
        return "AI service unavailable."

@app.get("/health")
async def health():
    return {"status": "ok", "mode": MODE}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info(f"Received message in {MODE} mode: {request.message}")
    
    if MODE == BotMode.ECHO:
        return ChatResponse(response=f"You said: {request.message}")
    
    if MODE == BotMode.SCRIPTED:
        lowered = request.message.lower()
        for keyword, reply in RESPONSE_MAP.items():
            if keyword.lower() in lowered:
                return ChatResponse(response=reply)
        return ChatResponse(response=DEFAULT_RESPONSE)
    
    if MODE == BotMode.AI:
        ai_reply = await _get_ai_response(request.message, request.history)
        return ChatResponse(response=ai_reply)

    return ChatResponse(response=DEFAULT_RESPONSE)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
