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

## 3. Опционально / на будущее

- [ ] Передавать `source` в запросе (чтобы различать generate_questions / evaluate_answer / generate_vacancy_advice в логах)
- [ ] Отдельный эндпоинт `GET /stats` — JSON со статистикой для дашборда
- [ ] Rate limiting по IP или по ключу (slowapi)
- [ ] Ротация API-ключа без перезапуска (читать из env динамически)
- [ ] Алерт не должен дублироваться при каждом запросе после превышения бюджета (cooldown или флаг)