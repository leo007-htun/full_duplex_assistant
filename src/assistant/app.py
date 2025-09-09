import asyncio, io, json, os
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader

# Your OpenAI client + optional local PCM player
from .services.openai_client import client
try:
    from .voice.tts_player import StreamingTTSPlayer
    tts_player = StreamingTTSPlayer()
except Exception:
    tts_player = None

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
app = FastAPI(title="COM Cloud • Full-Duplex Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
api = APIRouter(prefix="/api")

# Templates
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(loader=FileSystemLoader(PROMPT_DIR))
def intent_prompt() -> str: return _env.get_template("intent_prompt.j2").render()
def system_prompt(session_id="S-1") -> str: return _env.get_template("system_prompt.j2").render(session_id=session_id)

# Memory
chat_history: List[Dict[str,str]] = []

# Models
class ChatIn(BaseModel): message: str
class TTSIn(BaseModel):
    text: str
    voice: str = "alloy"

# Health
@api.get("/healthz")
async def healthz(): return {"ok": True}

# Example domain routes
@api.get("/weather")
async def weather():
    return {"type": "weather", "text": "Today looks sunny, about 25°C."}

@api.post("/talk")
async def talk(msg: ChatIn):
    global chat_history
    convo = [{"role":"system","content": system_prompt()}] + chat_history
    convo.append({"role":"user","content": msg.message})
    resp = await client.chat.completions.create(
        model="gpt-4o-mini", messages=convo, temperature=0.7
    )
    text = resp.choices[0].message.content.strip()
    chat_history += [{"role":"user","content":msg.message},{"role":"assistant","content":text}]
    chat_history[:] = chat_history[-40:]
    return {"type":"talk","text": text}

# Intent router (always returns text to speak)
@api.post("/determine_intent")
async def determine_intent(inp: ChatIn):
    # classify
    try:
        intent_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content": intent_prompt()},
                {"role":"user","content": inp.message}
            ],
            temperature=0.2, response_format={"type":"json_object"}
        )
        intent_obj = json.loads(intent_resp.choices[0].message.content)
    except Exception:
        intent_obj = {"intent":"unknown","reason":"parse_failed"}

    intent = intent_obj.get("intent","unknown")

    # route (and ALWAYS produce a result string)
    if intent == "weather":
        w = await weather()
        result = w["text"]
    elif intent in ("smalltalk","talk","chat"):
        t = await talk(ChatIn(message=inp.message))
        result = t["text"]
    else:
        # fallback to chat so client always has something to TTS
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content": system_prompt()},
                {"role":"user","content": inp.message},
            ],
            temperature=0.7,
        )
        result = resp.choices[0].message.content.strip()

    # (Optional) play on server speakers if you have a device
    if tts_player:
        try: tts_player.stop()
        except: pass

    return {"intent": intent, "result": result}

# STT upload (accepts webm/ogg/mp4/mpeg; strips codecs param)
@api.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    raw_ct = (file.content_type or "application/octet-stream").lower()
    base_ct = raw_ct.split(";")[0].strip()
    allowed = {"audio/webm","audio/ogg","audio/mpeg","audio/wav","audio/mp4","audio/x-m4a","application/octet-stream"}
    if base_ct not in allowed:
        return JSONResponse({"error": f"Unsupported content type: {raw_ct}"}, status_code=415)

    data = await file.read()
    if not data: return JSONResponse({"error":"Empty file"}, status_code=400)
    if len(data) > 25*1024*1024: return JSONResponse({"error":"Too large"}, status_code=413)

    name = (file.filename or "input").strip()
    if "." not in name:
        name += {
            "audio/webm":".webm","audio/ogg":".ogg","audio/mpeg":".mp3",
            "audio/wav":".wav","audio/mp4":".m4a","audio/x-m4a":".m4a"
        }.get(base_ct,"")

    try:
        tr = await client.audio.transcriptions.create(
            file=(name, io.BytesIO(data), base_ct),
            model="gpt-4o-transcribe",
        )
        return {"text": tr.text}
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)

# TTS (MP3) with cross-SDK param compatibility
@api.post("/tts")
async def tts(req: TTSIn):
    text = (req.text or "").strip()
    voice = (req.voice or "alloy").strip() or "alloy"
    if not text: return JSONResponse({"error":"Empty text"}, status_code=400)

    variants = (
        {"format":"mp3"}, {"response_format":"mp3"}, {"audio_format":"mp3"}, {}
    )
    last = None
    for extra in variants:
        try:
            res = await client.audio.speech.create(
                model="gpt-4o-mini-tts", voice=voice, input=text, **extra
            )
            buf = None
            if hasattr(res,"content") and isinstance(res.content,(bytes,bytearray)):
                buf = bytes(res.content)
            elif hasattr(res,"read"): buf = await res.read()
            elif isinstance(res,(bytes,bytearray)): buf = bytes(res)
            if buf:
                return Response(
                    content=buf, media_type="audio/mpeg",
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
                )
        except TypeError as e:
            last = e; continue
        except Exception as e:
            last = e; break
    return JSONResponse({"error": f"TTS failed: {last}"}, status_code=500)

@api.post("/tts/stop")
async def tts_stop():
    try:
        if tts_player: tts_player.stop()
    except: pass
    return {"ok": True}

# Wire router + health mirror
app.include_router(api)
@app.get("/healthz") async def healthz_root(): return await healthz()
