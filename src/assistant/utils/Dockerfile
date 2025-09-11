# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build deps only if needed; this is minimal for FastAPI+httpx+uvicorn+openai
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use a requirements file for layer caching; pin minimal versions
COPY src/assistant/utils/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY src ./src

EXPOSE 8000
CMD ["uvicorn", "assistant.app:app", "--host", "0.0.0.0", "--port", "8000"]
