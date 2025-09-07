import asyncio
import base64
import io
import json
import os
from typing import Dict, List, Optional, AsyncIterator

import pyaudio
import websockets
from fastapi import FastAPI, UploadFile, File, Header, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

# ✅ Local services
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# Config & App
# =========================================================
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="COM Cloud • Full-Duplex Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All browser-facing routes live under /api (Traefik rule PathPrefix(`/api`))
api = APIRouter(prefix="/api")

# Server-side audio player for interruptible playback
tts_player = StreamingTTSPlayer()

# Conversation memory (process-local)
conversation_history: List[Dict[str, str]] = []

# =========================================================
# Prompt templates
# =========================================================
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(loader=FileSystemLoader(PROMPT_DIR))

def render_intent_prompt() -> str:
    return _env.get_template("intent_prompt.j2").render()

def render_system_prompt(session_id: str = "SESSION-001") -> str:
    return _env.get_template("system_prompt.j2").render(session_id=session_id)

# =========================================================
# Server-side TTS (PCM to device) — interruptible
# =========================================================
async def speak_tts(text: str, voice: str = "nova"):
    """
    Plays TTS as PCM on the server's audio device via StreamingTTSPlayer.
    This is separate from /api/tts which returns MP3 bytes for the browser.
    """
    # Stop any ongoing playback immediately
    tts_player.stop()
    # Stream PCM from OpenAI and feed to the player
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
        format="pcm",
    ) as response:
        await tts_player.play_pcm_stream(response)

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
    voice: str = "alloy"   # Browser-playback voice (MP3)

# =========================================================
# Health & basic endpoints
# =========================================================
@api.get("/healthz")
async def healthz():
    return {"ok": True}

@api.get("/weather")
async def get_weather():
    return {"forecast": "Sunny, 25°C"}

# =========================================================
# Intent → route (and speak on server)
# =========================================================
@api.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")
    reason = intent_data.get("reason", "")

    if intent == "weather":
        result = "The forecast is Sunny, 25°C."
    elif intent == "smalltalk":
        system_content = render_system_prompt(session_id="SESSION-001")
        convo = [{"role": "system", "content": system_content}] + conversation_history
        convo.append({"role": "user", "content": user_text})
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=convo,
            temperature=0.7,
        )
        result = chat_resp.choices[0].message.content.strip()
        conversation_history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result},
        ]
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
    else:
        result = "Hmm, I’m not sure what you mean."

    # Speak on the server device (interruptible)
    try:
        await speak_tts(result)
    except Exception:
        # Don't fail the API if local playback fails (e.g., no device in container)
        pass

    return {"intent": intent, "reason": reason, "result": result}

# =========================================================
# STT for browser uploads
# =========================================================
@api.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if file.content_type not in {"audio/webm", "audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a"}:
        return JSONResponse({"error": f"Unsupported content type: {file.content_type}"}, status_code=415)

    audio_bytes = await file.read()
    if not audio_bytes:
        return JSONResponse({"error": "Empty audio file."}, status_code=400)
    if len(audio_bytes) > 25 * 1024 * 1024:
        return JSONResponse({"error": "File too large (25MB)."}, status_code=413)

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

# =========================================================
# Browser-playback TTS (MP3), with instant stop support
# =========================================================
@api.post("/tts")
async def tts_mp3(req: TTSRequest):
    """
    Returns MP3 bytes the browser <audio> can play.
    If streaming is supported in the SDK, we stream; otherwise we fall back to a single MP3 blob.
    """
    # Try streaming first
    try:
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=req.voice,
            input=req.text,
            format="mp3",
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
        # SDK has no streaming path — fall through to non-streaming
        pass
    except Exception:
        # Any streaming failure — try non-streaming
        pass

    # Non-streaming fallback
    try:
        res = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=req.voice,
            input=req.text,
            format="mp3",
        )
        data: Optional[bytes] = None

        if hasattr(res, "content") and isinstance(res.content, (bytes, bytearray)):
            data = bytes(res.content)
        if data is None and hasattr(res, "read"):
            data = await res.read()
        if data is None and isinstance(res, (bytes, bytearray)):
            data = bytes(res)

        if not data:
            raise RuntimeError("Empty TTS response")

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
async def stop_tts():
    """
    Immediately stop any server-side playback (PCM via StreamingTTSPlayer).
    The browser should also abort its own MP3 fetch/playback in parallel.
    """
    try:
        tts_player.stop()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": f"stop failed: {e}"}, status_code=500)

# =========================================================
# Background Realtime VAD loop (server side, optional)
# =========================================================
RATE = 16000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

async def mic_stream_vad():
    """
    Optional server-side VAD using OpenAI Realtime Transcription API.
    Runs only if ENABLE_VOICE=1. Interrupts server TTS on speech start.
    """
    if not OPENAI_API_KEY:
        print("⚠️  OPENAI_API_KEY not set; skipping server VAD loop.")
        return

    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {OPENAI_API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("🎙️ Connected to OpenAI Realtime API (transcription)")

        # Configure session with server-side VAD
        session_payload = {
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
        }
        await ws.send(json.dumps(session_payload))
        print("✅ VAD transcription session ready")

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_base64 = base64.b64encode(data).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_base64}))
                await asyncio.sleep(0.01)

        async def receive_loop():
            streaming_buffer: Dict[str, str] = {}
            async for message in ws:
                event = json.loads(message)
                et = event.get("type")

                if et == "input_audio_buffer.speech_started":
                    # Hard-stop any ongoing server TTS as soon as we detect speech
                    print("⏹️ Speech started — stopping server TTS")
                    tts_player.stop()

                elif et == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    item_id = event.get("item_id")
                    if item_id not in streaming_buffer:
                        streaming_buffer[item_id] = ""
                    streaming_buffer[item_id] += delta
                    print("✍️ Partial:", streaming_buffer[item_id], end="\r")

                elif et == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    user_text = event.get("transcript", "")
                    print(f"\n✅ You said: {user_text}")

                    # Route via the same intent path (speaks result on server)
                    await determine_intent(ChatMessage(message=user_text))

                    if item_id in streaming_buffer:
                        del streaming_buffer[item_id]

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

# Mount /api router
app.include_router(api)

# Dev entrypoint
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.assistant.app:app", host="0.0.0.0", port=8000, reload=True)
