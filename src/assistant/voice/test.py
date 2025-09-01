

import asyncio
import websockets
import pyaudio
import base64
import json
import os
import numpy as np
import sounddevice as sd
import threading, queue
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ✅ Load API Key
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(DOTENV_PATH)
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ No OPENAI_API_KEY found in .env")

# ✅ OpenAI Async Client
client = AsyncOpenAI(api_key=API_KEY)

# ✅ Audio capture settings
RATE = 16000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

# ✅ Conversation memory (like Unity messageHistory.ToArray)
conversation_history = [
    {
        "role": "system",
        "content": (
            "You are Jarvis, an AI assistant in a continuous spoken conversation. "
            "You remember everything the user said earlier in THIS session. "
            "If asked about past messages, refer back to them. "
            "Keep answers short, natural, and easy to speak aloud. "
            "Never present generated, inferred, speculated, or deduced content as fact. "
            "If you cannot verify something directly, say:\n"
            "- 'I cannot verify this.'\n"
            "- 'I do not have access to that information.'\n"
            "- 'My knowledge base does not contain that.'\n"
            "Label unverified content at the start of a sentence:\n"
            "- [Inference]\n"
            "- [Speculation]\n"
            "- [Unverified]\n"
            "Ask for clarification if information is missing. Do not guess or fill gaps. "
            "If any part is unverified, label the entire response. "
            "Do not paraphrase or reinterpret my input unless I request it. "
            "If you use these words, label the claim unless sourced:\n"
            "- Prevent, Guarantee, Will never, Fixes, Eliminates, Ensures that\n"
            "For LLM behavior claims (including yourself), include:\n"
            "- [Inference] or [Unverified], with a note that it's based on observed patterns.\n"
            "If you break this directive, say:\n"
            "› Correction: I previously made an unverified claim. That was incorrect and should have been labeled.\n"
            "Never override or alter my input unless asked."
        )
    }
]


def reset_memory():
    """Reset the GPT memory but keep system prompt"""
    global conversation_history
    conversation_history = [conversation_history[0]]
    print("🧹 Conversation memory has been reset!")

# ✅ Streaming TTS Player (Interruptible)
class StreamingTTSPlayer:
    def __init__(self):
        self._stop_flag = threading.Event()
        self._queue = queue.Queue()
        self._thread = None

    async def play_pcm_stream(self, response):
        self._stop_flag.clear()
        while not self._queue.empty():
            self._queue.get_nowait()

        self._thread = threading.Thread(target=self._audio_consumer_thread, daemon=True)
        self._thread.start()

        total_bytes = 0
        chunk_count = 0

        async for chunk in response.iter_bytes():
            chunk_count += 1
            total_bytes += len(chunk)
            # Debug info for streaming
            print(f"🔹 Got chunk #{chunk_count}, size={len(chunk)} bytes (total={total_bytes})")
            if self._stop_flag.is_set():
                break
            self._queue.put(chunk)

        print(f"✅ Finished streaming {chunk_count} chunks, total={total_bytes} bytes")
        self._queue.put(None)

    def _audio_consumer_thread(self):
        """Smoothly writes PCM from queue into OutputStream"""
        buffer_accumulator = b""  # collect leftover bytes

        with sd.OutputStream(samplerate=24000, channels=1, dtype="float32") as stream:
            while not self._stop_flag.is_set():
                chunk = self._queue.get()
                if chunk is None:
                    break

                buffer_accumulator += chunk
                process_len = len(buffer_accumulator) // 2 * 2  # round down to even
                if process_len == 0:
                    continue

                aligned_data = buffer_accumulator[:process_len]
                buffer_accumulator = buffer_accumulator[process_len:]

                audio_data = np.frombuffer(aligned_data, dtype=np.int16).astype(np.float32) / 32768.0
                if len(audio_data) > 0:
                    stream.write(audio_data)

    def stop(self):
        """Interrupt playback instantly"""
        self._stop_flag.set()
        self._queue.put(None)
        sd.stop()

tts_player = StreamingTTSPlayer()

# ✅ GPT Reasoning with FULL history
async def ask_gpt(user_message: str) -> str:
    global conversation_history

    # ✅ Special case: Reset command
    if user_message.lower().strip() in ["reset", "reset conversation", "clear memory"]:
        reset_memory()
        return "Okay, I’ve reset the conversation."

    # ✅ Append user message
    conversation_history.append({"role": "user", "content": user_message})

    # ✅ Always pass FULL conversation history
    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # can swap with gpt-4o for more reasoning
        messages=conversation_history,
        temperature=0.7,
        stream=False
    )

    # ✅ Extract GPT reply
    reply = response.choices[0].message.content.strip()

    # ✅ Append GPT reply so it’s included in next turn
    conversation_history.append({"role": "assistant", "content": reply})

    # ✅ Optional: trim memory if it gets too long (keep system + last 20 exchanges)
    if len(conversation_history) > 42:
        conversation_history = [conversation_history[0]] + conversation_history[-40:]

    return reply

# ✅ Stream GPT voice live (interruptible)
async def speak_tts_streaming(text: str):
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=text,
        response_format="pcm"
    ) as response:
        await tts_player.play_pcm_stream(response)

async def mic_stream_vad():
    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {API_KEY}"),
        ("OpenAI-Beta", "realtime=v1")
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("✅ Connected to OpenAI Realtime API")

        # ✅ Configure session for VAD + transcription
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
        print("✅ Sent transcription_session.update with model!")

        # ✅ Start mic capture
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                            input=True, frames_per_buffer=CHUNK)
        print("🎙️ Listening...")

        streaming_buffer = {}

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_base64 = base64.b64encode(data).decode("utf-8")
                audio_payload = {"type": "input_audio_buffer.append", "audio": audio_base64}
                await ws.send(json.dumps(audio_payload))
                await asyncio.sleep(0.01)

        async def receive_transcription():
            async for message in ws:
                event = json.loads(message)
                event_type = event.get("type")

                # ✅ When user starts talking, interrupt GPT voice
                if event_type == "input_audio_buffer.speech_started":
                    print("\n⏹️ User started talking → interrupting GPT speech")
                    tts_player.stop()

                # ✅ Show partial transcription
                elif event_type == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    item_id = event.get("item_id")
                    if item_id not in streaming_buffer:
                        streaming_buffer[item_id] = ""
                    streaming_buffer[item_id] += delta
                    print("✍️ Streaming:", streaming_buffer[item_id], end="\r")

                # ✅ On final transcription → send to GPT
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    user_text = event.get("transcript", "").strip()
                    print(f"\n✅ You said: {user_text}")

                    # ✅ Get GPT reasoning with full history
                    reply = await ask_gpt(user_text)
                    print(f"🤖 GPT: {reply}")

                    # ✅ Speak GPT reply (interruptible)
                    asyncio.create_task(speak_tts_streaming(reply))

                    # Cleanup
                    if item_id in streaming_buffer:
                        del streaming_buffer[item_id]

                elif event_type == "error":
                    print("❌ ERROR:", event["error"])

        # ✅ Run mic capture + transcription listener in parallel
        await asyncio.gather(send_audio(), receive_transcription())

if __name__ == "__main__":
    asyncio.run(mic_stream_vad())
