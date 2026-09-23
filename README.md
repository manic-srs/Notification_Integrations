# Notification Integration

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1)

A Notification Management Application that lets a user send a message
across **Teams, Email and Slack** from one form, tracks delivery status
per channel, retries failures, and accepts delivery-confirmation
callbacks via a webhook.

Built to the "Notification Management Application (Teams • Email • Slack)"
spec: FastAPI + MySQL (no ORM — raw SQL via PyMySQL), with a provider-adapter
layer so the service never talks to a vendor SDK directly.

## Table of contents

- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Getting the code](#getting-the-code)
- [Running it with Docker](#running-it-with-docker-recommended-for-a-quick-demo)
- [Running the backend without Docker](#running-the-backend-without-docker)
- [Database setup](#database--mysql-only-no-orm)
- [Provider credentials](#provider-credentials-all-optional--mock-is-the-default)
- [Trying it out via the API directly](#trying-it-out-via-the-api-directly)
- [API summary](#api-summary)
- [Design notes](#design-notes)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Architecture

```
Client (frontend / API caller)  --fetch-->  FastAPI API layer  -->  Notification Service
                                                                          |
                                                          +---------------+---------------+
                                                          |               |               |
                                                    Teams Provider   Slack Provider  Email Provider
                                                    (Power Automate)  (Slack SDK)     (SMTP)
                                                          |               |               |
                                                          +-------- MockProvider --------+
                                                             (auto fallback when a
                                                              channel's credentials
                                                              aren't configured)

                                         Repository / Database Layer (raw SQL, PyMySQL)
                                                          |
                                                        MySQL
```

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (ASGI) |
| Database | MySQL 8.0, accessed via raw SQL over [PyMySQL](https://pymysql.readthedocs.io/) — no ORM |
| Validation | [Pydantic](https://docs.pydantic.dev/) v2 / `pydantic-settings` |
| Integrations | Microsoft Teams (Power Automate webhook), Slack (`slack_sdk`), Email (SMTP) |
| Testing | `pytest` against a real MySQL schema |
| Containerization | Docker + Docker Compose |

## Project layout

```
Notification_Integration/
├── docker-compose.yml            # one-command stack: MySQL + Backend + Frontend
├── Backend/
│   ├── main.py                  # FastAPI entrypoint (CORS, DB init, router)
│   ├── requirements.txt
│   ├── .env.example             # copy to .env and fill in real credentials
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── schema.sql                # raw MySQL DDL - the single source of truth for the schema
│   ├── app/
│   │   ├── config.py             # Settings (env-driven)
│   │   ├── db.py                 # PyMySQL connection management (no ORM)
│   │   ├── security.py           # webhook secret comparison, redaction
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── models/                # plain dataclasses (Notification, NotificationDelivery)
│   │   ├── repositories/          # the only place raw SQL is written
│   │   ├── providers/             # Teams / Slack / Email adapters + Mock + factory
│   │   ├── services/               # NotificationService, retry policy
│   │   ├── webhooks/                # provider callback normalization
│   │   └── api/                     # FastAPI routes
│   └── tests/                        # pytest suite (offline, MockProvider only)
└── Frontend/
    ├── Dockerfile                    # static HTML/CSS/JS served by nginx, no build step
    ├── Login.html                    # sign-in screen (client-side only, no backend call)
    ├── Dashboard.html                # stats + recent notifications
    ├── Notification.html             # send-notification form
    ├── History.html                  # search/filter notification history
    ├── config.js                     # API_BASE_URL
    ├── common.js                     # shared fetch helpers used by Dashboard/Notification
    ├── send-notification.js          # Notification.html's form logic
    └── *.css                          # per-page styles + shared styles.css
```

## Prerequisites

| Tool | macOS | Windows |
|---|---|---|
| Python 3.11+ | `brew install python@3.11`, or the [python.org](https://www.python.org/downloads/) installer | [python.org](https://www.python.org/downloads/) installer — check **"Add python.exe to PATH"** during setup |
| MySQL 8.0 | `brew install mysql` | [MySQL Installer for Windows](https://dev.mysql.com/downloads/installer/), or `choco install mysql` |
| Docker Desktop *(optional — only needed for the Docker quick start)* | [docker.com](https://www.docker.com/products/docker-desktop/) | [docker.com](https://www.docker.com/products/docker-desktop/), with the WSL2 backend enabled |
| Git | `brew install git` (or Xcode Command Line Tools) | [git-scm.com](https://git-scm.com/download/win) — this also installs Git Bash |

Windows commands below are written for **PowerShell**. If you're using Git Bash
instead, the macOS/Linux commands work as-is.

## Getting the code

```bash
git clone https://github.com/manic-srs/Notification_Integrations.git
cd Notification_Integrations
```

## Running it with Docker (recommended for a quick demo)

Identical on both platforms once Docker Desktop is running — just start it
from your terminal of choice.

**macOS / Linux (bash):**
```bash
cp Backend/.env.example Backend/.env   # edit with real credentials, or leave blank for Mock
docker compose up --build
```

**Windows (PowerShell):**
```powershell
Copy-Item Backend\.env.example Backend\.env   # edit with real credentials, or leave blank for Mock
docker compose up --build
```

Starts MySQL + the backend together, in one command:

- Backend docs: `http://localhost:8000/docs`

This MySQL is a fresh, empty database living in its own Docker volume,
separate from any MySQL you run natively — no local MySQL install needed.
`Backend/.env`'s `MYSQL_*` values are ignored under Docker (the compose file
always points the backend at its own `mysql` service instead); everything
else in that file — Teams/Slack/SMTP credentials, retry settings, webhook
secret — is used exactly as it would be running natively. The backend
container bind-mounts `Backend/`, so editing the code on your machine still
hot-reloads it, same as `uvicorn --reload`.

If port 8000 is already taken by something else on your machine, override it
without editing the compose file — create a `.env` file next to
`docker-compose.yml` (not `Backend/.env`) with:
```
BACKEND_PORT=8001
```
and the backend docs will be at `http://localhost:8001/docs` instead. See
`docker-compose.yml` for details, including how to override the MySQL root
password the same way.

Stop everything with `docker compose down` (add `-v` to also delete the
MySQL data volume and start fresh next time).

## Running the backend (without Docker)

### macOS

```bash
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit with real credentials, or leave blank for Mock

uvicorn main:app --reload --port 8000
```

Install and start MySQL:
```bash
brew install mysql
brew services start mysql
```

### Windows (PowerShell)

```powershell
cd Backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env    # edit with real credentials, or leave blank for Mock

uvicorn main:app --reload --port 8000
```

Notes for Windows:
- If PowerShell refuses to run the activation script (*"running scripts is
  disabled on this system"*), run
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that
  terminal, then re-run `.venv\Scripts\Activate.ps1`.
- Using Command Prompt instead of PowerShell? Activate with
  `.venv\Scripts\activate.bat`.
- Install MySQL with the [MySQL Installer](https://dev.mysql.com/downloads/installer/)
  (it also registers and starts MySQL as a Windows service automatically), or
  via Chocolatey: `choco install mysql` then `net start mysql`.

Either way, this requires a MySQL server to already be running — on startup
the app connects via PyMySQL and creates its tables automatically if they
don't exist yet (raw `CREATE TABLE IF NOT EXISTS`, no migration tool). Visit
`http://localhost:8000/docs` for interactive Swagger docs.

### Database — MySQL only, no ORM

There is no SQLite fallback and no SQLAlchemy: every read and write goes
through raw SQL in `app/repositories/notification_repository.py`, executed
via PyMySQL (`app/db.py`). A running MySQL server is required (installed
above for your platform).

1. Confirm MySQL is running:
   - macOS: `brew services list` should show `mysql` as `started`.
   - Windows: `Get-Service MySQL80` (or open **Services** and check
     "MySQL80" is *Running*) — the MySQL Installer starts this automatically.
2. Create the database (same command on both platforms, using the `mysql`
   client or MySQL Workbench):
   ```sql
   CREATE DATABASE IF NOT EXISTS notification_db CHARACTER SET utf8mb4;
   ```
   (or run `Backend/schema.sql` directly, which creates both the database and
   the two tables in one step — either way, the app will create the tables
   itself on first boot if they don't already exist).
3. Set these in `.env`:
   ```
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=your-password
   MYSQL_DATABASE=notification_db
   ```

### Provider credentials (all optional — Mock is the default)

Every channel falls back to `MockProvider` (always succeeds, no network call)
until its own credentials are set in `.env`, so the whole app runs with zero
external accounts configured, on either platform:

| Channel | Env vars | Notes |
|---|---|---|
| Teams | `TEAMS_WEBHOOK_URL` | Power Automate / Teams incoming webhook |
| Slack | `SLACK_BOT_TOKEN` | Bot token with `chat:write`, `im:write`, `users:read`, `users:read.email` |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER_EMAIL` | Any SMTP provider (Gmail example in `.env.example` — use an **App Password**, not your regular password, if 2FA is on) |

Set `FORCE_MOCK_PROVIDERS=true` to force every channel to Mock even if
credentials are present (handy for demos/CI). With real credentials set, the
startup log confirms each channel individually, e.g.:
```
Channel teams  -> real provider
Channel slack  -> real provider
Channel email  -> real provider
```

### Trying it out via the API directly

You can exercise the API without the frontend too, via the interactive
Swagger docs at `http://localhost:8000/docs`, or `curl`:

```bash
curl -X POST http://localhost:8000/api/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Deploy finished",
    "message": "Build #42 deployed to prod",
    "channels": {
      "teams": [{ "destination": "ops-channel" }],
      "slack": [{ "destination": "#engineering" }],
      "email": [{ "recipient": "team@example.com", "subject": "Deploy done" }]
    }
  }'
```

With no credentials configured, every channel sends through `MockProvider`
and returns a successful delivery status immediately.

## API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness check |
| POST | `/api/notifications` | create a notification and send it on every requested channel |
| GET | `/api/notifications` | list/search/filter (`channel`, `status`, `q`, `limit`, `offset`) |
| GET | `/api/notifications/{id}` | fetch one notification + its per-channel deliveries |
| POST | `/api/notifications/{id}/retry` | re-attempt every `FAILED` delivery, bounded by `RETRY_MAX_ATTEMPTS` |
| POST | `/api/webhooks/{provider}` | delivery-confirmation callback (`X-Webhook-Secret` header required); idempotent |
| GET | `/api/stats` | total/pending/delivered/failed counts (for a dashboard) |

CORS is controlled by `CORS_ORIGINS` in `.env` (`*` by default) — for
production use, point it at the frontend's actual origin instead of `*`.

## Design notes

- **Provider abstraction:** `NotificationProvider` (an ABC in
  `app/providers/base.py`) is the only interface the service layer knows
  about. `app/providers/factory.py` decides Teams/Slack/Email vs. Mock per
  channel based on whether that channel's credentials are configured — the
  service and API layers never change.
- **Independent per-channel status:** one `NotificationDelivery` row per
  (notification, channel, destination), so one channel failing never affects
  another.
- **Bounded retry with backoff:** `app/services/retry.py` retries only
  failures the adapter marks `retryable` (timeouts, 5xx, rate limits) with
  exponential backoff, up to `RETRY_MAX_ATTEMPTS`. Non-retryable failures
  (bad credentials, invalid destination) fail immediately.
- **Idempotent webhook:** `POST /api/webhooks/{provider}` is protected by a
  shared-secret header, ignores callbacks for unknown message ids without
  erroring, no-ops on a duplicate status, and never lets a stale `FAILED`
  callback overwrite an already-`DELIVERED` status.
- **Cross-notification threading:** repeated notifications sent to the same
  (channel, destination) pair land in one running conversation instead of as
  separate, unrelated messages. A `channel_threads` table (see
  `schema.sql`) stores one "anchor" per (channel, destination) — a Slack
  `thread_ts` or an Email `Message-ID` — the first time a message is sent
  there. Every later send to that same destination looks up the anchor
  first and passes it to the provider: Slack replies in-thread (`thread_ts`),
  Email sets `In-Reply-To`/`References` and prefixes the subject with "Re: ".
  Teams intentionally ignores this (see `app/providers/teams/provider.py`) —
  a Teams 1:1 chat is already one continuous conversation, so there is
  nothing to thread. The anchor is "first write wins": once saved for a
  destination it is never overwritten, so every later message threads off
  the original root.

## Tests

Tests run against a dedicated MySQL database (`notification_test_db`),
never the dev database — every test drops and recreates the tables
first. Create it once (same SQL on both platforms):

```sql
CREATE DATABASE IF NOT EXISTS notification_test_db CHARACTER SET utf8mb4;
```

Then run:

**macOS / Linux:**
```bash
cd Backend
source .venv/bin/activate
MYSQL_PASSWORD=your-password pytest -q
```

**Windows (PowerShell):**
```powershell
cd Backend
.venv\Scripts\Activate.ps1
$env:MYSQL_PASSWORD = "your-password"
pytest -q
```

(`MYSQL_HOST`/`MYSQL_PORT`/`MYSQL_USER` default to `127.0.0.1`/`3306`/`root` —
override the same way if yours differ.) `FORCE_MOCK_PROVIDERS=true` is set
automatically by the test suite, so no real Teams/Slack/SMTP credentials or
network access are needed — the tests cover the API
(create/list/filter/stats/404s), bounded retry/backoff behavior,
provider-factory fallback, webhook security/idempotency, and cross-notification
threading (`tests/test_threading.py`), all against a real MySQL schema.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pip install` fails with a permissions error | Make sure the virtual environment is activated (prompt should show `(.venv)`) before running `pip install`. |
| PowerShell: *"cannot be loaded because running scripts is disabled"* | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then retry activation. |
| `uvicorn` can't connect to MySQL | Confirm the MySQL service is running (`brew services list` on macOS, `Get-Service MySQL80` on Windows) and that `MYSQL_PASSWORD` in `.env` matches what you set during MySQL install. |
| Frontend gets CORS errors calling this API | Set `CORS_ORIGINS` in `Backend/.env` to the frontend's actual origin (or `*` for local development). |
| Docker: backend can't reach MySQL | Make sure `docker compose up` finished the MySQL healthcheck before the backend started (compose handles this via `depends_on: condition: service_healthy`) — check with `docker compose logs mysql`. |
| Docker: `Bind for 0.0.0.0:8000 failed: port is already allocated` | Something else on your machine already has port 8000 (check with `docker ps` or `lsof -i :8000`). Set `BACKEND_PORT=8001` (or any free port) in a `.env` file next to `docker-compose.yml` rather than fighting over 8000. |

## Contributing

1. Create a branch off `main`: `git checkout -b feature/your-change`.
2. Make your change, keeping the provider-abstraction pattern in
   `app/providers/` for any new channel, and raw SQL confined to
   `app/repositories/` for any new persistence.
3. Add or update tests under `Backend/tests/` — see [Tests](#tests) for how
   to run them locally.
4. Open a pull request describing what changed and why. CI (once configured)
   should run `pytest -q` against a MySQL service before merging.

Please don't commit real credentials — `Backend/.env` is git-ignored for
exactly that reason; use `Backend/.env.example` to document new variables.
