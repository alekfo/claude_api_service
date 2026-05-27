import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

load_dotenv()

app = FastAPI()
client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

api_key_header = APIKeyHeader(name="X-API-Key")


class PromptRequest(BaseModel):
    prompt: str


@app.post("/ask")
def ask(request: PromptRequest, api_key: str = Security(api_key_header)):
    if api_key != os.getenv("SERVICE_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return {"response": message.content[0].text}