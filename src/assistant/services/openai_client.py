# services/openai_client.py
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # points to src/assistant
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(DOTENV_PATH)

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ No OPENAI_API_KEY found in .env")

client = AsyncOpenAI(api_key=API_KEY)
