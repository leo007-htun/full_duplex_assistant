import httpx
import json
from typing import Optional

class Client:
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None, timeout: int = 60):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def responses(self, model: str, input: str, session_id: Optional[str] = None, metadata: Optional[dict] = None):
        url = f"{self.base}/v1/responses"
        payload = {"model": model, "input": input, "session_id": session_id, "metadata": metadata}
        r = httpx.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
