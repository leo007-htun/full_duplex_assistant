import asyncio
import base64
import json
import os
import time
from typing import Dict, List, Optional

import pyaudio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

# ✅ your local modules
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# Config
# =========================================================
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
API_KEY = os.getenv("OPENAI_API_KEY", "")

RATE = 16000
CHUNK = 320  # 20ms @ 16kHz for server mic (if used)
FORMAT = pyaudio.paInt16
CHANNELS = 1

OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-mini-transcribe")
OPENAI_REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={OPENAI_REALTIME_MODEL}"

# =========================================================
# FastAPI + CORS
# =========================================================
app = FastAPI(title="Voice Assistant with Intent Routing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tts_player = StreamingTTSPlayer()

# =========================================================
# Prompts
# =========================================================
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
conversation_history: List[Dict[str, str]] = []


def _env():
    return Environment(loader=FileSystemLoader(PROMPT_DIR))


def render_intent_prompt() -> str:
    return _env().get_template("intent_prompt.j2").render()


def render_system_prompt(session_id: str = "SESSION-001") -> str:
    return _env().get_template("system_prompt.j2").render(session_id=session_id)


def render_summarization_prompt(search_context: str) -> str:
    return _env().get_template("summarization.j2").render(search_context=search_context)


# =========================================================
# TTS helper (server speakers; only if ENABLE_VOICE=1)
# =========================================================
async def speak_tts(text: str):
    if not ENABLE_VOICE or not text:
        return
    try:
        tts_player.stop()  # stop any previous playback
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="nova",
            input=text,
            response_format="pcm",
        ) as response:
            await tts_player.play_pcm_stream(response)
    except Exception:
        # don't let TTS failure break the request
        pass


# =========================================================
# Intent via GPT
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
        stream=False,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"intent": "unknown", "reason": "Could not parse GPT response."}


# =========================================================
# (Optional) Web search via Playwright + summary
# =========================================================
async def bing_scrape(query: str):
    from playwright.async_api import async_playwright  # lazy import

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.bing.com/search?q={query}", wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("li.b_algo h2 a", timeout=5000)
        except Exception:
            await browser.close()
            return []

        items = await page.query_selector_all("li.b_algo")
        results = []
        for el in items[:5]:
            title_el = await el.query_selector("h2 a")
            snippet_el = await el.query_selector(".b_caption p")
            title = (await title_el.inner_text()) if title_el else ""
            url = (await title_el.get_attribute("href")) if title_el else ""
            snippet = (await snippet_el.inner_text()) if snippet_el else ""
            results.append({"title": title.strip(), "snippet": snippet.strip(), "url": (url or "").strip()})
        await browser.close()
        return results


async def do_web_scraping(query: str) -> str:
    try:
        results = await bing_scrape(query)
    except Exception:
        await speak_tts("I couldn’t fetch live search results right now.")
        return "I couldn’t fetch live search results."

    if not results:
        await speak_tts("I didn’t find any relevant search results.")
        return "I didn’t find any relevant search results."

    search_context = "\n".join([f"- {i['title']}: {i['snippet']} ({i['url']})" for i in results])
    summary_prompt = render_summarization_prompt(search_context)
    summary_resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.4,
        stream=False,
    )
    text = summary_resp.choices[0].message.content.strip()
    await speak_tts(text)
    return text


# =========================================================
# HTTP routes
# =========================================================
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant is running!"}


@app.get("/weather")
async def get_weather():
    return {"forecast": "Sunny, 25°C"}


class ChatMessage(BaseModel):
    message: str


@app.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")

    if intent == "weather":
        data = await get_weather()
        result = f"The forecast is {data['forecast']}."
    elif intent == "web_search":
        result = await do_web_scraping(user_text)
    elif intent == "smalltalk":
        system_content = render_system_prompt(session_id="SESSION-001")
        history = [{"role": "system", "content": system_content}] + conversation_history
        history.append({"role": "user", "content": user_text})
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
            temperature=0.7,
            stream=False,
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

    await speak_tts(result)
    return {"intent": intent, "result": result}


# =========================================================
# Server-mic loop (local dev only)
# =========================================================
async def mic_stream_vad():
    """Optional: capture from server mic and stream to Realtime (server VAD; no per-frame commit)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("mic_stream_vad: OPENAI_API_KEY not set; skipping server mic loop.")
        return

    headers = [
        ("Authorization", f"Bearer {api_key}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    async with websockets.connect(OPENAI_REALTIME_URL, extra_headers=headers) as upstream:
        # Configure session
        await upstream.send(json.dumps({
            "type": "session.update",
            "session": {
                "input_audio_format": {"type": "pcm16", "sample_rate_hz": RATE},
                "input_audio_transcription": {"model": OPENAI_REALTIME_MODEL, "language": "en"},
                "turn_detection": {"type": "server_vad", "threshold": 0.32,
                                   "prefix_padding_ms": 300, "silence_duration_ms": 350},
                "input_audio_noise_reduction": {"type": "near_field"},
            }
        }))

        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode("utf-8")
                await upstream.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64}))
                # Do NOT commit here with server VAD
                await asyncio.sleep(CHUNK / RATE)  # ~20ms

        async def recv_transcription():
            async for message in upstream:
                evt = json.loads(message)
                et = evt.get("type")
                if et == "input_audio_buffer.speech_started":
                    tts_player.stop()
                elif et in ("conversation.item.input_audio_transcription.delta",
                            "transcription.delta",
                            "response.audio_transcript.delta"):
                    pass  # could log partials for debugging
                elif et in ("conversation.item.input_audio_transcription.completed",
                            "transcription.completed"):
                    user_text = evt.get("transcript", "")
                    await determine_intent(ChatMessage(message=user_text))
                elif et in ("error", "response.error"):
                    print("UPSTREAM ERROR (server mic):", json.dumps(evt, indent=2))

        await asyncio.gather(send_audio(), recv_transcription())


# =========================================================
# TTS streaming to the browser
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
    SAMPLE_RATE = 24000
    await ws.send_text(json.dumps({"type": "tts_start", "sample_rate": SAMPLE_RATE}))

    async def to_browser():
        try:
            async with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="nova",
                input=text,
                response_format="pcm",
            ) as resp:
                async for chunk in resp.iter_bytes():
                    if tts.cancel_event.is_set():
                        break
                    b64 = base64.b64encode(chunk).decode("utf-8")
                    await ws.send_text(json.dumps({"type": "tts_chunk", "pcm_b64": b64}))
        except asyncio.CancelledError:
            pass
        finally:
            await ws.send_text(json.dumps({"type": "tts_end"}))

    async def to_server_speakers():
        if not ENABLE_VOICE:
            return
        try:
            tts_player.stop()
            async with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="nova",
                input=text,
                response_format="pcm",
            ) as resp:
                if "cancel_event" in tts_player.play_pcm_stream.__code__.co_varnames:
                    await tts_player.play_pcm_stream(resp, cancel_event=tts.cancel_event)
                else:
                    await tts_player.play_pcm_stream(resp)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(to_server_speakers())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        try:
            await task
        except Exception:
            pass


# =========================================================
# WebSockets
# =========================================================
@app.websocket("/ws/echo")
async def ws_echo(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(msg)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    tts = TTSSession()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        await ws.send_text(json.dumps({"type": "error", "detail": "Missing OPENAI_API_KEY"}))
        await ws.close()
        return

    headers = [
        ("Authorization", f"Bearer {api_key}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    try:
        async with websockets.connect(OPENAI_REALTIME_URL, extra_headers=headers) as upstream:
            # Configure session for browser mic stream
            await upstream.send(json.dumps({
                "type": "session.update",
                "session": {
                    "input_audio_format": {"type": "pcm16", "sample_rate_hz": 16000},
                    "input_audio_transcription": {"model": OPENAI_REALTIME_MODEL, "language": "en"},
                    "turn_detection": {"type": "server_vad", "threshold": 0.32,
                                       "prefix_padding_ms": 300, "silence_duration_ms": 350},
                    "input_audio_noise_reduction": {"type": "near_field"},
                },
            }))

            async def ping():
                while True:
                    try:
                        await upstream.send(json.dumps({"type": "ping", "timestamp": time.time()}))
                        await asyncio.sleep(20)
                    except Exception:
                        break

            async def forward_up():
                try:
                    while True:
                        # Expecting JSON text frames from browser
                        msg = await ws.receive_text()
                        try:
                            data = json.loads(msg)
                        except Exception:
                            # ignore non-JSON frames
                            continue

                        t = data.get("type")
                        if t == "ping":
                            await ws.send_text(json.dumps({"type": "pong", "t": time.time()}))
                            continue

                        if t == "barge_in":
                            tts.cancel()
                            await ws.send_text(json.dumps({"type": "tts_stop"}))
                            continue

                        if t == "audio":
                            # ACK back to the browser so you SEE activity immediately
                            try:
                                raw = base64.b64decode(data.get("audio_b64", ""))
                                await ws.send_text(json.dumps({
                                    "type": "ack",
                                    "kind": "audio",
                                    "bytes": len(raw),
                                }))
                            except Exception:
                                pass

                            # Append only; with server VAD the server will commit on silence.
                            await upstream.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data.get("audio_b64", ""),
                            }))
                            continue

                        if t == "flush":
                            # Manual force-send if you want it (e.g., a button on the page)
                            await upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            continue
                except WebSocketDisconnect:
                    pass

            async def forward_down():
                async for raw in upstream:
                    evt = json.loads(raw)
                    et = evt.get("type")

                    if et in ("error", "response.error"):
                        # Surface upstream errors to browser + server logs
                        print("UPSTREAM ERROR:", json.dumps(evt, indent=2))
                        try:
                            await ws.send_text(json.dumps({"type": "error", "detail": evt}))
                        except Exception:
                            pass
                        continue

                    # Optional heartbeat to understand upstream flow
                    if et not in (
                        "conversation.item.input_audio_transcription.delta",
                        "input_audio_buffer.speech_started",
                        "conversation.item.input_audio_transcription.completed",
                        "input_audio_buffer.committed",
                        "input_audio_buffer.speech_stopped",
                    ):
                        print("upstream evt:", et)

                    if et == "input_audio_buffer.speech_started":
                        tts.cancel()
                        await ws.send_text(json.dumps({"type": "tts_stop"}))
                        await ws.send_text(json.dumps({"type": "event", "name": "speech_started"}))

                    elif et in ("conversation.item.input_audio_transcription.delta",
                                "transcription.delta",
                                "response.audio_transcript.delta"):
                        await ws.send_text(json.dumps({"type": "partial", "text": evt.get("delta", "")}))

                    elif et in ("conversation.item.input_audio_transcription.completed",
                                "transcription.completed"):
                        user_text = evt.get("transcript", "")
                        res = await determine_intent(ChatMessage(message=user_text))
                        reply = res.get("result", "")
                        await ws.send_text(json.dumps({"type": "final", "text": user_text, "reply": reply}))
                        tts.cancel()
                        tts.reset()
                        tts.task = asyncio.create_task(stream_tts_to_browser(ws, reply, tts))

            await asyncio.gather(ping(), forward_up(), forward_down())

    except Exception as e:
        print("ws_stream error:", e)
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        tts.cancel()


# =========================================================
# Startup
# =========================================================
@app.on_event("startup")
async def startup_event():
    if ENABLE_VOICE:
        asyncio.create_task(mic_stream_vad())
        print("✅ Full-duplex ASR+TTS voice loop started (server mic).")
    else:
        print("🛑 Voice loop disabled (ENABLE_VOICE=0) — using browser mic via /ws/stream.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("assistant.app:app", host="0.0.0.0", port=8000, reload=True)
