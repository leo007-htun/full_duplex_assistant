import asyncio, json, base64
import websockets
import pyaudio
from services.openai_client import client
from core.conversation import ask_gpt
from voice.tts_player import StreamingTTSPlayer

# Mic config
RATE = 16000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

tts_player = StreamingTTSPlayer()

async def speak_tts_streaming(text: str):
    async with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=text,
        response_format="pcm"
    ) as response:
        await tts_player.play_pcm_stream(response)

async def mic_stream_vad():
    from services.openai_client import API_KEY

    uri = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = [
        ("Authorization", f"Bearer {API_KEY}"),
        ("OpenAI-Beta", "realtime=v1")
    ]

    async with websockets.connect(uri, extra_headers=headers) as ws:
        print("✅ Connected to OpenAI Realtime API")

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
        print("✅ VAD session configured!")

        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                            input=True, frames_per_buffer=CHUNK)
        print("🎙️ Listening...")

        streaming_buffer = {}

        async def send_audio():
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64}))
                await asyncio.sleep(0.01)

        async def receive_transcription():
            async for message in ws:
                event = json.loads(message)
                etype = event.get("type")

                if etype == "input_audio_buffer.speech_started":
                    print("\n⏹️ User started talking → interrupting GPT speech")
                    tts_player.stop()

                elif etype == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    iid = event.get("item_id")
                    streaming_buffer.setdefault(iid, "")
                    streaming_buffer[iid] += delta
                    print("✍️ Streaming:", streaming_buffer[iid], end="\r")

                elif etype == "conversation.item.input_audio_transcription.completed":
                    iid = event.get("item_id")
                    user_text = event.get("transcript", "").strip()
                    print(f"\n✅ You said: {user_text}")

                    reply = await ask_gpt(user_text)
                    print(f"🤖 GPT: {reply}")

                    asyncio.create_task(speak_tts_streaming(reply))
                    if iid in streaming_buffer:
                        del streaming_buffer[iid]

                elif etype == "error":
                    print("❌ ERROR:", event["error"])

        await asyncio.gather(send_audio(), receive_transcription())
