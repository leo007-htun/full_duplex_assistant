import io
import json
import os
from typing import Dict, List, Optional, AsyncIterator

from fastapi import FastAPI, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
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
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# per-session memory to avoid cross-talk
sessions: Dict[str, List[Dict[str, str]]] = {}

def get_session_id(x_session_id: Optional[str] = Header(default=None)) -> str:
    return x_session_id or "ANON"

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
    # Ask the SDK for strict JSON; if not supported by your model, we still try/except
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except Exception:
        return {"intent": "unknown", "response": f"Could not parse GPT response: {content[:200]}"}

@app.post("/api/determine_intent")
async def determine_intent(msg: ChatMessage, x_session_id: Optional[str] = Header(default=None)):
    session_id = get_session_id(x_session_id)
    history = sessions.setdefault(session_id, [])

    user_text = msg.message
    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")

    if intent == "smalltalk":
        system_content = render_system_prompt(session_id=session_id)
        convo = [{"role": "system", "content": system_content}] + history
        convo.append({"role": "user", "content": user_text})
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=convo,
            temperature=0.7,
        )
        result = chat_resp.choices[0].message.content.strip()
        history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result},
        ]
        if len(history) > 40:
            sessions[session_id] = history[-40:]
    elif intent == "weather":
        result = "The weather is sunny, 25°C."
    else:
        result = intent_data.get("response", "Sorry, I didn't understand that.")

    return {"intent": intent, "result": result}

# ------------------------
# Health
# ------------------------
@app.get("/api/healthz")
async def healthz():
    return {"ok": True}

# ------------------------
# STT
# ------------------------
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Basic validation to avoid surprising 500s
    if file.content_type not in {"audio/webm", "audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a"}:
        return JSONResponse({"error": f"Unsupported content type: {file.content_type}"}, status_code=415)

    audio_bytes = await file.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        return JSONResponse({"error": "File too large (25MB limit)."}, status_code=413)

    # Use original filename/mimetype if possible
    filename = file.filename or "input.webm"
    mimetype = file.content_type or "application/octet-stream"

    try:
        resp = await client.audio.transcriptions.create(
            file=(filename, io.BytesIO(audio_bytes), mimetype),
            model="gpt-4o-transcribe",
        )
        return {"text": resp.text}
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)

# ------------------------
# TTS
# ------------------------
class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"  # keep default

@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """
    Robust TTS that works across OpenAI SDK minor changes.
    Always returns 'audio/mpeg' so the browser can play it directly.
    """
    # Prefer true streaming if available
    try:
        # Newer SDKs: stream bytes from server
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=req.voice,
            input=req.text,
        ) as resp:
            async def gen() -> AsyncIterator[bytes]:
                async for chunk in resp.iter_bytes():
                    if chunk:
                        yield chunk
            return StreamingResponse(
                gen(),
                media_type="audio/mpeg",
                headers={
                    "Cache-Control": "no-store",
                    "Content-Disposition": 'inline; filename="speech.mp3"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
    except AttributeError:
        # Older SDK fallback: create returns a buffer-like object or raw bytes
        pass
    except Exception as e:
        # If the streaming path failed for other reasons, try non-streaming fallback
        fallback_error = str(e)

    try:
        res = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=req.voice,
            input=req.text,
        )
        # Handle various possible return shapes
        data: Optional[bytes] = None

        # Some SDKs return a Response with .content
        if hasattr(res, "content") and isinstance(res.content, (bytes, bytearray)):
            data = bytes(res.content)

        # Some return a context manager-like object with .read()
        if data is None and hasattr(res, "read"):
            data = await res.read()

        # Or raw bytes
        if data is None and isinstance(res, (bytes, bytearray)):
            data = bytes(res)

        if not data:
            raise RuntimeError("Empty TTS response from SDK.")

        return Response(
            content=data,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="speech.mp3"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as e:
        detail = getattr(e, "message", str(e))
        return JSONResponse({"error": f"TTS failed: {detail}"}, status_code=500)
