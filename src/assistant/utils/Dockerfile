# ---- Base: Python 3.8 (required by your env) ----
FROM python:3.8-slim

# System env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENABLE_VOICE=0

# ---- System dependencies (audio, build tools, playwright deps) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc python3-dev \
    curl ca-certificates \
    libasound2 libasound2-dev portaudio19-dev \
    ffmpeg \
    # Playwright/Chromium common runtime libs (remove if not scraping)
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libpangocairo-1.0-0 libgtk-3-0 \
  && rm -rf /var/lib/apt/lists/*

# ---- Workdir ----
WORKDIR /app

# ---- Install Python deps (pins compatible with Python 3.8) ----
# Note: keep httpx<0.28; use a recent OpenAI client (you had 1.97.0 locally)
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
    "httpx<0.28"

# Download Playwright browsers (remove if not scraping)
RUN python -m playwright install --with-deps

# ---- Copy project source ----
COPY . .

# ---- Port & default command ----
EXPOSE 8000

# Use --app-dir so Python can import from ./src
# If your package is bpmn_assistant, change the target accordingly.
CMD ["python", "-m", "uvicorn", "assistant.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
