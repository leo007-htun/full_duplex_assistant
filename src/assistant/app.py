import asyncio
import json
import os
import base64
import pyaudio
import websockets
from typing import Dict, Optional, AsyncIterator, List

from fastapi import FastAPI, UploadFile, File, Header, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader

# ✅ Relative imports
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# ✅ Config & App
# =========================================================
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "0") == "1"

app = FastAPI(title="Voice Assistant with Intent Routing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

tts_player = StreamingTTSPlayer()

# =========================================================
# ✅ Prompt Templates
# =========================================================
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
conversation_history: List[Dict[str, str]] = []


def render_intent_prompt() -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    return env.get_template("intent_prompt.j2").render()


def render_system_prompt(session_id: str = "SESSION-001") -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    return env.get_template("system_prompt.j2").render(session_id=session_id)


def render_summarization_prompt(search_context: str) -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    return env.get_template("summarization.j2").render(search_context=search_context)


# =========================================================
# ✅ Speak text interruptibly (server playback)
# =========================================================
async def speak_tts(text: str):
    """Plays PCM to the server's audio device using your StreamingTTSPlayer."""
    tts_player.stop()  # interrupt current playback
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=text,
        response_format="pcm",  # PCM for your player
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
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"intent": "unknown", "reason": "Could not parse GPT response."}


# =========================================================
# ✅ (Optional) Web scraping + summarization (unchanged behavior)
# =========================================================
async def bing_scrape(query: str):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.bing.com/search?q={query}", wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("li.b_algo h2 a", timeout=5000)
        except:
            await browser.close()
            return []

        elements = await page.query_selector_all("li.b_algo")
        results = []
        for el in elements[:5]:
            title_el = await el.query_selector("h2 a")
            snippet_el = await el.query_selector(".b_caption p")
            title = await (title_el.inner_text() if title_el else "")
            url = await (title_el.get_attribute("href") if title_el else "")
            snippet = await (snippet_el.inner_text() if snippet_el else "")
            results.append({"title": title.strip(), "snippet": snippet.strip(), "url": (url or "").strip()})
        await browser.close()
        return results


async def do_web_scraping(query: str) -> str:
    try:
        print(f"🌐 Scraping Bing for: {query}")
        results = await bing_scrape(query)
    except Exception as e:
        print(f"❌ Scraper error: {e}")
        await speak_tts("I couldn’t fetch live search results right now.")
        return "I couldn’t fetch live search results."

    if not results:
        await speak_tts("I didn’t find any relevant search results.")
        return "I didn’t find any relevant search results."

    search_context = "\n".join(
        [f"- {item['title']}: {item['snippet']} ({item['url']})" for item in results]
    )
    summary_prompt = render_summarization_prompt(search_context)
    print("🤖 Asking GPT to summarize search results...")
    summary_resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.4,
        stream=False,
    )
    summary_text = summary_resp.choices[0].message.content.strip()
    print(f"✅ Summary: {summary_text}")
    await speak_tts(summary_text)
    return summary_text


# =========================================================
# ✅ Models
# =========================================================
class ChatMessage(BaseModel):
    message: str


class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"  # for browser playback endpoint


# =========================================================
# ✅ API: Health
# =========================================================
@api.get("/healthz")
async def healthz():
    return {"ok": True}


# =========================================================
# ✅ API: Dummy Weather
# =========================================================
@api.get("/weather")
async def get_weather():
    return {"forecast": "Sunny, 25°C"}


# =========================================================
# ✅ API: Intent → Route → (Server speak)
# =========================================================
@api.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")
    reason = intent_data.get("reason", "")

    if intent == "weather":
        result_data = await get_weather()
        result = f"The forecast is {result_data['forecast']}."
    elif intent == "web_search":
        result = await do_web_scraping(user_text)
    elif intent == "smalltalk":
        system_content = render_system_prompt(session_id="SESSION-001")
        history_with_prompt = [{"role": "system", "content": system_content}] + conversation_history
        history_with_prompt.append({"role": "user", "content": user_text})
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history_with_prompt,
            temperature=0.7,
            stream=False,
        )
        reply_text = chat_resp.choices[0].message.content.strip()
        conversation_history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}]
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
        result = reply_text
    else:
        result = "Hmm, I’m not sure what you mean."

    # Speak result on the server (interruptible)
    await speak_tts(result)

    return {"intent": intent, "reason": reason, "result": result}


# =========================================================
# ✅ API: STT for browser uploads
# =========================================================
@api.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if file.content_type not in {"audio/webm", "audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a"}:
        return JSONResponse({"error": f"Unsupported content type: {file.content_type}"}, status_code=415)

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        return JSONResponse({"error": "Empty audio file."}, status_code=400)
    if len(audio_bytes) > 25 * 1024 * 1024:
        return JSONResponse({"error": "File too large (25MB)."}, status_code=413)

    filename = file.filename or "input.webm"
    mimetype = file.content_type or "application/octet-stream"

    try:
        resp = await client.audio.transcriptions.create(
            file=(filename, io.BytesIO(audio_bytes), mimetype),  # type: ignore[name-defined]
            model="gpt-4o-transcribe",
        )
        return {"text": resp.text}
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)


# =========================================================
# ✅ API: TTS for browser playback (MP3)
# =========================================================
@api.post("/tts")
async def text_to_speech(req: TTSRequest):
    """
    Returns MP3 bytes so the browser <audio> can play them.
    Separate from speak_tts() which plays PCM to the server device.
    """
    # 1) Try streaming if SDK supports it
    try:
        async with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=req.voice,
            input=req.text,
            format="mp3",  # force mp3
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
        pass
    except Exception:
        pass

    # 2) Fallback to non-streaming
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


# =========================================================
# ✅ Background Full-Duplex Voice Loop (ASR + TTS)
# =========================================================
RATE = 16000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
API_KEY = os.getenv("OPENAI_API_KEY")


async def mic_stream_vad():
    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("🎙️ Voice loop connected to OpenAI Realtime API")

        session_payload = {
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-mini-transcribe", "language": "en"},
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
        print("✅ VAD transcription session ready!")

        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_base64 = base64.b64encode(data).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_base64}))
                await asyncio.sleep(0.01)

        async def receive_transcription():
            streaming_buffer: Dict[str, str] = {}
            async for message in ws:
                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "input_audio_buffer.speech_started":
                    print("\n⏹️ User started talking → interrupting GPT speech")
                    tts_player.stop()

                elif event_type == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    item_id = event.get("item_id")
                    if item_id not in streaming_buffer:
                        streaming_buffer[item_id] = ""
                    streaming_buffer[item_id] += delta
                    print("✍️ Partial:", streaming_buffer[item_id], end="\r")

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    user_text = event.get("transcript", "")
                    print(f"\n✅ You said: {user_text}")
                    await determine_intent(ChatMessage(message=user_text))
                    if item_id in streaming_buffer:
                        del streaming_buffer[item_id]

        await asyncio.gather(send_audio(), receive_transcription())


# =========================================================
# ✅ Root + Health (non-/api) for quick probes
# =========================================================
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant is running!"}


# =========================================================
# ✅ Startup: Launch Voice Loop in Background (env-controlled)
# =========================================================
@app.on_event("startup")
async def startup_event():
    if ENABLE_VOICE:
        asyncio.create_task(mic_stream_vad())
        print("✅ Full-duplex ASR+TTS voice loop started!")
    else:
        print("ℹ️ ENABLE_VOICE is off; VAD loop not started.")


# =========================================================
# ✅ Mount API router last
# =========================================================
app.include_router(api)

# =========================================================
# ✅ Proper uvicorn entry (dev)
# =========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.assistant.app:app", host="0.0.0.0", port=8000, reload=True)
