import asyncio
import json
import os
import base64
import subprocess
import pyaudio
import websockets
import numpy as np
import sounddevice as sd
from playwright.async_api import async_playwright

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
from jinja2 import Environment, FileSystemLoader

# ✅ Relative imports
from .services.openai_client import client
from .voice.tts_player import StreamingTTSPlayer

# =========================================================
# ✅ FastAPI App
# =========================================================
app = FastAPI(title="Voice Assistant with Intent Routing")
tts_player = StreamingTTSPlayer()

# =========================================================
# ✅ Prompt Templates
# =========================================================
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")

conversation_history = []


def render_intent_prompt() -> str:
    """Loads the intent classifier prompt"""
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("intent_prompt.j2")
    return template.render()


def render_system_prompt(session_id: str = "SESSION-001") -> str:
    """Loads the Jarvis smalltalk system prompt"""
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("system_prompt.j2")
    return template.render(session_id=session_id)


def render_summarization_prompt(search_context: str) -> str:
    """Loads summarization.j2 with search results context"""
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("summarization.j2")
    return template.render(search_context=search_context)


# =========================================================
# ✅ Speak text interruptibly
# =========================================================
async def speak_tts(text: str):
    tts_player.stop()  # Stop any ongoing playback
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=text,
        response_format="pcm"
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
            {"role": "user", "content": message}
        ],
        temperature=0.2,
        stream=False
    )

    try:
        parsed = json.loads(resp.choices[0].message.content)
    except Exception:
        parsed = {"intent": "unknown", "reason": "Could not parse GPT response."}

    return parsed


# =========================================================
# ✅ Web Search using scraper.js + GPT summarization
# =========================================================


async def bing_scrape(query: str):
    """Scrape Bing search results (lazy import to avoid startup hang)."""
    from playwright.async_api import async_playwright  # ✅ Lazy import only when needed

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.bing.com/search?q={query}", wait_until="domcontentloaded")

        # Wait for search result items
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

            title = await title_el.inner_text() if title_el else ""
            url = await title_el.get_attribute("href") if title_el else ""
            snippet = await snippet_el.inner_text() if snippet_el else ""

            results.append({
                "title": title.strip(),
                "snippet": snippet.strip(),
                "url": url.strip()
            })

        await browser.close()
        return results


async def do_web_scraping(query: str) -> str:
    """Run Bing scraping → GPT summarization → interruptible TTS."""
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

    # ✅ Convert results into readable context for GPT
    search_context = "\n".join(
        [f"- {item['title']}: {item['snippet']} ({item['url']})" for item in results]
    )

    # ✅ Render `summarization.j2` template
    summary_prompt = render_summarization_prompt(search_context)

    print("🤖 Asking GPT to summarize search results...")
    summary_resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.4,
        stream=False
    )

    summary_text = summary_resp.choices[0].message.content.strip()

    print(f"✅ Summary: {summary_text}")

    # ✅ Speak the final summary
    await speak_tts(summary_text)
    print(summary_text)
    return summary_text





# =========================================================
# ✅ Dummy Weather Tool
# =========================================================
@app.get("/weather")
async def get_weather():
    return {"forecast": "Sunny, 25°C"}


# =========================================================
# ✅ Request Model
# =========================================================
class ChatMessage(BaseModel):
    message: str


# =========================================================
# ✅ Intent → Route → Speak
# =========================================================
@app.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message

    # 1️⃣ Classify intent
    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")
    reason = intent_data.get("reason", "")

    # 2️⃣ Confirm intent verbally
    confirm_text = f"Oh, you want me to handle '{intent}'. {reason}. Let me work on it."
    #await speak_tts(confirm_text)

    # 3️⃣ Route internally
    if intent == "weather":
        result_data = await get_weather()
        result = f"The forecast is {result_data['forecast']}."

    elif intent == "web_search":
        result = await do_web_scraping(user_text)

    elif intent == "smalltalk":
        # ✅ Load Jarvis smalltalk prompt
        system_content = render_system_prompt(session_id="SESSION-001")

        # ✅ Combine memory with system prompt
        history_with_prompt = [{"role": "system", "content": system_content}] + conversation_history
        history_with_prompt.append({"role": "user", "content": user_text})

        # ✅ Call GPT
        chat_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history_with_prompt,
            temperature=0.7,
            stream=False
        )
        reply_text = chat_resp.choices[0].message.content.strip()

        # ✅ Save conversation memory
        conversation_history.append({"role": "user", "content": user_text})
        conversation_history.append({"role": "assistant", "content": reply_text})

        # ✅ Trim if too big
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]

        result = reply_text

    else:
        result = "Hmm, I’m not sure what you mean."

    # 4️⃣ Speak final result
    await speak_tts(result)

    return {
        "intent": intent,
        "reason": reason,
        "result": result
    }


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
        ("OpenAI-Beta", "realtime=v1")
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("🎙️ Voice loop connected to OpenAI Realtime API")

        # Setup session
        session_payload = {
            "type": "transcription_session.update",
            "session": {
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
                },
                "input_audio_noise_reduction": {
                    "type": "near_field"
                }
            }
        }
        await ws.send(json.dumps(session_payload))
        print("✅ VAD transcription session ready!")

        # Mic capture
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                            input=True, frames_per_buffer=CHUNK)

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_base64 = base64.b64encode(data).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_base64}))
                await asyncio.sleep(0.01)

        async def receive_transcription():
            streaming_buffer = {}
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
# ✅ Healthcheck
# =========================================================
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant is running!"}


# =========================================================
# ✅ Startup: Launch Voice Loop in Background
# =========================================================
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(mic_stream_vad())
    print("✅ Full-duplex ASR+TTS voice loop started!")


# =========================================================
# ✅ Proper uvicorn entry
# =========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.assistant.app:app", host="0.0.0.0", port=8000, reload=True)
