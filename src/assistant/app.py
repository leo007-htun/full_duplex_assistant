import os
import io
import json
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

# OpenAI SDK
import openai
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Voice Assistant API")

# Allow CORS for your hosted frontend
ALLOWED_ORIGINS = ["https://com-cloud.cloud"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Models
# ---------------------------
class ChatMessage(BaseModel):
    message: str

# ---------------------------
# /determine_intent endpoint
# ---------------------------
@app.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    user_text = msg.message
    # Call GPT-4o-mini to determine response
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":user_text}],
            temperature=0.5,
            stream=False
        )
        gpt_reply = resp.choices[0].message.content.strip()
    except Exception as e:
        gpt_reply = f"Error generating response: {str(e)}"
    return {"result": gpt_reply}

# ---------------------------
# /tts endpoint
# ---------------------------
@app.get("/tts")
async def tts(text: str, voice: str = "nova"):
    """
    Generate TTS PCM or WAV audio for given text.
    """
    try:
        # Streaming TTS from OpenAI (gpt-4o-mini-tts)
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            response_format="wav"
        ) as response:
            audio_bytes = b""
            for chunk in response.iter_bytes():
                audio_bytes += chunk
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
    except Exception as e:
        return Response(content=f"Error generating TTS: {str(e)}", status_code=500)

# ---------------------------
# Health check
# ---------------------------
@app.get("/")
def home():
    return {"status": "ok", "message": "Assistant API is running."}

# ---------------------------
# Run app
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
