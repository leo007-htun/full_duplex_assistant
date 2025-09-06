import asyncio
import base64
import json
import os
from typing import Optional, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# Config
# =========================================================
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")

app = FastAPI(title="Voice Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tts_player = StreamingTTSPlayer()

# =========================================================
# Conversation
# =========================================================
conversation_history: List[Dict[str, str]] = []

# =========================================================
# HTTP Routes
# =========================================================
class ChatMessage(BaseModel):
    message: str

@app.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":user_text}],
        temperature=0.7,
        stream=False
    )
    reply = resp.choices[0].message.content.strip()
    conversation_history.append({"role":"user","content":user_text})
    conversation_history.append({"role":"assistant","content":reply})
    if len(conversation_history) > 40:
        conversation_history = conversation_history[-40:]
    
    if ENABLE_VOICE:
        # optional server TTS
        await speak_tts(reply)
    
    return {"result": reply}

async def speak_tts(text: str):
    if not ENABLE_VOICE or not text:
        return
    try:
        tts_player.stop()
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="nova",
            input=text,
            response_format="pcm"
        ) as resp:
            await tts_player.play_pcm_stream(resp)
    except Exception:
        pass

# =========================================================
# WebSocket for real-time STT+TTS
# =========================================================
class TTSSession:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.cancel_event = asyncio.Event()

    def cancel(self):
        self.cancel_event.set()
        tts_player.stop()
        if self.task and not self.task.done():
            self.task.cancel()

    def reset(self):
        self.cancel_event = asyncio.Event()
        self.task = None

async def stream_tts_to_browser(ws: WebSocket, text: str, tts: TTSSession):
    """Stream TTS PCM to browser; interruptable."""
    await ws.send_text(json.dumps({"type":"tts_start", "sample_rate":24000}))
    try:
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="nova",
            input=text,
            response_format="pcm"
        ) as resp:
            async for chunk in resp.iter_bytes():
                if tts.cancel_event.is_set():
                    break
                await ws.send_text(json.dumps({"type":"tts_chunk", "pcm_b64":base64.b64encode(chunk).decode()}))
    finally:
        await ws.send_text(json.dumps({"type":"tts_end"}))

@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    tts = TTSSession()

    try:
        while True:
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                continue

            t = data.get("type")
            if t == "ping":
                await ws.send_text(json.dumps({"type":"pong"}))
            elif t == "barge_in":
                tts.cancel()
                await ws.send_text(json.dumps({"type":"tts_stop"}))
            elif t == "audio":
                # Send to OpenAI Realtime API for transcription
                async with websockets.connect(
                    "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-transcribe",
                    extra_headers=[("Authorization", f"Bearer {os.getenv('OPENAI_API_KEY','')}"),
                                   ("OpenAI-Beta","realtime=v1")]
                ) as upstream:
                    await upstream.send(json.dumps({
                        "type":"input_audio_buffer.append",
                        "audio":data.get("audio_b64","")
                    }))
                    await upstream.send(json.dumps({"type":"input_audio_buffer.commit"}))
            elif t == "flush":
                pass  # optional commit flush logic

    except WebSocketDisconnect:
        tts.cancel()

# =========================================================
# Startup
# =========================================================
@app.on_event("startup")
async def startup_event():
    print("✅ Voice Assistant started. Browser mic mode active.")
