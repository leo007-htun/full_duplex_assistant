import io
import json
import os
from typing import Dict, List

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader

from .services.openai_client import client

# ------------------------
# Config
# ------------------------
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
app = FastAPI(title="Browser-First Voice Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_history: List[Dict[str, str]] = []

# ------------------------
# Prompts
# ------------------------
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(loader=FileSystemLoader(PROMPT_DIR))

def render_intent_prompt() -> str:
    return _env.get_template("intent_prompt.j2").render()

def render_system_prompt(session_id: str = "SESSION-001") -> str:
    return _env.get_template("system_prompt.j2").render(session_id=session_id)

class ChatMessage(BaseModel):
    message: str

# ------------------------
# Determine intent
# ------------------------
async def determine_intent_gpt(message: str) -> Dict[str, str]:
    prompt = render_intent_prompt()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.2,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"intent": "unknown", "response": "Could not parse GPT response."}

@app.post("/api/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message
    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")

    if intent == "smalltalk":
        system_content = render_system_prompt()
        history = [{"role": "system", "content": system_content}] + conversation_history
        history.append({"role": "user", "content": user_text})
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
            temperature=0.7,
        )
        result = chat_resp.choices[0].message.content.strip()
        conversation_history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result},
        ]
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
    elif intent == "weather":
        result = "The weather is sunny, 25°C."
    else:
        result = intent_data.get("response", "Sorry, I didn't understand that.")

    return {"intent": intent, "result": result}

# ------------------------
# STT
# ------------------------
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    resp = await client.audio.transcriptions.create(
        file=("input.webm", io.BytesIO(audio_bytes), "audio/webm"),
        model="gpt-4o-transcribe"
    )
    return {"text": resp.text}

# ------------------------
# TTS
# ------------------------
class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"

@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    resp = await client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=req.voice,
        input=req.text,
    )
    audio_bytes = await resp.read()
    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
