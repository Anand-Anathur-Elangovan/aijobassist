# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (Next.js)
```bash
npm install          # Install dependencies
npm run dev          # Start dev server (localhost:3000)
npm run build        # Production build
npm run lint         # ESLint check
```

### Backend (Python Task Runner)
```bash
pip install -r requirements.txt          # Install Python dependencies
playwright install chromium              # Install browser for automation
python taskrunner/server.py              # Start task runner HTTP server
python taskrunner/task_runner.py         # Run task runner directly
```

### Tests
```bash
pytest tests/                            # Run all tests
pytest tests/test_ats_bot.py            # Run ATS form-fill tests
python taskrunner/mock_test.py          # Standalone task runner tests
python taskrunner/test_url_apply.py     # Test single-URL application
python taskrunner/test_naukri_direct.py # Test Naukri automation
```

### Docker
```bash
docker build -t aijobassist .
docker run --env-file .env aijobassist
```

## Architecture

VantaHire is an AI-powered job application automation platform with two independently deployed services:

### 1. Frontend — Next.js 14 App Router
- **`/app/(protected)/`** — All authenticated pages (dashboard, agent, analytics, billing, etc.)
- **`/app/api/ai/`** — AI API routes powered by Claude: `tailor-resume`, `cover-letter`, `match-score`, `interview-prep`, `skill-gap`, `analyze-jd`, `career-copilot`, etc.
- **`/app/api/tasks/`** — Task management endpoints (create, status, logs)
- **`/app/api/billing/`** — Razorpay payment + quota enforcement
- **`/context/AuthContext.tsx`** — Supabase Auth state provider; wraps entire app
- **`/middleware.ts`** — JWT refresh on every request via Supabase SSR

### 2. Backend — Python Task Runner (deployed as Docker container on Railway)
- **`taskrunner/server.py`** — Flask HTTP server; starts polling loop in background thread
- **`taskrunner/task_runner.py`** — Polls Supabase `tasks` table for `PENDING` tasks and dispatches by type:
  - `AUTO_APPLY` → LinkedIn/Naukri automation
  - `TAILOR_AND_APPLY` → Tailor resume then apply
  - `URL_APPLY` → Apply to a specific URL
  - `TAILOR_RESUME` → Resume rewrite only
  - `GMAIL_DAILY_CHECK` → Parse rejection/offer emails
- **`automation/linkedin.py`** — Playwright-based LinkedIn scraping and Easy Apply automation
- **`automation/naukri.py`** — Playwright-based Naukri job portal automation
- **`automation/human.py`** — Human-like behavior injection (random delays, mouse jitter) to evade bot detection

### 3. Form-Fill Pipeline (automation/)
The core AI form-filling pipeline processes each job application:
1. **`ats_fingerprint.py`** — Detect ATS type (Workday, Greenhouse, Lever, etc.)
2. **`run_form_fill.py`** — Inject JavaScript to extract form fields with context (labels, aria, placeholders)
3. **`field_normalizer.py`** — Normalize field names; automatically skip EEO/demographic fields
4. **`field_cache.py`** — SQLite cache for repeated field answers (avoids redundant Claude calls)
5. **`claude_filler.py`** — Send fields to Claude (Haiku for speed, Sonnet for accuracy) to generate answers from resume + preferences
6. **`fill_validator.py` / `sync_fill_validator.py`** — Verify form is correctly filled; retry on failure
7. **`ai_client.py`** — Claude API wrapper with circuit-breaker; routes to `claude-haiku-4-5` or `claude-sonnet-4-6` based on task complexity

### 4. Database (Supabase PostgreSQL)
Key tables:
- `tasks` — Async job queue with `status`, `input`, `output`, `logs` (JSONB array for live streaming)
- `resumes` — Resume metadata + `parsed_text` used for AI matching
- `job_preferences` — User search criteria (title, salary, industries, location, relocation)
- `applications` — Applied job records
- `billing_subscriptions` — Razorpay orders + daily quota counters per feature
- `railway_sessions` — Live screenshots and session state from cloud automation runs
- `user_profiles` — Per-user Telegram chat IDs and notification settings

All tables use Row Level Security (RLS) scoped to the authenticated user.

### 5. Key Integration Points
- **Task creation flow:** Frontend (`/app/api/tasks/create`) inserts a row into `tasks` table → Python runner polls and picks it up
- **Live logs:** Python runner appends structured JSON to `tasks.logs` → Frontend polls for updates and streams to UI
- **Resume data flow:** Upload → `/api/ai/parse-resume` extracts text → stored in `resumes.parsed_text` → used by form-fill pipeline and match-score
- **Quota enforcement:** Each task type has daily limits checked in `/app/api/billing/check-quota` before task creation
- **Notifications:** After each application, runner sends Telegram message (per-user chat ID from DB) and/or Gmail SMTP email

## Environment Variables
See `.env.example` for all required variables:
- `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`
- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET`
- `TELEGRAM_BOT_TOKEN` (per-user `TELEGRAM_CHAT_ID` stored in DB)
- `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`

## Database Schema
Run `schema.sql` (and any `schema*.sql` variants) in Supabase SQL editor to set up tables and RLS policies.
