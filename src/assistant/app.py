# server.py
import os
import io
import json
import base64
import asyncio
from typing import Optional, Dict, List

import httpx
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

# OpenAI (async)
try:
    from openai import AsyncOpenAI
except Exception:
    # Backward compatibility shim if older SDK is installed
    from openai import AsyncOpenAI  # type: ignore

load_dotenv()  # loads .env from cwd or parents

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in your environment or .env")

# CORS: allow your Live Server origins (adjust as needed)
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
extra_origins = os.getenv("ALLOWED_ORIGINS", "")
if extra_origins:
    ALLOWED_ORIGINS += [o.strip() for o in extra_origins.split(",") if o.strip()]

app = FastAPI(title="Full-Duplex Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

# OpenAI async client
oa = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────
def _parse_client_secret(payload: dict) -> Optional[str]:
    """
    OpenAI may return:
      { "client_secret": { "value": "ek_..." } }
      or
      { "client_secret": "ek_..." }
    """
    cs = payload.get("client_secret")
    if isinstance(cs, dict):
        return cs.get("value")
    if isinstance(cs, str):
        return cs
    return None


async def _create_realtime_ephemeral() -> str:
    """
    Works with current Realtime API:
      POST /v1/realtime/sessions  (preferred)
    Falls back to legacy /v1/realtime/transcription_sessions if present.
    """
    base = "https://api.openai.com"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        # Try the general sessions endpoint first (no params required)
        r = await client.post(f"{base}/v1/realtime/sessions", headers=headers, json={})
        if r.status_code == 200:
            secret = _parse_client_secret(r.json())
            if not secret:
                raise HTTPException(status_code=500, detail="No client_secret in sessions response")
            return secret

        # If your account has a transcription-specific endpoint enabled, try it
        r2 = await client.post(f"{base}/v1/realtime/transcription_sessions", headers=headers, json={})
        if r2.status_code == 200:
            secret = _parse_client_secret(r2.json())
            if not secret:
                raise HTTPException(status_code=500, detail="No client_secret in transcription_sessions response")
            return secret

        # Bubble up error
        detail = r.text if r.content else r.reason_phrase
        raise HTTPException(status_code=r.status_code or 500, detail=f"OpenAI error: {detail}")


# ─────────────────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────────────────

@app.get("/rt-token")
async def rt_token():
    """
    Returns ephemeral client secret for the browser Realtime WS:
      GET /rt-token  -> { "client_secret": { "value": "ek_..." } }
    Your frontend then connects to:
      wss://api.openai.com/v1/realtime?intent=transcription
    with `Authorization: Bearer ek_...` and `OpenAI-Beta: realtime=v1`
    """
    secret = await _create_realtime_ephemeral()
    # Return in the "nested" shape many examples expect
    return {"client_secret": {"value": secret}}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ─────────────  Simple intent + chat  ─────────────
conversation_history: List[Dict[str, str]] = []

INTENT_SYSTEM = (
    "You are a tiny intent classifier. "
    "Return JSON with fields intent (weather|smalltalk|web_search|unknown) and reason."
)

def _system_prompt(session_id: str = "SESSION-001") -> str:
    return f"You are NEXUS assistant (session {session_id}). Be concise, helpful, sci-fi tone optional."

class ChatMessage(BaseModel):
    message: str

try:
    from pydantic import BaseModel  # ensure available
except Exception:
    from pydantic.main import BaseModel  # fallback


@api.post("/determine_intent")
async def determine_intent(msg: ChatMessage, request: Request):
    global conversation_history
    user_text = (msg.message or "").strip()
    if not user_text:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Abort early if client disconnected
    if await request.is_disconnected():
        return JSONResponse({"error": "Request aborted"}, status_code=499)

    # 1) classify
    intent_resp = await oa.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": INTENT_SYSTEM},
            {"role": "user", "content": user_text},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        intent_data = json.loads(intent_resp.choices[0].message.content or "{}")
    except Exception:
        intent_data = {"intent": "unknown", "reason": "parse_error"}

    intent = intent_data.get("intent", "unknown")
    reason = intent_data.get("reason", "")

    if await request.is_disconnected():
        return JSONResponse({"error": "Request aborted"}, status_code=499)

    # 2) route
    if intent == "weather":
        result = "The forecast is Sunny, 25°C."
    elif intent == "smalltalk":
        sys = _system_prompt("SESSION-001")
        convo = [{"role": "system", "content": sys}] + conversation_history
        convo.append({"role": "user", "content": user_text})
        chat = await oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=convo,
            temperature=0.7,
        )
        result = (chat.choices[0].message.content or "").strip()
        conversation_history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result},
        ]
        conversation_history[:] = conversation_history[-40:]
    elif intent == "web_search":
        result = "Here's what I found on the web (stub)."
    else:
        result = "Hmm, I'm not sure what you mean."

    # (Optional) fire-and-forget local TTS playback on the server machine.
    # Commented out by default to avoid audio device issues.
    # asyncio.create_task(_speak_locally(result))

    return {"intent": intent, "reason": reason, "result": result}


# ─────────────  Upload STT  ─────────────
@api.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    raw_ct = (file.content_type or "application/octet-stream").lower()
    base_ct = raw_ct.split(";")[0].strip()
    allowed = {
        "audio/webm", "audio/ogg", "audio/mpeg",
        "audio/wav", "audio/mp4", "audio/x-m4a",
        "application/octet-stream",
    }
    if base_ct not in allowed:
        return JSONResponse({"error": f"Unsupported content type: {raw_ct}"}, status_code=415)

    audio_bytes = await file.read()
    if not audio_bytes:
        return JSONResponse({"error": "Empty audio file."}, status_code=400)
    if len(audio_bytes) > 25 * 1024 * 1024:
        return JSONResponse({"error": "File too large (25MB)."}, status_code=413)

    name = (file.filename or "").strip() or "input"
    # try to leave extension sensible
    ext_map = {
        "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
        "audio/wav": ".wav", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
        "application/octet-stream": "",
    }
    if "." not in name and base_ct in ext_map:
        name += ext_map[base_ct]
    mimetype = base_ct if base_ct in ext_map else "application/octet-stream"

    try:
        resp = await oa.audio.transcriptions.create(
            file=(name, io.BytesIO(audio_bytes), mimetype),
            model="gpt-4o-transcribe",
        )
        # newer SDKs: resp.text; older may be resp["text"]
        text = getattr(resp, "text", None) or resp.get("text")
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)


# ─────────────  Browser TTS (MP3)  ─────────────
class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"

@api.post("/tts")
async def tts_mp3(req: TTSRequest):
    txt = (req.text or "").strip()
    if not txt:
        return JSONResponse({"error": "Empty text"}, status_code=400)
    voice = (req.voice or "alloy").strip() or "alloy"
    try:
        # Most recent SDKs:
        audio = await oa.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=txt,
            response_format="mp3",  # some SDKs accept "format"
        )
        # Normalize to bytes
        data = None
        if hasattr(audio, "content") and isinstance(audio.content, (bytes, bytearray)):
            data = bytes(audio.content)
        elif hasattr(audio, "read"):
            data = await audio.read()
        elif isinstance(audio, (bytes, bytearray)):
            data = bytes(audio)
        if not data:
            raise RuntimeError("No audio returned")
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
        return JSONResponse({"error": f"TTS failed: {e}"}, status_code=500)

@api.post("/tts/stop")
async def tts_stop():
    # no-op placeholder; you can wire this to an interruptible player if needed
    return {"ok": True}


# Mount API router
app.include_router(api)


# Root
@app.get("/")
def root():
    return {"status": "ok", "message": "Assistant is running!"}


# ─────────────────────────────────────────────────────────
# Optional: server-side mic → Realtime VAD (desktop dev only)
# Disabled by default; set ENABLE_VOICE=1 to try it.
# ─────────────────────────────────────────────────────────
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"

async def _server_vad_loop():
    try:
        import pyaudio  # only if you really want server mic
    except Exception:
        print("⚠️  pyaudio not installed; skipping server mic loop.")
        return

    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {OPENAI_API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]
    RATE = 16000
    CHUNK = 1024

    async with websockets.connect(uri, extra_headers=headers) as ws:
        # minimal session config
        await ws.send(json.dumps({
            "type": "transcription_session.update",
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "gpt-4o-mini-transcribe",
                "language": "en"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            }
        }))

        import pyaudio
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(data).decode("utf-8")
                }))
                await asyncio.sleep(0.01)

        async def recv_loop():
            partial: Dict[str, str] = {}
            async for msg in ws:
                ev = json.loads(msg)
                et = ev.get("type")
                if et == "conversation.item.input_audio_transcription.delta":
                    item_id = ev.get("item_id")
                    delta = ev.get("delta", "")
                    partial[item_id] = partial.get(item_id, "") + delta
                    print("…", partial[item_id], end="\r")
                elif et == "conversation.item.input_audio_transcription.completed":
                    item_id = ev.get("item_id")
                    text = ev.get("transcript", "")
                    print(f"\nYou said: {text}")
                    partial.pop(item_id, None)

        await asyncio.gather(send_audio(), recv_loop())


@app.on_event("startup")
async def on_start():
    if ENABLE_VOICE:
        asyncio.create_task(_server_vad_loop())
        print("✅ Server VAD loop started (ENABLE_VOICE=1)")
    else:
        print("ℹ️ Server VAD disabled (ENABLE_VOICE=0)")


# Dev entry
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
