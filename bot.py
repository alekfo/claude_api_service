import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BotCommand, Message
from dotenv import load_dotenv

import db

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PRICES = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
}
DEFAULT_PRICE = {"input": 3.0, "output": 15.0}

DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "100000"))
MONTHLY_TOKEN_BUDGET = int(os.getenv("MONTHLY_TOKEN_BUDGET", "2000000"))


def calc_cost(input_tokens: int, output_tokens: int, model: str = "claude-sonnet-4-6") -> float:
    price = PRICES.get(model, DEFAULT_PRICE)
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


dp = Dispatcher()


@dp.message(Command("today"))
async def cmd_today(message: Message):
    s = db.get_today_stats()
    cost = calc_cost(s["input_tokens"], s["output_tokens"])
    await message.answer(
        f"📊 <b>Сегодня</b>\n\n"
        f"Запросов: {s['requests']}\n"
        f"Токены: {s['total_tokens']:,} (in: {s['input_tokens']:,} / out: {s['output_tokens']:,})\n"
        f"Стоимость: ${cost:.4f}\n"
        f"Среднее время: {s['avg_elapsed']:.1f}с",
        parse_mode="HTML",
    )


@dp.message(Command("month"))
async def cmd_month(message: Message):
    s = db.get_month_stats()
    cost = calc_cost(s["input_tokens"], s["output_tokens"])
    await message.answer(
        f"📅 <b>Текущий месяц</b>\n\n"
        f"Запросов: {s['requests']}\n"
        f"Токены: {s['total_tokens']:,} (in: {s['input_tokens']:,} / out: {s['output_tokens']:,})\n"
        f"Стоимость: ${cost:.4f}\n"
        f"Среднее время: {s['avg_elapsed']:.1f}с",
        parse_mode="HTML",
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    rows = db.get_recent_requests(10)
    if not rows:
        await message.answer("Записей нет.")
        return
    lines = ["📋 <b>Последние 10 запросов</b>\n"]
    for r in rows:
        preview = (r["prompt_preview"] or "")[:40]
        lines.append(
            f"<code>{r['created_at'][:16]}</code> | "
            f"{r['total_tokens']:,} tok | {r['elapsed_seconds']:.1f}с | "
            f"{r['stop_reason']} | {preview}…"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("budget"))
async def cmd_budget(message: Message):
    today = db.get_today_total_tokens()
    month = db.get_month_total_tokens()
    today_pct = today / DAILY_TOKEN_BUDGET * 100 if DAILY_TOKEN_BUDGET else 0
    month_pct = month / MONTHLY_TOKEN_BUDGET * 100 if MONTHLY_TOKEN_BUDGET else 0
    await message.answer(
        f"💰 <b>Бюджет токенов</b>\n\n"
        f"Сегодня: {today:,} / {DAILY_TOKEN_BUDGET:,} ({today_pct:.1f}%)\n"
        f"Месяц:   {month:,} / {MONTHLY_TOKEN_BUDGET:,} ({month_pct:.1f}%)",
        parse_mode="HTML",
    )


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    db.init_db()
    bot = Bot(token=token)
    await bot.set_my_commands([
        BotCommand(command="today", description="Запросы и расход за сегодня"),
        BotCommand(command="month", description="Сводка за текущий месяц"),
        BotCommand(command="stats", description="Последние 10 запросов"),
        BotCommand(command="budget", description="Расход токенов vs бюджет"),
    ])
    logger.info("Bot started, polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())