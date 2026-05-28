# claude_api_service — CLAUDE.md

HTTP-прокси между PrepMate и Anthropic API. Принимает промпты, отправляет в Claude, возвращает текстовый ответ. Логирует каждый запрос в SQLite, отправляет алерты через Telegram-бот.

## Стек

- **Python 3.12**, **FastAPI**, **uvicorn**
- **anthropic** — официальный SDK для Anthropic API
- **aiogram 3.x** — Telegram-бот
- **python-dotenv** — переменные окружения из `.env`
- **SQLite** (stdlib) — лог запросов
- Docker Compose для запуска на сервере

## Структура проекта

```
main.py            — FastAPI app (эндпоинт /ask, алерты в Telegram)
db.py              — инициализация SQLite + хелперы для статистики
bot.py             — Telegram-бот (команды /today /month /stats /budget)
requirements.txt   — зависимости
Dockerfile         — образ на python:3.12-slim
docker-compose.yml — два сервиса: api + tg-bot, shared volume ./data
.env               — переменные окружения (не в git)
data/logs.db       — SQLite БД (создаётся автоматически, не в git)
CLOUDFLARE.md      — заметки по настройке Cloudflare (если используется)
```

## API

### `POST /ask`

**Заголовки:** `X-API-Key: <SERVICE_API_KEY>`

**Тело запроса:**
```json
{"prompt": "текст промпта"}
```

**Ответ:**
```json
{"response": "текст ответа от Claude"}
```

**Ошибки:**
- `403 Forbidden` — неверный API-ключ
- `502 Bad Gateway` — ошибка Anthropic API или пустой ответ

## Переменные окружения (.env)

```
CLAUDE_API_KEY=...                   # ключ Anthropic API
SERVICE_API_KEY=...                  # ключ авторизации для входящих запросов
CLAUDE_MODEL=claude-sonnet-4-6       # модель по умолчанию

TELEGRAM_BOT_TOKEN=...               # токен бота от @BotFather
TELEGRAM_CHAT_ID=...                 # твой chat_id для алертов
DAILY_TOKEN_BUDGET=100000            # алерт при превышении дневного лимита
MONTHLY_TOKEN_BUDGET=2000000         # алерт при превышении месячного лимита
DB_PATH=/app/data/logs.db            # путь к SQLite (внутри Docker)
```

## Текущие параметры вызова Claude

```python
client.messages.create(
    model=model,
    max_tokens=4096,
    messages=[{"role": "user", "content": request.prompt}],
)
```

Возвращается `message.content[0].text`.

## Флоу обработки запроса

1. Проверка `X-API-Key` → 403 если неверный
2. Вызов Anthropic API → при ошибке: лог + Telegram-алерт + HTTP 502
3. Логирование `stop_reason`, токенов, времени в консоль
4. Если `stop_reason == "max_tokens"` → Telegram-алерт об обрезке
5. Валидация `content[0].text` → 502 если пусто
6. Запись в `request_log` (SQLite)
7. Проверка дневного/месячного бюджета → Telegram-алерт при превышении
8. Возврат `{"response": text}` — происходит всегда при успешном ответе Claude

## Telegram-бот (bot.py)

Отдельный Docker-сервис, читает из той же SQLite БД.

**Команды:**
- `/today` — запросы, токены, стоимость за сегодня
- `/month` — сводка за текущий месяц
- `/stats` — последние 10 запросов
- `/budget` — расход токенов vs дневной/месячный лимит (%)

**Алерты (из main.py, через urllib):**
- Ошибка Anthropic API
- `stop_reason == "max_tokens"` — ответ обрезан
- Превышение `DAILY_TOKEN_BUDGET`
- Превышение `MONTHLY_TOKEN_BUDGET`

## SQLite — таблица request_log

```sql
CREATE TABLE request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    elapsed_seconds REAL,
    stop_reason TEXT,
    prompt_preview TEXT   -- первые 100 символов промпта
);
```

База данных на сервере: `<папка с docker-compose.yml>/data/logs.db`

## Запуск (dev)

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# бот отдельно:
python bot.py
```

## Запуск (прод)

```bash
docker compose up -d
```