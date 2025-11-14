# src/assistant/app.py
import os
import time
import httpx
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
from .core.metrics import (
    MetricsMiddleware,
    initialize_metrics,
    get_metrics_response,
    token_mint_latency,
    rate_limit_exceeded,
    record_client_metrics,
    track_time,
    openai_api_latency
)
#from .api.responses import router as responses_router
#app.include_router(responses_router)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in env")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
FRONTEND_ORIGINS = set(ALLOWED_ORIGINS or ["https://com-cloud.cloud"])

#middleware blocked anything without Origin → 403
ALLOWED_HOSTS = {(urlparse(o).netloc or o.replace("https://", "").replace("http://", ""))
    for o in FRONTEND_ORIGINS
}

app = FastAPI(title="Full Duplex Assistant API", version="1.0.0")

# Initialize metrics system
initialize_metrics(version="1.0.0", environment=os.getenv("ENVIRONMENT", "production"))

# Add metrics middleware FIRST (to track all requests)
app.add_middleware(MetricsMiddleware)

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

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics"""
    content, media_type = get_metrics_response()
    return Response(content=content, media_type=media_type)

# Client metrics ingestion endpoint
@app.post("/api/metrics")
async def ingest_client_metrics(request: Request):
    """
    Receive performance metrics from client and record them
    """
    try:
        metrics_data = await request.json()
        record_client_metrics(metrics_data)
        return {"status": "recorded"}
    except Exception as e:
        raise HTTPException(500, f"Failed to record metrics: {str(e)}")

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

    # Track token minting latency
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(url, headers=headers, json=payload)

        duration = time.perf_counter() - start
        token_mint_latency.observe(duration)

        if r.status_code >= 400:
            # Don't leak details to client; log r.text in real logs if needed
            raise HTTPException(r.status_code, "upstream error")

        resp = JSONResponse(r.json())
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except httpx.TimeoutException:
        duration = time.perf_counter() - start
        token_mint_latency.observe(duration)
        raise HTTPException(504, "upstream timeout")

@app.middleware("http")
async def restrict_rt_token(request: Request, call_next):
    # Only protect the token endpoint
    if request.url.path.startswith("/rt-token"):
        # CORS preflight (if any)
        if request.method == "OPTIONS":
            return JSONResponse({}, status_code=200)

        origin  = request.headers.get("origin")
        referer = request.headers.get("referer")
        host    = request.headers.get("host")  # e.g. "com-cloud.cloud"

        # Allowed if:
        # - Origin header is present AND whitelisted, OR
        # - No Origin, but Host matches allowed hosts (same-origin GET), OR
        # - Referer host matches allowed hosts (fallback)
        allowed = False
        if FRONTEND_ORIGINS:
            if origin and origin in FRONTEND_ORIGINS:
                allowed = True
            elif host and host in ALLOWED_HOSTS:
                allowed = True
            elif referer:
                ref_host = urlparse(referer).netloc
                allowed = ref_host in ALLOWED_HOSTS
        else:
            # If no FRONTEND_ORIGINS configured, allow by default
            allowed = True

        if not allowed:
            return JSONResponse({"error": "forbidden"}, status_code=403)

        # Basic IP rate-limit
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
        if not allow(client_ip):
            # Track rate limit violation
            rate_limit_exceeded.labels(endpoint="/rt-token", client_ip=client_ip).inc()
            return JSONResponse({"error": "rate_limited"}, status_code=429)

    return await call_next(request)

