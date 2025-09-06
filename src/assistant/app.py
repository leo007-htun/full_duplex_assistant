import asyncio
import json
import os
from typing import Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .services.openai_client import client

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://com-cloud.cloud").split(",")
API_KEY = os.getenv("OPENAI_API_KEY", "")

app = FastAPI(title="Browser-First Voice Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_history: List[Dict[str, str]] = []

# -------------------
# Prompts
# -------------------
from jinja2 import Environment, FileSystemLoader
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(loader=FileSystemLoader(PROMPT_DIR))


def render_intent_prompt() -> str:
    return _env.get_template("intent_prompt.j2").render()


def render_system_prompt(session_id: str = "SESSION-001") -> str:
    return _env.get_template("system_prompt.j2").render(session_id=session_id)


class ChatMessage(BaseModel):
    message: str


# -------------------
# Determine intent
# -------------------
async def determine_intent_gpt(message: str) -> Dict[str, str]:
    prompt = render_intent_prompt()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.2,
        stream=False,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"intent": "unknown", "reason": "Could not parse GPT response."}


@app.post("/determine_intent")
async def determine_intent(msg: ChatMessage):
    global conversation_history
    user_text = msg.message
    intent_data = await determine_intent_gpt(user_text)
    intent = intent_data.get("intent", "unknown")

    # Simple smalltalk logic
    if intent == "smalltalk":
        system_content = render_system_prompt()
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
        result = f"Intent: {intent}, GPT reply: {intent_data.get('response','')}"

    return {"intent": intent, "result": result}
