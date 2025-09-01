from jinja2 import Environment, FileSystemLoader
import os
from services.openai_client import client  # ✅ FIXED

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "../prompts")

def render_system_prompt(session_id=None):
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("system_prompt.j2")
    return template.render(session_id=session_id)

conversation_history = [
    {"role": "system", "content": render_system_prompt(session_id="ABC123")}
]

def reset_memory():
    global conversation_history
    conversation_history = [
        {"role": "system", "content": render_system_prompt(session_id="ABC123")}
    ]
    print("🧹 Conversation memory reset!")

async def ask_gpt(user_message: str) -> str:
    global conversation_history

    if user_message.lower().strip() in ["reset", "reset conversation", "clear memory"]:
        reset_memory()
        return "Okay, I've reset the conversation."

    conversation_history.append({"role": "user", "content": user_message})

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation_history,
        temperature=0.7,
        stream=False
    )
    reply = response.choices[0].message.content.strip()

    conversation_history.append({"role": "assistant", "content": reply})

    if len(conversation_history) > 42:
        conversation_history = [conversation_history[0]] + conversation_history[-40:]

    return reply
