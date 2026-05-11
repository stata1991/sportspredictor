# FantasyFuel — Backend & Deploy Runbook

## Overview

FantasyFuel.ai is a multi-sport prediction platform. The active product is FIFA World Cup 2026 match predictions using a Dixon-Coles statistical model + Claude AI reasoning layer. Cricket (IPL/T20WC) routes exist but are paused.

This runbook covers: local dev, Docker build, AWS deploy (backend + frontend), rollback, environment variables, and pitfalls learned from production incidents.

## Architecture

- **Backend:** FastAPI on AWS Elastic Beanstalk (Docker on Amazon Linux 2), us-east-2
- **Frontend:** React 18 + MUI on S3 + CloudFront, us-east-1 (cross-region by design — CloudFront is global)
- **DB:** Supabase Pro, `football` schema, alembic-managed migrations
- **Monitoring:** Sentry (two separate projects: backend + frontend), CloudWatch via EB
- **AI:** Anthropic API (`claude-sonnet-4-6`) for agent reasoning + upset index
- **Data:** API-Football (api-sports.io) for fixtures, lineups, live scores
- **Pre-rendering:** react-snap (Puppeteer-based) for SEO — 9 routes pre-rendered at build time

## Key Resources & IDs

| Resource | ID / Name | Region |
|---|---|---|
| EB environment | `fantasyfuel-docker3` | us-east-2 |
| EB CNAME | `fantasyfuel-docker3.eba-qxf2p43b.us-east-2.elasticbeanstalk.com` | us-east-2 |
| EC2 instance | `i-0921339dd06e66ee5` (3.19.97.245) | us-east-2 |
| S3 bucket | `fantasyfuel.ai` | us-east-1 |
| CloudFront distribution | `E3M2G8G0JUVPK0` | global |
| Pre-football rollback AMI | `ami-02ec382ffa06e246b` | us-east-2 |
| Pre-football EB version | `app-72ed-260221_173723868919` | — |
| Domain registrar | Namecheap | — |
| DNS | Namecheap default DNS (`dns1.registrar-servers.com`) | — |

> **Do not include credentials or DSNs in this doc.** They live in: 1Password, Sentry dashboard settings, Supabase console, and EB environment properties.

## Prerequisites

- AWS CLI v2 configured with credentials for account `240639309844`
- EB CLI installed (`pip install awsebcli`)
- Node 18+ and npm
- Python 3.11
- Google Chrome installed at `/Applications/Google Chrome.app` (for react-snap on macOS)
- `git`, on a branch you intend to deploy

## Local Development

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

## Environment Variables

### Backend (EB environment properties)

| Var | Source | Notes |
|---|---|---|
| `DATABASE_URL` | Supabase pooler URL (transaction mode, port 6543) | Format: `postgresql+psycopg://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres` |
| `API_FOOTBALL_KEY` | api-football.com dashboard | |
| `ANTHROPIC_API_KEY` | console.anthropic.com | |
| `ANTHROPIC_MODEL` | literal string: `claude-sonnet-4-6` | |
| `SENTRY_DSN` | Sentry → fantasyfuel-backend project | |
| `AUTH_ENABLED` | `"false"` | Flip to `"true"` only when auth feature ships |

### Frontend (build-time, baked into bundle)

| Var | Location | Notes |
|---|---|---|
| `REACT_APP_API_URL` | `frontend/.env.production` | Must be `https://fantasyfuel.ai` — **NO `/api` suffix** (axios call sites prepend it) |
| `REACT_APP_SENTRY_DSN` | `frontend/.env.production` | Different from backend DSN — separate Sentry project |

## Standard Deploy Sequence

### Pre-deploy checklist

- [ ] On `main` with merge commit clean (`git status`)
- [ ] All tests green locally (`cd frontend && npm test -- --watchAll=false` and `cd backend && pytest`)
- [ ] EB env vars current (`eb printenv` lists all six)
- [ ] AMI snapshot exists if this is a high-risk deploy

### Backend deploy

```bash
# 1. Set default environment for this branch
eb use fantasyfuel-docker3

# 2. (Optional, recommended for risky deploys) Take fresh AMI snapshot
#    via AWS Console → EC2 → Instances → i-0921339dd06e66ee5 → Actions → Create image

# 3. Deploy
eb deploy

# 4. Watch until Status: Ready, Health: Green
eb status

# 5. Smoke tests (3 curls)
EB_CNAME="fantasyfuel-docker3.eba-qxf2p43b.us-east-2.elasticbeanstalk.com"
curl -s "http://$EB_CNAME/" | jq .status                           # → "ok"
curl -s "http://$EB_CNAME/api/football/fixtures" | jq '.fixtures | length'  # → >0
curl -s "http://$EB_CNAME/api/football/predict/pre-match/1489369" | jq .stage  # → "pre_lineup" or similar
```

### Frontend deploy

```bash
cd frontend

# 1. Clean install
npm ci

# 2. react-snap needs Chrome path on macOS
export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 3. Build (includes react-snap post-build)
npm run build
# Verify: should say "crawled 9 out of 9"

# 4. Sanity check — API URL baked correctly
grep -o "fantasyfuel.ai/api" build/static/js/main.*.js | head -1
# Should return a match

# 5. Backup current S3 build (rollback insurance)
aws s3 sync s3://fantasyfuel.ai/ ~/s3-backup-$(date +%Y%m%d)/

# 6. Deploy to S3
aws s3 sync build/ s3://fantasyfuel.ai/ --delete

# 7. Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id E3M2G8G0JUVPK0 --paths "/*"
```

### Post-deploy smoke (hit fantasyfuel.ai, not the EB CNAME)

```bash
# New bundle serves
curl -sI "https://fantasyfuel.ai/static/js/main.*.js" | head -1  # 200

# Pages load
curl -s -o /dev/null -w "%{http_code}" "https://fantasyfuel.ai/"                                    # 200
curl -s -o /dev/null -w "%{http_code}" "https://fantasyfuel.ai/football/world-cup-2026/"             # 200
curl -s -o /dev/null -w "%{http_code}" "https://fantasyfuel.ai/football/world-cup-2026/live/"        # 200
curl -s -o /dev/null -w "%{http_code}" "https://fantasyfuel.ai/football/world-cup-2026/track-record/" # 200

# Pre-rendered titles are route-specific
grep -o "<title>[^<]*</title>" build/football/world-cup-2026/index.html
# → <title>FIFA World Cup 2026 Schedule | FantasyFuel</title>

# API responds through CloudFront
curl -s "https://fantasyfuel.ai/api/football/fixtures" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['fixtures']),'fixtures')"

# DevTools: console clean, Network tab no 5xx
```

## Rollback

### Backend rollback

```bash
# Soft rollback — redeploy a previous EB application version
aws elasticbeanstalk update-environment \
  --environment-name fantasyfuel-docker3 \
  --version-label app-72ed-260221_173723868919

# Or via EB console: Elastic Beanstalk → App versions → select version → Deploy

# Disaster recovery (env termination):
# Launch EC2 from AMI ami-02ec382ffa06e246b, reattach to env
```

### Frontend rollback

```bash
# Restore from backup
aws s3 sync ~/s3-backup-<date>/ s3://fantasyfuel.ai/ --delete
aws cloudfront create-invalidation --distribution-id E3M2G8G0JUVPK0 --paths "/*"
```

## Match-Day Procedure (WC 2026 Fixtures)

- **Morning of fixture:** re-run `GET /api/football/predict/pre-match/{fixture_id}`. Snapshot the JSON output for comparison with the post-match outcome.
- **1 hour before kickoff:** check whether lineups data has flowed in — call `GET /api/football/fixtures/{fixture_id}` and look for `status.short` changing from `NS` to lineup-available. Re-run pre-match prediction (should now return `stage: post_lineup`).
- **During match:** monitor Sentry dashboard for backend/frontend errors. Optionally call `GET /api/football/predict/live/{fixture_id}` to verify live predictions update.
- **After full-time:** capture actual outcome. Log as "prediction hit" or "prediction miss" for accuracy tracking. Run `GET /api/football/accuracy` to check if rollups have been updated.

## Pitfalls Learned

These are real incidents from production deploys. Future deploys should check this list before deploying.

1. **CloudFront error response intercepts API 404s.** Custom error responses are distribution-wide — a 404→`/index.html` rewrite for SPA fallback also intercepts EB 404 JSON responses. Solution: rely on S3 static-website's own error document config (`Error document: index.html`) instead, and remove the CloudFront custom error response entirely.

2. **`REACT_APP_API_URL` must NOT end in `/api`.** Axios call sites prepend `/api/...` to all requests. If the base URL also ends in `/api`, all requests become `/api/api/...` and 404. Set it to just `https://fantasyfuel.ai`.

3. **Favicon browser caching is aggressive.** Renaming to `favicon-v2.ico` (and updating `<link>` in `index.html`) is the only reliable cache-bust.

4. **react-snap + nested routes.** Child components rendered through `<Outlet>` may not have their `<Helmet>` tags captured in pre-rendered HTML. Move title/meta logic into the parent Layout component which renders synchronously. This is why `WorldCup2026Layout.tsx` owns the `<Helmet>` for all three sub-routes.

5. **`eb use` is per-branch.** Switching from `feature/football` to `main` and running `eb deploy` will fail with "no default environment". Run `eb use fantasyfuel-docker3` once per branch.

6. **`PUPPETEER_EXECUTABLE_PATH` required for react-snap** to find Chrome on macOS. Add to your shell rc file so it persists: `export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`

7. **EB AL2 platform deprecated June 30, 2026.** After that date, can't create new AL2 envs. Plan AL2023 migration for late July post-tournament. AMI snapshot is the emergency recreate path.

8. **Supabase shares a `public` schema with an unrelated app.** All football migrations MUST be scoped to `schema='football'` in alembic. Bare table names will collide with the other product.

9. **MUI theme `background.default` must be a plain color, not a CSS gradient.** `CssBaseline` applies it as `background-color` on `<body>`, which silently drops gradient values and falls back to white. Use `#0d0d0d`.

10. **Error-based routing couples frontend to backend wording.** The frontend parses 422 detail strings to distinguish "live" from "not predictable" fixtures. Works for V1 but fragile — post-launch, switch to structured error codes or a lightweight `/api/football/fixtures/{id}/status` endpoint.

11. **DNS is on Namecheap, not Route 53.** Despite AWS nameserver artifacts in `dig NS` output, the authoritative DNS is Namecheap's default DNS servers (`dns1.registrar-servers.com`). DNS changes (A records, CNAMEs) must be made in the Namecheap dashboard.

## Maintenance Tasks

### Sentry

- Two projects: `fantasyfuel-backend` (FastAPI) and `fantasyfuel-frontend` (React)
- Backend DSN lives in EB env var `SENTRY_DSN`
- Frontend DSN lives in `frontend/.env.production` (build-time)
- Verify after each significant deploy with intentional test errors

### DB migrations

```bash
# Run against prod Supabase from laptop:
DATABASE_URL=<prod_session_pooler> alembic upgrade head

# Use session pooler (port 5432) for migrations, transaction pooler (6543) for runtime
# Verify after:
alembic current  # should show 0002 or later
```

### Tracked Backlog (Post-Launch)

- AL2 → AL2023 platform migration (after tournament ends)
- Logo PNGs (32 country flags) → SVG sprite for mobile perf
- Structured error codes from backend (replace string-parsing of 422 detail in frontend)
- Two Sentry backend projects (`fantasyfuel-backend` vs `fantasyfuel-backend-2`) — consolidate
- Dynamic match titles (`France vs Germany Prediction | FantasyFuel`) work at runtime only, not in pre-rendered HTML — acceptable for `/football/match/{id}` since those routes aren't pre-rendered by react-snap

## Project Structure

```
backend/
├── main.py                 # FastAPI app, cricket routes, middleware, Sentry init
├── config.py               # Cache TTLs, env var config
├── cache.py                # Redis / in-memory cache client
├── football/
│   ├── routes.py           # Football API endpoints (/fixtures, /predict, /accuracy, /upsets)
│   ├── data_provider.py    # API-Football client
│   ├── persistence.py      # SQLAlchemy queries (football schema)
│   ├── schemas.py          # Pydantic models for API-Football data
│   ├── predictions/        # Dixon-Coles engine, derivations
│   ├── agent/              # Anthropic reasoning + upset index
│   └── tests/              # Route + persistence tests
└── shared/
    ├── db.py               # AsyncSession factory
    └── models.py           # SQLAlchemy ORM models
```

```
frontend/
├── public/
│   ├── index.html          # SPA shell, OG tags, favicon links
│   ├── favicon-v2.ico      # Cache-busted favicon
│   ├── logo.svg            # SVG icon
│   └── manifest.json       # PWA manifest (FantasyFuel branding)
├── src/
│   ├── index.tsx            # Entry: Sentry, HelmetProvider, ThemeProvider, CssBaseline
│   ├── App.tsx              # Router: nested routes, lazy loading
│   ├── api.ts               # Axios instance (base URL from env)
│   ├── theme/theme.ts       # MUI dark theme (palette, typography, component overrides)
│   ├── football/
│   │   ├── components/      # FixtureCard, FixtureList, LiveBadge, LiveMatchSection, WhyPanel
│   │   ├── hooks/           # useFixtures, useAccuracy, useUpsets, useLivePolling, useMatchPrediction
│   │   ├── types/           # AFFixture, AccuracyRollup, WorldCupOutletContext
│   │   ├── utils/           # fixtureStatus (isInPlay, isCompleted), probability formatters
│   │   └── colors.ts        # Design tokens
│   └── pages/
│       ├── HomePage.tsx
│       ├── AboutPage.tsx
│       ├── PrivacyPage.tsx
│       ├── AuthPage.tsx
│       └── football/
│           ├── WorldCup2026Layout.tsx  # Parent: tabs, Helmet (URL-driven), Outlet
│           ├── SchedulePage.tsx        # Tab 1: fixture list
│           ├── LiveMatchPage.tsx       # Tab 2: in-play fixtures
│           ├── TrackRecordPage.tsx     # Tab 3: KPI cards + accuracy table
│           ├── MatchPage.tsx           # Individual match prediction
│           └── UpsetsPage.tsx          # Upset watch list
└── package.json             # react-snap config: 9 pre-rendered routes
```
