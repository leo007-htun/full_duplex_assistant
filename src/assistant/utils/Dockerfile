FROM python:3.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENABLE_VOICE=0 \
    PYTHONPATH=/app/src

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc python3-dev \
    curl ca-certificates \
    libasound2 libasound2-dev portaudio19-dev \
    ffmpeg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libpangocairo-1.0-0 libgtk-3-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 🔑 Include python-multipart for FastAPI file uploads
RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    "uvicorn[standard]==0.23.2" \
    pydantic==2.6.4 \
    jinja2==3.1.3 \
    websockets==10.4 \
    numpy==1.24.4 \
    sounddevice==0.4.6 \
    pyaudio==0.2.13 \
    playwright==1.40.0 \
    openai==1.97.0 \
    python-multipart==0.0.9 \
    "httpx<0.28"

# (Large) browser deps for Playwright
RUN python -m playwright install --with-deps

COPY . .

EXPOSE 8000

# Using python -m uvicorn is a bit more robust w.r.t. PATH
CMD ["python", "-m", "uvicorn", "assistant.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
