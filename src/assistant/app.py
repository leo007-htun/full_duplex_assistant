import asyncio
import json
import os
import base64
import time
import pyaudio
import websockets
import numpy as np  # optional
import sounddevice as sd  # optional
from playwright.async_api import async_playwright

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader

# ✅ Relative imports
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# ✅ Server config (env-driven)
# =========================================================
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
RATE = 16000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
API_KEY = os.getenv("OPENAI_API_KEY")

# =========================================================
# ✅ FastAPI App + CORS
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
# ✅ Prompt Templates
# =========================================================
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
conversation_history: List[Dict[str, str]] = []


def render_intent_prompt() -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("intent_prompt.j2")
    return template.render()


def render_system_prompt(session_id: str = "SESSION-001") -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("system_prompt.j2")
    return template.render(session_id=session_id)


def render_summarization_prompt(search_context: str) -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("summarization.j2")
    return template.render(search_context=search_context)


# =========================================================
# ✅ Speak text (server speakers; no-op unless ENABLE_VOICE=1)
# =========================================================
async def speak_tts(text: str):
    if not ENABLE_VOICE:
        return
    # ensure previous playback halts before starting new
    tts_player.stop()
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=text,
        response_format="pcm",
    ) as response:
        await tts_player.play_pcm_stream(response)


# =========================================================
# ✅ GPT Intent Classification
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
        parsed = json.loads(resp.choices[0].message.content)
    except Exception:
        parsed = {"intent": "unknown", "reason": "Could not parse GPT response."}
    return parsed


# =========================================================
# ✅ Web Search via Playwright + GPT summary
# =========================================================
async def bing_scrape(query: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.bing.com/search?q={query}", wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("li.b_algo h2 a", timeout=5000)
        except Exception:
            await browser.close()
            return []
        elements = await page.query_selector_all("li.b_algo")
        results = []
        for el in elements[:5]:
            title_el = await el.query_selector("h2 a")
            snippet_el = await el.query_selector(".b_caption p")
            title = await title_el.inner_text() if title_el else ""
            url = await title_el.get_attribute("href") if title_el else ""
            snippet = await snippet_el.inner_text() if snippet_el else ""
            results.append({"title": title.strip(), "snippet": snippet.strip(), "url": url.strip()})
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
    summary_text = summary_resp.choices[0].message.content.strip()
    await speak_tts(summary_text)
    return summary_text


# =========================================================
# ✅ Routes
# =========================================================
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
    reason = intent_data.get("reason", "")

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
        conversation_history += [{"role": "user", "content": user_text},
                                 {"role": "assistant", "content": result}]
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
    else:
        result = "Hmm, I’m not sure what you mean."

    await speak_tts(result)
    return {"intent": intent, "reason": reason, "result": result}


# =========================================================
# ✅ Server mic loop (local dev only; off in production)
# =========================================================
async def mic_stream_vad():
    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [("Authorization", f"Bearer {API_KEY}"), ("OpenAI-Beta", "realtime=v1")]
    async with websockets.connect(uri, extra_headers=headers) as upstream:
        await upstream.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-mini-transcribe", "language": "en"},
                "turn_detection": {"type": "server_vad", "threshold": 0.5,
                                   "prefix_padding_ms": 300, "silence_duration_ms": 500},
                "input_audio_noise_reduction": {"type": "near_field"},
            },
        }))
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                            frames_per_buffer=CHUNK)

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode("utf-8")
                await upstream.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64}))
                await upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))
                await asyncio.sleep(0.01)

        async def recv_transcription():
            buf: Dict[str, str] = {}
            async for message in upstream:
                evt = json.loads(message)
                et = evt.get("type")
                if et == "input_audio_buffer.speech_started":
                    tts_player.stop()
                elif et == "conversation.item.input_audio_transcription.delta":
                    delta = evt.get("delta", "")
                    buf.setdefault(evt.get("item_id"), "")
                    buf[evt.get("item_id")] += delta
                    print("✍️ Partial:", buf[evt.get("item_id")], end="\r")
                elif et == "conversation.item.input_audio_transcription.completed":
                    user_text = evt.get("transcript", "")
                    print(f"\n✅ You said: {user_text}")
                    await determine_intent(ChatMessage(message=user_text))
                    buf.pop(evt.get("item_id"), None)

        await asyncio.gather(send_audio(), recv_transcription())


# =========================================================
# ✅ TTS streaming to browser (cancelable session)
# =========================================================
class TTSSession:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.cancel_event = asyncio.Event()

    def cancel(self):
        # signal streamers to stop and halt server audio immediately
        self.cancel_event.set()
        tts_player.stop()
        if self.task and not self.task.done():
            self.task.cancel()

    def reset(self):
        self.cancel_event = asyncio.Event()
        self.task = None


async def stream_tts_to_browser(ws: WebSocket, text: str, tts: TTSSession):
    """
    Stream OpenAI TTS to the browser in real-time as PCM16 base64 chunks.
    Also optional server playback if ENABLE_VOICE=1.
    """
    SAMPLE_RATE = 24000
    await ws.send_text(json.dumps({"type": "tts_start", "sample_rate": SAMPLE_RATE}))

    async def to_browser():
        try:
            async with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="nova",
                input=text,
                response_format="pcm",  # raw PCM16 mono
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
            # ensure previous playback halted
            tts_player.stop()
            async with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="nova",
                input=text,
                response_format="pcm",
            ) as resp:
                # poll cancel flag between buffer writes
                await tts_player.play_pcm_stream(resp, cancel_event=tts.cancel_event if hasattr(tts_player, "play_pcm_stream") else None)  # if your player supports it
        except asyncio.CancelledError:
            pass
        except Exception:
            # swallow server-audio errors to not break browser stream
            pass

    # Run both, but cancel the sibling if one completes or is cancelled
    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(to_server_speakers())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        try:
            await task
        except Exception:
            pass


# =========================================================
# ✅ Browser ↔ Server WebSocket for realtime streaming + barge-in
# =========================================================
@app.websocket("/ws/echo")
async def ws_echo(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            await ws.send_text(f"echo:{data}")
    except WebSocketDisconnect:
        pass
@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    tts = TTSSession()

    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {os.getenv('OPENAI_API_KEY', '')}")),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    try:
        async with websockets.connect(uri, extra_headers=headers) as upstream:
            # Configure transcription with sensitive VAD for instant pickup
            await upstream.send(json.dumps({
                "type": "transcription_session.update",
                "session": {
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "gpt-4o-mini-transcribe", "language": "en"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.45,
                        "prefix_padding_ms": 150,
                        "silence_duration_ms": 250
                    },
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

            # ---- Browser -> OpenAI ----
            async def forward_up():
                try:
                    while True:
                        msg = await ws.receive_text()
                        data = json.loads(msg)

                        # Manual barge-in from client UI
                        if data.get("type") == "barge_in":
                            tts.cancel()
                            await ws.send_text(json.dumps({"type": "tts_stop"}))
                            continue

                        if data.get("type") == "audio":
                            await upstream.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data["audio_b64"],
                            }))
                            await upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))

                        elif data.get("type") == "flush":
                            await upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))
                except WebSocketDisconnect:
                    pass

            # ---- OpenAI -> Browser ----
            async def forward_down():
                async for raw in upstream:
                    evt = json.loads(raw)
                    t = evt.get("type")

                    if t == "input_audio_buffer.speech_started":
                        # Auto barge-in when user starts speaking
                        tts.cancel()
                        await ws.send_text(json.dumps({"type": "tts_stop"}))
                        await ws.send_text(json.dumps({"type": "event", "name": "speech_started"}))

                    elif t == "conversation.item.input_audio_transcription.delta":
                        await ws.send_text(json.dumps({"type": "partial", "text": evt.get("delta", "")}))

                    elif t == "conversation.item.input_audio_transcription.completed":
                        user_text = evt.get("transcript", "")

                        # Route intent
                        res = await determine_intent(ChatMessage(message=user_text))
                        reply = res.get("result", "")

                        # Send text immediately
                        await ws.send_text(json.dumps({"type": "final", "text": user_text, "reply": reply}))

                        # Start NEW streaming TTS (cancel previous)
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
        # ensure any TTS is stopped on disconnect
        tts.cancel()


# =========================================================
# ✅ Healthcheck
# =========================================================
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant is running!"}


# =========================================================
# ✅ Startup (server mic only if enabled)
# =========================================================
@app.on_event("startup")
async def startup_event():
    if ENABLE_VOICE:
        asyncio.create_task(mic_stream_vad())
        print("✅ Full-duplex ASR+TTS voice loop started (server mic).")
    else:
        print("🛑 Voice loop disabled (ENABLE_VOICE=0) — using browser mic via /ws/stream.")


# =========================================================
# ✅ Uvicorn entry
# =========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("assistant.app:app", host="0.0.0.0", port=8000, reload=True)
