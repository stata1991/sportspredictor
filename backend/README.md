# FantasyFuel Backend

FastAPI backend for multi-sport predictions (cricket IPL/T20WC + football World Cup 2026).

## Local development

```bash
# From repo root:
pip install -r requirements.txt -r requirements-dev.txt

# Required env vars (copy backend/.env.example → backend/.env):
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/fantasyfuel"
export API_FOOTBALL_KEY="your-api-football-key"
# Optional:
export ANTHROPIC_API_KEY="your-anthropic-key"   # enables agent reasoning
export SENTRY_DSN="https://...@sentry.io/..."   # enables error tracking
export ENV="development"                         # Sentry environment tag

# Run:
uvicorn backend.main:app --reload --port 8000

# Tests:
python -m pytest backend/ -q
```

## Docker

```bash
# Build (from repo root — Dockerfile is at repo root):
docker build -t fantasyfuel-backend .

# Run:
docker run -p 8000:8000 \
  -e DATABASE_URL="$DATABASE_URL" \
  -e API_FOOTBALL_KEY="$API_FOOTBALL_KEY" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e SENTRY_DSN="$SENTRY_DSN" \
  -e ENV="production" \
  fantasyfuel-backend

# Verify:
curl -s http://localhost:8000/ | jq .
# → {"status": "ok"}
```

## AWS Elastic Beanstalk deploy

EB environment: `Fantasyfuel-backend-env-2-env` (us-east-2, Docker on Amazon Linux 2).

```bash
# From repo root (requires EB CLI + credentials configured):
eb deploy Fantasyfuel-backend-env-2-env

# Or via AWS Console:
# Elastic Beanstalk → Fantasyfuel-backend-env-2 → Upload and deploy
# Upload a zip of: Dockerfile, requirements.txt, backend/
```

EB environment variables (set in Configuration → Software → Environment properties):

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `API_FOOTBALL_KEY` | Yes | RapidAPI key for api-football |
| `ANTHROPIC_API_KEY` | No | Enables Claude agent reasoning layer |
| `SENTRY_DSN` | No | Enables Sentry error tracking |
| `ENV` | No | Sentry environment tag (default: `development`) |
| `REDIS_URL` | No | Redis URL for caching (falls back to in-memory) |

## Match-day procedure (WC 2026 fixtures)

- **Morning of fixture:** re-run `GET /api/football/predict/pre-match/{fixture_id}`. Snapshot the JSON output for comparison with the post-match outcome.
- **1 hour before kickoff:** check whether lineups data has flowed in — call `GET /api/football/fixtures/{fixture_id}` and look for `status.short` changing from `NS` to lineup-available. Re-run pre-match prediction (should now return `stage: post_lineup`).
- **During match:** monitor Sentry dashboard for backend/frontend errors. Optionally call `GET /api/football/predict/live/{fixture_id}` to verify live predictions update.
- **After full-time:** capture actual outcome. Log as "prediction hit" or "prediction miss" for accuracy tracking. Run `GET /api/football/accuracy` to check if rollups have been updated.

## Project structure

```
backend/
├── main.py                 # FastAPI app, cricket routes, middleware
├── config.py               # Cache TTLs, env var config
├── cache.py                # Redis / in-memory cache client
├── football/
│   ├── routes.py           # Football API endpoints
│   ├── data_provider.py    # API-Football client
│   ├── persistence.py      # SQLAlchemy queries
│   ├── schemas.py          # Pydantic models for API-Football data
│   ├── predictions/        # Dixon-Coles engine, derivations
│   ├── agent/              # Anthropic reasoning + upset index
│   └── tests/              # Route + persistence tests
└── shared/
    ├── db.py               # AsyncSession factory
    └── models.py           # SQLAlchemy ORM models
```
