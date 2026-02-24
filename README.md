### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Telegram Bot token ([@BotFather](https://t.me/BotFather))
- for user token ([@userinfobot])

### 2. Clone and install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database

Create a PostgreSQL user with password, create the database, grant permissions, and run the schema. Run these as the system `postgres` user (use `sudo -u postgres` if you get "role ... does not exist"):

```bash
# 1. Open PostgreSQL as superuser (postgres)
sudo -u postgres psql

CREATE USER divergence_app WITH PASSWORD 'your_secure_password';
CREATE DATABASE divergence OWNER divergence_app;
\c divergence
GRANT ALL PRIVILEGES ON DATABASE divergence TO divergence_app;
GRANT ALL ON SCHEMA public TO divergence_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO divergence_app;
\q

# 3. Apply the schema (as postgres; it creates tables in divergence)
sudo -u postgres psql -d divergence -f sql/schema.sql

# 4. Grant table and sequence permissions (sequences need UPDATE for SERIAL/nextval)
sudo -u postgres psql -d divergence -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO divergence_app; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO divergence_app;"
```

Then set `DATABASE_URL` in `.env` (use the same password you set above):

```
DATABASE_URL=postgresql://divergence_app:your_secure_password@localhost:5432/divergence
```

### 4. Environment

```bash
cp .env.example .env
# Edit .env: set DATABASE_URL and TELEGRAM_BOT_TOKEN
```

### 5. Config (optional)

Edit `config/config.yaml` to change:

- `polling.interval_minutes` (default 10)
- `polling.z_score_window` (default 24)
- `defaults.open_threshold`, `close_threshold`, `cooldown_minutes`
- `series_a` / `series_b`: `url`, `params`, `value_path` (JSON path to the numeric value)

Default demo uses CoinGecko (Bitcoin price = “belief”, Ethereum price = “price”) so the service runs without API keys. Replace with your own “belief-like” and price APIs as needed.

### 6. Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs  
- Health: http://localhost:8000/api/health  

### 7. Register users and get alerts

- **Register a user** (so they receive Telegram alerts):

  ```bash
  curl -X POST http://localhost:8000/api/users/register \
    -H "Content-Type: application/json" \
    -d '{"telegram_id": 8630483102, "username": "@testuser9870"}'
  ```

- **Optional – set custom thresholds** for a user (use `user_id` from register response):

  ```bash
  curl -X PATCH "http://localhost:8000/api/users/1/thresholds" \
    -H "Content-Type: application/json" \
    -d '{"open_threshold": 2.5, "close_threshold": 0.5, "cooldown_minutes": 90}'
  ```

Users must have **started** the bot (or received a message from the bot first) for Telegram to allow sending them messages.

## SQL schema

See `sql/schema.sql`. Summary:

| Table            | Purpose                                      |
|------------------|----------------------------------------------|
| `users`          | Telegram users (telegram_id, username)        |
| `user_thresholds`| Per-user open/close thresholds, cooldown     |
| `snapshots`      | Raw values + change + z-score per series     |
| `divergence_scores` | Computed score each poll                  |
| `alerts`         | Alert lifecycle (OPEN/UPDATE/CLOSED)         |
| `alert_events`   | Audit log of status changes                  |

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (DB + config) |
| POST | `/api/users/register` | Register user (body: `telegram_id`, optional `username`) |
| PATCH | `/api/users/{user_id}/thresholds` | Update open/close/cooldown (body: optional floats and cooldown_minutes) |

## Edge cases

- **Insufficient history**: No divergence is computed until there are enough snapshots for both series (z-score window); no alert is sent.
- **API errors**: Poll cycle logs the error and skips that cycle; no alert.
- **Missing Telegram token**: Alerts are not sent; a warning is logged.
- **Cooldown**: New OPEN is not created until `cooldown_until` has passed for that user.

## Demo / live demo

1. Apply the SQL schema and set `DATABASE_URL` and `TELEGRAM_BOT_TOKEN` in `.env`.
2. Run: `./run.sh` or `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
3. Open http://localhost:8000/docs and call `POST /api/users/register` with your Telegram ID (e.g. from [@userinfobot](https://t.me/userinfobot)).
4. Start your bot in Telegram (or send it a message so it can message you).
5. Wait for poll cycles (default every 10 minutes) or set `polling.interval_minutes: 1` in `config/config.yaml` for a quick test. When divergence crosses your thresholds, you receive OPEN/UPDATE/CLOSED messages.

For a **recorded demo**: run the service, show `/api/health`, register a user, and (optionally) trigger one poll by temporarily reducing the interval or waiting one cycle.

## License

MIT.
