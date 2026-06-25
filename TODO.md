# TODO — claude_api_service

## 1. Критические баги — ВЫПОЛНЕНО ✅

### 1.1 Увеличить max_tokens ✅
`max_tokens` поднят до `4096`. При обрезке (`stop_reason == "max_tokens"`) отправляется Telegram-алерт.

### 1.2 Обработка ошибок и логирование ✅
- `try/except anthropic.APIError` → HTTP 502 + лог + Telegram-алерт
- Валидация `message.content` перед `[0].text`
- Логирование `stop_reason`, токенов, времени в консоль

---

## 2. Мониторинг через Telegram-бот — ВЫПОЛНЕНО ✅

- **db.py** — SQLite, таблица `request_log`, хелперы для статистики
- **bot.py** — aiogram 3.x, команды `/today` `/month` `/stats` `/budget`
- **main.py** — запись в БД после каждого запроса, алерты через urllib
- **docker-compose.yml** — сервис `tg-bot`, shared volume `./data`

**Алерты реализованы:**
- Ошибка Anthropic API
- `stop_reason == "max_tokens"`
- Превышение `DAILY_TOKEN_BUDGET`
- Превышение `MONTHLY_TOKEN_BUDGET`

---

## 3. Известные проблемы — требуют исправления

### 3.1 ✅ Таймаут на вызов Anthropic SDK — ВЫПОЛНЕНО
Anthropic-клиент использовал дефолтный таймаут (600 сек). Это приводило к зависшим соединениям
и реальному 504 на продакшне (24.06.2026).

**Решение:** таймаут API-сервиса (85s) меньше таймаута PrepMate (90s) — сервис успевает
вернуть 502 до того как PrepMate сам отвалится по ReadTimeout.
- PrepMate `interviews/services.py`: `timeout=90`
- API-сервис `main.py`: `httpx.Timeout(85.0)`

### 3.2 🔴 Блокирующий Telegram-алерт в async-обработчике
`send_telegram_alert()` использует `urllib.request.urlopen()` — синхронный вызов с `timeout=5`.
В FastAPI это блокирует event loop при каждой ошибке или превышении бюджета.

**Исправление:** вынести в thread pool:
```python
import asyncio
async def send_telegram_alert_async(text: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send_telegram_alert, text)
```

### 3.3 🟡 Спам алертами при превышении бюджета
После превышения лимита каждый следующий запрос (evaluate_answer — 8 штук за сессию)
отправляет отдельный Telegram-алерт. За одну сессию PrepMate может прийти 8+ одинаковых сообщений.

**Исправление:** добавить cooldown-флаг в памяти или через SQLite:
```python
_budget_alert_sent: dict[str, float] = {}  # {"daily": timestamp, "monthly": timestamp}
ALERT_COOLDOWN = 3600  # 1 час
```

### 3.4 🟡 Порт 8000 потенциально открыт публично
В `docker-compose.yml` порт слушает на `0.0.0.0:8000`. Если фаервол сервера не закрывает
этот порт — сервис доступен напрямую в обход Cloudflare Tunnel.

**Исправление:** привязать только к localhost:
```yaml
ports:
  - "127.0.0.1:8000:8000"
```

### 3.5 🟡 SQLite при конкурентных запросах
PrepMate запускает 2 gunicorn-воркера с 20 gevent-соединениями каждый. При одновременных
запросах к API-сервису SQLite может бросать `database is locked` при записи в `request_log`.
Пока нагрузка низкая — некритично; при росте пользователей заменить на PostgreSQL или
добавить WAL-режим (`PRAGMA journal_mode=WAL`).

### 3.6 🟡 Нет `/health` эндпоинта
`docker-compose.yml` не имеет `healthcheck`. При зависании сервиса PrepMate узнаёт об этом
только по таймауту запроса.

**Исправление:**
```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

И в `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 5s
  retries: 3
```

### 3.7 🟢 Нет поля `source` в логах
В `request_log` пишется только `prompt_preview` (100 символов). Непонятно, какая функция
PrepMate сделала запрос — `generate_questions`, `evaluate_answer` или `generate_vacancy_advice`.
Мешает анализу стоимости по типам запросов.

**Исправление:** PrepMate добавляет `source` в тело запроса:
```python
requests.post(url, json={"prompt": ..., "source": "evaluate_answer"})
```
Сервис принимает и логирует в БД.

### 3.8 🟢 Цены в `bot.py` захардкожены
```python
PRICES = {"claude-sonnet-4-6": {"input": 3.0, "output": 15.0}}
```
При смене модели нужно обновлять вручную — легко забыть.

---

## 4. Опционально / на будущее

- [ ] Отдельный эндпоинт `GET /stats` — JSON со статистикой для дашборда
- [ ] Rate limiting по IP или по ключу (slowapi)
- [ ] Ротация API-ключа без перезапуска (читать из env динамически)