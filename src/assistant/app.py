import asyncio
import base64
import io
import json
import os
from typing import Dict, List, Optional, AsyncIterator

# 3rd-party
import websockets
from fastapi import FastAPI, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

# ✅ Local services (your thin OpenAI client + PCM player)
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# Config
# =========================================================
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Full-Duplex Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All browser calls come under /api
api = APIRouter(prefix="/api")

# Server-side audio player (interruptible)
tts_player = StreamingTTSPlayer()

# Minimal in-memory convo history (kept short)
conversation_history: List[Dict[str, str]] = []

# Templates
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(loader=FileSystemLoader(PROMPT_DIR))

def render_intent_prompt() -> str:
    return _env.get_template("intent_prompt.j2").render()

def render_system_prompt(session_id: str = "SESSION-001") -> str:
    return _env.get_template("system_prompt.j2").render(session_id=session_id)

# =========================================================
# Server-side TTS (PCM to device) — interruptible
# =========================================================
async def speak_tts_locally(text: str, voice: str = "nova"):
    """
    Plays TTS through a local audio device (if present).
    Safe to best-effort: if device missing (Docker), we swallow errors.
    """
    try:
        tts_player.stop()
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            format="pcm",  # PCM stream for local device
        ) as response:
            await tts_player.play_pcm_stream(response)
    except Exception:
        # No device in container or SDK mismatch: ignore
        pass

# =========================================================
# Intent classification
# =========================================================
async def determine_intent_gpt(message: str) -> Dict[str, str]:
    system_prompt = render_intent_prompt()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"intent": "unknown", "reason": "Could not parse GPT response."}

# =========================================================
# Models
# =========================================================
class ChatMessage(BaseModel):
    message: str

class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"  # browser playback voice (mp3)

# =========================================================
# Health + tiny tools
# =========================================================
@api.get("/healthz")
async def healthz():
    return {"ok": True}

@api.get("/weather")
async def get_weather():
    # demo tool
    return {"forecast": "Sunny, 25°C"}

# =========================================================
# Intent → route → (optionally speak on server) → return text
# =========================================================
@api.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    # 1) classify
    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")
    reason = intent_data.get("reason", "")

    # 2) route
    if intent == "weather":
        data = await get_weather()
        result = f"The forecast is {data['forecast']}."
    elif intent == "smalltalk":
        sys_prompt = render_system_prompt("SESSION-001")
        convo = [{"role": "system", "content": sys_prompt}] + conversation_history
        convo.append({"role": "user", "content": user_text})
        chat = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=convo,
            temperature=0.7,
        )
        result = (chat.choices[0].message.content or "").strip()
        conversation_history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result},
        ]
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
    elif intent == "web_search":
        # stub; you can call your scraper + summarizer here
        result = "Here’s what I found on the web (stub)."
    else:
        result = "Hmm, I’m not sure what you mean."

    # 3) optionally speak on the server device (if you run on a desktop)
    await speak_tts_locally(result)

    # 4) return text for the browser to TTS
    return {"intent": intent, "reason": reason, "result": result}

# =========================================================
# STT for browser uploads (handles codecs=…)
# =========================================================
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
    ext_map = {
        "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
        "audio/wav": ".wav", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
        "application/octet-stream": "",
    }
    if "." not in name and base_ct in ext_map:
        name += ext_map[base_ct]
    mimetype = base_ct if base_ct in ext_map else "application/octet-stream"

    try:
        resp = await client.audio.transcriptions.create(
            file=(name, io.BytesIO(audio_bytes), mimetype),
            model="gpt-4o-transcribe",
        )
        return {"text": resp.text}
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)

# =========================================================
# Browser-playback TTS (MP3), with instant stop support
# =========================================================
@api.post("/tts")
async def tts_mp3(req: TTSRequest):
    """
    Returns MP3 bytes the browser <audio> can play.
    Uses a tolerant param shim for SDK variants.
    """
    text = (req.text or "").strip()
    voice = (req.voice or "alloy").strip() or "alloy"
    if not text:
        return JSONResponse({"error": "Empty text"}, status_code=400)

    async def create_tts(model: str, voice: str, text: str) -> Optional[bytes]:
        attempts = (
            {"format": "mp3"},
            {"response_format": "mp3"},
            {"audio_format": "mp3"},
            {},
        )
        last = None
        for extra in attempts:
            try:
                res = await client.audio.speech.create(
                    model=model, voice=voice, input=text, **extra
                )
                data = None
                if hasattr(res, "content") and isinstance(res.content, (bytes, bytearray)):
                    data = bytes(res.content)
                elif hasattr(res, "read"):
                    data = await res.read()
                elif isinstance(res, (bytes, bytearray)):
                    data = bytes(res)
                if data:
                    return data
            except TypeError as e:
                last = e
                continue
            except Exception as e:
                last = e
                break
        if last:
            raise last
        return None

    try:
        data = await create_tts("gpt-4o-mini-tts", voice, text)
        if not data:
            raise RuntimeError("TTS returned no audio")
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
        print(f"[/api/tts] error: {type(e).__name__}: {e}")
        return JSONResponse({"error": f"TTS failed: {e}"}, status_code=500)

@api.post("/tts/stop")
async def stop_tts():
    try:
        tts_player.stop()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": f"stop failed: {e}"}, status_code=500)

# =========================================================
# Optional: server-side VAD loop (desktop/dev only)
# =========================================================
RATE = 16000
CHUNK = 1024
CHANNELS = 1

async def mic_stream_vad():
    if not OPENAI_API_KEY:
        print("⚠️  OPENAI_API_KEY not set; skipping server VAD loop.")
        return

    try:
        import pyaudio  # only import when enabled
    except Exception:
        print("⚠️  pyaudio not available; skipping server VAD loop.")
        return

    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {OPENAI_API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("🎙️ Connected to OpenAI Realtime (transcription)")

        await ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe",
                    "language": "en",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "input_audio_noise_reduction": {"type": "near_field"},
            },
        }))
        print("✅ VAD session ready")

        import pyaudio
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64}))
                await asyncio.sleep(0.01)

        async def receive_loop():
            partial: Dict[str, str] = {}
            async for message in ws:
                event = json.loads(message)
                et = event.get("type")

                if et == "input_audio_buffer.speech_started":
                    # BARGe-IN: kill any local playback instantly
                    tts_player.stop()

                elif et == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    item_id = event.get("item_id")
                    partial[item_id] = partial.get(item_id, "") + delta
                    print("✍️", partial[item_id], end="\r")

                elif et == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    text = event.get("transcript", "")
                    print(f"\n✅ You said: {text}")

                    # Route through the same endpoint logic
                    await determine_intent(ChatMessage(message=text))
                    partial.pop(item_id, None)

        await asyncio.gather(send_audio(), receive_loop())

# =========================================================
# Root + startup
# =========================================================
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant is running!"}

@app.on_event("startup")
async def startup_event():
    if ENABLE_VOICE:
        asyncio.create_task(mic_stream_vad())
        print("✅ Server VAD loop started (ENABLE_VOICE=1)")
    else:
        print("ℹ️ Server VAD disabled (ENABLE_VOICE=0)")

# Mount /api
app.include_router(api)

# Optionally mirror a few routes at root (handy for debugging/health)
@app.get("/healthz")
async def _health_alias():
    return await healthz()

# Dev entry
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.assistant.app:app", host="0.0.0.0", port=8000, reload=True)
