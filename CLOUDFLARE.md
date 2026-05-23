# Деплой сервиса с Cloudflare Tunnel

## Контекст

Сервис запущен на DigitalOcean (164.90.202.152). Некоторые провайдеры (Timeweb, cloud.ru) имеют плохой пиринг с DigitalOcean — ответные пакеты теряются. Cloudflare Tunnel решает эту проблему: дроплет сам устанавливает исходящее соединение к Cloudflare, и трафик идёт через их сеть.

Схема:
```
Клиент → Cloudflare → Дроплет (Docker) → Anthropic API
```

---

## Как работает проксирование

### Проблема без Cloudflare

Без туннеля трафик шёл напрямую:
```
Клиент (Timeweb) ──запрос──▶ Дроплет (DigitalOcean)
Клиент (Timeweb) ◀──ответ── Дроплет (DigitalOcean)  ✗ пакеты теряются
```
Запрос доходил, но ответные пакеты терялись из-за плохого пиринга между DigitalOcean и Timeweb на уровне сетевого оборудования провайдеров. Это не решается настройками на машинах.

### Решение с Cloudflare Tunnel

```
Клиент (Timeweb)
  │  HTTPS запрос на api.fieldlog.online
  ▼
Серверы Cloudflare (Амстердам)
  │  запрос передаётся по туннелю
  ▼
cloudflared (процесс на дроплете)
  │  перенаправляет на localhost:8000
  ▼
Docker контейнер (FastAPI, порт 8000)
  │  вызов Anthropic API
  ▼
Anthropic API → ответ идёт обратно по той же цепочке
```

**Ключевой момент:** дроплет сам инициирует исходящее соединение к Cloudflare при старте `cloudflared`. Это постоянный туннель, по которому Cloudflare передаёт входящие запросы дроплету. Дроплету не нужно отправлять пакеты напрямую клиенту — ответ возвращается через тот же туннель обратно к Cloudflare, а Cloudflare уже доставляет его клиенту. У Cloudflare хорошая связность со всеми провайдерами, поэтому проблема пиринга исчезает.

### Как `service: http://localhost:8000` связывается с Docker

В конфиге туннеля:
```yaml
ingress:
  - hostname: api.fieldlog.online
    service: http://localhost:8000
```

Эта строка говорит cloudflared: входящий запрос на `api.fieldlog.online` перенаправить на `localhost:8000` этой же машины.

В `docker-compose.yml` прописан проброс порта:
```yaml
ports:
  - "8000:8000"
```

Это значит: порт `8000` внутри контейнера примаплен на порт `8000` хост-машины (дроплета). Поэтому `localhost:8000` на дроплете — это и есть FastAPI внутри Docker-контейнера.

### Почему HTTPS снаружи, но HTTP внутри

Cloudflare терминирует SSL — принимает HTTPS от клиента, расшифровывает, и передаёт дроплету уже по HTTP через туннель. Это нормально: туннель сам по себе зашифрован, открытый HTTP между cloudflared и контейнером не выходит за пределы машины.

### Как клиент находит сервис: роль DNS

Когда клиент делает запрос на `https://api.fieldlog.online`, он сначала спрашивает DNS: "какой IP у этого адреса?". Отвечают DNS-серверы Cloudflare (потому что мы переключили nameserver-а домена на Cloudflare). Они возвращают **свой собственный IP**, а не IP дроплета.

```
Клиент: "кто такой api.fieldlog.online?"
    │
    ▼
Cloudflare DNS: "это наш IP — 104.21.x.x"
    │
    ▼
Клиент идёт на 104.21.x.x (серверы Cloudflare)
    │
    ▼
Cloudflare передаёт запрос дроплету через туннель
```

Дроплет не светит своим IP наружу — клиент никогда не узнает реальный адрес `164.90.202.152`.

Когда мы выполнили команду:
```bash
cloudflared tunnel route dns claude-service api.fieldlog.online
```

Cloudflare создал не A-запись с IP дроплета, а **CNAME-запись** на адрес туннеля:
```
api.fieldlog.online → dabc8dd6-09ca-4159-937f-b91af6f9445f.cfargotunnel.com
```

Проверить можно командой:
```bash
dig api.fieldlog.online
```

В ответе будет IP Cloudflare, а не `164.90.202.152`.

---

## 1. Подготовка домена

1. Зарегистрировать домен (в нашем случае `fieldlog.online` на reg.ru)
2. Создать аккаунт на [cloudflare.com](https://cloudflare.com)
3. В панели Cloudflare: **Add a Site** → ввести домен → выбрать бесплатный план
4. Cloudflare покажет два nameserver-а, например:
   ```
   rocky.ns.cloudflare.com
   sydney.ns.cloudflare.com
   ```
5. На reg.ru: Домены → `fieldlog.online` → DNS-серверы → заменить на nameserver-а Cloudflare
6. Подождать 10–30 минут. Cloudflare пришлёт письмо когда домен активируется.

---

## 2. Запуск сервиса на дроплете

Подключиться к дроплету:
```bash
ssh root@164.90.202.152
```

Клонировать репозиторий:
```bash
git clone <repo-url> claude_api_service
cd claude_api_service
```

Создать файл `.env`:
```bash
nano .env
```
Содержимое:
```
CLAUDE_API_KEY=<ваш ключ>
CLAUDE_MODEL=claude-sonnet-4-6
```

Запустить сервис:
```bash
docker compose up -d
```

Проверить что сервис работает:
```bash
docker compose ps
docker compose logs -f -t
```

Проверить локально:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "привет"}'
```

---

## 3. Установка cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

---

## 4. Авторизация в Cloudflare

```bash
cloudflared login
```

Команда выдаст ссылку — открыть в браузере, авторизоваться в Cloudflare, выбрать домен `fieldlog.online`.

Сертификат сохранится в `/root/.cloudflared/cert.pem`.

---

## 5. Создание именованного туннеля

```bash
cloudflared tunnel create claude-service
```

Команда создаст файл с credentials, например:
```
/root/.cloudflared/dabc8dd6-09ca-4159-937f-b91af6f9445f.json
```

Запомнить ID туннеля (в нашем случае `dabc8dd6-09ca-4159-937f-b91af6f9445f`).

---

## 6. Создание конфига туннеля

```bash
printf 'tunnel: dabc8dd6-09ca-4159-937f-b91af6f9445f\ncredentials-file: /root/.cloudflared/dabc8dd6-09ca-4159-937f-b91af6f9445f.json\n\ningress:\n  - hostname: api.fieldlog.online\n    service: http://localhost:8000\n  - service: http_status:404\n' > ~/.cloudflared/config.yml
```

Проверить содержимое:
```bash
cat ~/.cloudflared/config.yml
```

Должно быть:
```yaml
tunnel: dabc8dd6-09ca-4159-937f-b91af6f9445f
credentials-file: /root/.cloudflared/dabc8dd6-09ca-4159-937f-b91af6f9445f.json

ingress:
  - hostname: api.fieldlog.online
    service: http://localhost:8000
  - service: http_status:404
```

---

## 7. Создание DNS-записи

```bash
cloudflared tunnel route dns claude-service api.fieldlog.online
```

Команда создаст CNAME-запись `api.fieldlog.online` в Cloudflare DNS, указывающую на туннель.

---

## 8. Запуск туннеля как системного сервиса

```bash
cloudflared service install
systemctl start cloudflared
systemctl status cloudflared
```

Сервис запускается автоматически при перезагрузке дроплета.

---

## 9. Проверка

С любой машины:
```bash
curl -X POST https://api.fieldlog.online/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "привет"}'
```

---

## Управление сервисами на дроплете

```bash
# Логи сервиса (с временными метками)
docker compose logs -f -t

# Перезапуск Docker-сервиса
docker compose restart

# Статус Cloudflare Tunnel
systemctl status cloudflared

# Перезапуск туннеля
systemctl restart cloudflared
```
