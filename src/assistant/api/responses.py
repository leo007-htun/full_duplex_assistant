from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1", tags=["responses"])

class ResponsesRequest(BaseModel):
    model: str
    input: Optional[str] = None
    session_id: Optional[str] = None
    stream: Optional[bool] = False
    metadata: Optional[dict] = None

# Replace this with your real orchestrator call
async def _orchestrate_sync(model: str, text: str, session_id: Optional[str]):
    # for now echo back; swap with your LLM orchestration call
    return {"object": "response", "model": model, "input": text, "output": f"Echo: {text}"}

@router.post("/responses")
async def create_response(req: ResponsesRequest, request: Request):
    try:
        # optionally check auth here (e.g., API key)
        result = await _orchestrate_sync(req.model, req.input or "", req.session_id)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
