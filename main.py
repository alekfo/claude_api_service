import json
import logging
import os
import time
import urllib.request

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

import db

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

api_key_header = APIKeyHeader(name="X-API-Key")

DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "100000"))
MONTHLY_TOKEN_BUDGET = int(os.getenv("MONTHLY_TOKEN_BUDGET", "2000000"))

db.init_db()


class PromptRequest(BaseModel):
    prompt: str


def send_telegram_alert(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("Failed to send Telegram alert: %s", e)


@app.post("/ask")
def ask(request: PromptRequest, api_key: str = Security(api_key_header)):
    if api_key != os.getenv("SERVICE_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")

    t0 = time.monotonic()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": request.prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API error: %s", e)
        send_telegram_alert(f"🔴 Ошибка Anthropic API: {e}")
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e}")

    elapsed = time.monotonic() - t0
    stop_reason = message.stop_reason
    usage = message.usage

    logger.info(
        "Claude response: stop_reason=%s input_tokens=%d output_tokens=%d elapsed=%.1fs",
        stop_reason, usage.input_tokens, usage.output_tokens, elapsed,
    )

    if stop_reason == "max_tokens":
        logger.warning("Response truncated at max_tokens — consider increasing limit")
        send_telegram_alert("⚠️ Ответ Claude был обрезан (max_tokens). Рассмотрите увеличение лимита.")

    if not message.content or message.content[0].type != "text":
        logger.error("Unexpected response content: %s", message.content)
        raise HTTPException(status_code=502, detail="Empty or unexpected response from Claude")

    text = message.content[0].text
    if not text.strip():
        logger.error("Claude returned empty text (stop_reason=%s)", stop_reason)
        raise HTTPException(status_code=502, detail="Empty response from Claude")

    db.log_request(model, usage.input_tokens, usage.output_tokens, elapsed, stop_reason, request.prompt)

    today_tokens = db.get_today_total_tokens()
    if today_tokens > DAILY_TOKEN_BUDGET:
        send_telegram_alert(
            f"⚠️ Дневной лимит токенов превышен: {today_tokens:,} / {DAILY_TOKEN_BUDGET:,}"
        )

    month_tokens = db.get_month_total_tokens()
    if month_tokens > MONTHLY_TOKEN_BUDGET:
        send_telegram_alert(
            f"⚠️ Месячный лимит токенов превышен: {month_tokens:,} / {MONTHLY_TOKEN_BUDGET:,}"
        )

    return {"response": text}