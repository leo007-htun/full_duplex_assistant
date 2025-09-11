# src/assistant/app.py
import os
import time
import httpx
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in env")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
FRONTEND_ORIGINS = set(ALLOWED_ORIGINS or ["https://com-cloud.cloud"])

app = FastAPI(title="Full Duplex Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---- Tiny in-memory token bucket per client IP for /rt-token ----
WINDOW_SECS = 10
MAX_TOKENS = 10  # avg
BURST = 20

buckets = defaultdict(lambda: {"ts": 0.0, "tokens": float(BURST)})

def allow(ip: str) -> bool:
    now = time.monotonic()
    b = buckets[ip]
    elapsed = max(0.0, now - b["ts"])
    b["ts"] = now
    # Refill at MAX_TOKENS per WINDOW_SECS
    refill = (elapsed / WINDOW_SECS) * MAX_TOKENS
    b["tokens"] = min(float(BURST), b["tokens"] + refill)
    if b["tokens"] >= 1.0:
        b["tokens"] -= 1.0
        return True
    return False

@app.middleware("http")
async def restrict_rt_token(request: Request, call_next):
    # Only the frontend origin can mint tokens
    if request.url.path.startswith("/rt-token"):
        origin = request.headers.get("origin", "")
        if origin not in FRONTEND_ORIGINS:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        # Basic IP rate-limit
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
        if not allow(client_ip):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
    return await call_next(request)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

# Mint ephemeral token for OpenAI Realtime
@app.get("/rt-token")
async def rt_token():
    url = "https://api.openai.com/v1/realtime/sessions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini-realtime-preview",
        "voice": "alloy",  # default; client can update via session.update
    }
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        # Don't leak details to client; log r.text in real logs if needed
        raise HTTPException(r.status_code, "upstream error")
    resp = JSONResponse(r.json())
    resp.headers["Cache-Control"] = "no-store"
    return resp
