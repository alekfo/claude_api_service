import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

app = FastAPI()
client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


class PromptRequest(BaseModel):
    prompt: str


@app.post("/ask")
def ask(request: PromptRequest):
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return {"response": message.content[0].text}