# VantaHire / AIJobAssist — Full Codebase Context

> **Purpose:** Single reference file for AI-assisted development. Read this before ANY feature work.
> Update this file whenever new tables, routes, functions, or major logic changes are made.

---

## 1. Project Overview

**Product:** VantaHire — AI-powered job automation + Career Copilot for Indian students
**Stack:** Next.js 14 (App Router) + Supabase + Tailwind CSS + Anthropic Claude API + Razorpay
**Language:** TypeScript (frontend/API routes) + Python (automation bot)
**Supabase URL:** `https://feqhdpxnzlctpwvvjxui.supabase.co`

### Two Product Modes
| Mode | Users | Purpose |
|------|-------|---------|
| `job_seeker` | Working professionals | Auto-apply to LinkedIn/Naukri, AI resume tailoring, cover letters |
| `student` | School/college students | College Pathfinder (school→college engine), Placement Mode |

---

## 2. File Structure

```
aijobassist/
├── app/
│   ├── globals.css
│   ├── layout.tsx              # Root layout — AuthProvider wraps all children
│   ├── page.tsx                # Redirects → /landing
│   ├── (protected)/            # Requires auth (AuthGuard + SubscriptionGuard)
│   │   ├── layout.tsx          # Wraps protected pages with AuthGuard
│   │   ├── admin/page.tsx      # Admin dashboard (super-admin only)
│   │   ├── admin/setup-guide/  # Admin setup docs
│   │   ├── agent/page.tsx      # Task runner / bot control panel — NOW HAS execution mode selector
│   │   ├── agent/setup/page.tsx # NEW — Railway setup wizard for users
│   │   ├── analytics/page.tsx  # Usage analytics
│   │   ├── applications/       # Application tracker
│   │   ├── billing/page.tsx    # Subscription & billing UI
│   │   ├── career-copilot/page.tsx  # College Pathfinder + Placement Mode
│   │   ├── dashboard/page.tsx  # Main dashboard + job preferences (30+ fields)
│   │   ├── interview-prep/     # Interview prep (standalone AI feature)
│   │   ├── job-preferences/    # Job search config
│   │   ├── job-search/         # Search & apply to jobs
│   │   ├── notifications/      # In-app notifications
│   │   ├── pricing/page.tsx    # Plans & pricing
│   │   ├── resume-studio/      # Resume builder / tailoring
│   │   ├── settings/page.tsx   # Account settings
│   │   └── upload-resume/      # PDF resume upload + parse
│   ├── api/
│   │   ├── agent-key/route.ts
│   │   ├── railway/            # NEW — Railway cloud execution APIs
│   │   │   ├── trigger/route.ts     # POST — start Railway job
│   │   │   ├── stop/route.ts        # POST — stop Railway job
│   │   │   ├── status/route.ts      # GET — job status
│   │   │   └── stream/route.ts      # GET — WebSocket screenshot stream
│   │   ├── ai/ ...             (unchanged)
│   │   ├── billing/ ...        (unchanged)
│   │   ├── gmail/trigger/
│   │   └── job-history/reset/
│   ├── contact/page.tsx
│   ├── landing/page.tsx
│   ├── login/page.tsx
│   ├── onboarding/page.tsx
│   ├── privacy/page.tsx
│   ├── refund/page.tsx
│   └── terms/page.tsx
├── automation/
│   ├── ai_client.py
│   ├── gmail_client.py
│   ├── human.py
│   ├── linkedin.py
│   ├── naukri.py
│   ├── resume_parser.py
│   ├── resume_tailor.py
│   └── screenshot_streamer.py  # NEW — WebSocket screenshot push during automation
├── components/
│   ├── AuthGuard.tsx
│   ├── NavBar.tsx
│   ├── SubscriptionGuard.tsx
│   └── ExecutionModeModal.tsx  # NEW — modal for own machine vs Railway selection
├── context/
│   └── AuthContext.tsx
├── lib/
│   ├── ai.ts
│   ├── api-auth.ts
│   ├── billing.ts
│   ├── railway.ts              # NEW — Railway API helpers + quota tracking
│   └── supabase.ts
├── taskrunner/
│   ├── main.py
│   ├── task_runner.py          # UPDATED — checks execution_mode before running locally
│   ├── api_client.py
│   ├── build_agent.py
│   └── agent_entry.py
├── middleware.ts
├── next.config.js
├── tailwind.config.ts
├── schema.sql
├── schema_additions.sql
├── schema_billing.sql
├── schema_career_copilot.sql
└── schema_railway.sql          # NEW — Railway execution tables
```

---

## 3. Environment Variables (`.env.local`)

```env
NEXT_PUBLIC_SUPABASE_URL=https://feqhdpxnzlctpwvvjxui.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...  (public anon key)
SUPABASE_SERVICE_ROLE_KEY=eyJ...      (service key — server-side only)
ANTHROPIC_API_KEY=sk-ant-...          (Claude AI)
RAZORPAY_KEY_ID=rzp_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
RAILWAY_API_TOKEN=...                 # NEW — from Railway account settings
RAILWAY_PROJECT_ID=...                # NEW — Railway project ID
RAILWAY_SERVICE_ID=...                # NEW — Railway service ID
RAILWAY_SERVICE_URL=https://...       # NEW — public URL of Railway automation service
```

**Super admins (bypass all quotas):**
- `kaviyasaravanan01@gmail.com`
- `anandanathurelangovan94@gmail.com`

---

## 4. Database Schema

### Core Tables (`schema.sql`) — UNCHANGED

**`resumes`**, **`jobs`**, **`applications`** — unchanged.

**`tasks`** — UPDATED: added `execution_mode` column
```
id, user_id, application_id, type TEXT, status task_status DEFAULT 'PENDING',
input JSONB, output JSONB, error TEXT,
logs JSONB DEFAULT '[]',
progress INT DEFAULT 0,
current_job TEXT,
custom_prompt_override TEXT,
paused BOOLEAN DEFAULT FALSE,
stop_requested BOOLEAN DEFAULT FALSE,
execution_mode TEXT DEFAULT 'own_machine',   -- NEW: 'own_machine' | 'railway'
railway_job_id TEXT,                          -- NEW: Railway run ID when execution_mode='railway'
created_at, completed_at
```

### Extended Tables (`schema_additions.sql`) — UNCHANGED

### Billing Tables (`schema_billing.sql`) — UPDATED

**`plans`** — Seeded plans (UPDATED with Railway limits):
| slug | name | Monthly | Weekly |
|------|------|---------|--------|
| `trial` | Free Trial | ₹0 (10 days) | — |
| `free` | Free | ₹0 | — |
| `normal` | Pro | ₹999 | ₹349 |
| `premium` | Premium | ₹1999 | ₹699 |

**`plan_limits`** — UPDATED: added `railway_minutes` action_type
| action | trial | free | pro | premium |
|--------|-------|------|-----|---------|
| auto_apply | 10 | 0 | 25 | 80 |
| semi_auto | 20 | 10 | 75 | 200 |
| ai_tailor | 5 | 1 | 15 | 40 |
| gmail_scan | 5 | 3 | 25 | 75 |
| cover_letter | 5 | 2 | 15 | 40 |
| jd_analysis | 10 | 5 | 50 | 999 |
| **railway_minutes** | **5** | **5** | **15** | **30** |

> Admin super-users get 120 minutes/day (2 hours) — hardcoded in `lib/railway.ts`, bypass `enforceQuota`.

**`user_profiles`** — UPDATED: added execution preference
```
id, user_id UNIQUE, full_name, phone, country TEXT DEFAULT 'India',
avatar_url, onboarding_done BOOL, role TEXT DEFAULT 'user',
job_preferences JSONB,
app_mode TEXT DEFAULT 'job_seeker',
preferred_execution_mode TEXT DEFAULT 'own_machine',  -- NEW: 'own_machine' | 'railway'
railway_configured BOOL DEFAULT FALSE,                 -- NEW: has user done Railway setup?
created_at, updated_at
```

### NEW: Railway Tables (`schema_railway.sql`)

**`railway_sessions`**
```sql
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
user_id UUID REFERENCES auth.users NOT NULL,
task_id UUID REFERENCES tasks(id),
railway_run_id TEXT,                    -- Railway's internal run ID
status TEXT DEFAULT 'pending',          -- 'pending' | 'running' | 'completed' | 'failed' | 'stopped'
started_at TIMESTAMPTZ DEFAULT now(),
ended_at TIMESTAMPTZ,
duration_seconds INT,                   -- computed on end
screenshot_count INT DEFAULT 0,
error TEXT,
created_at TIMESTAMPTZ DEFAULT now()
```

**`railway_daily_usage`**
```sql
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
user_id UUID REFERENCES auth.users NOT NULL,
usage_date DATE DEFAULT CURRENT_DATE,
minutes_used NUMERIC(6,2) DEFAULT 0,    -- cumulative minutes used today
UNIQUE(user_id, usage_date)
```

---

## 5. lib/ai.ts — UNCHANGED

---

## 6. API Routes

### Existing AI Routes — UNCHANGED

### Billing Routes — UNCHANGED

### NEW: Railway Routes

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/api/railway/trigger` | POST | Bearer | Start a Railway automation job |
| `/api/railway/stop` | POST | Bearer | Stop a running Railway job |
| `/api/railway/status` | GET | Bearer | Get current Railway job status + screenshot |
| `/api/railway/stream` | GET | Bearer | SSE stream of screenshots (base64 JPEG, 1/sec) |

#### `POST /api/railway/trigger`
```typescript
// Request body:
{ task_id: string, task_type: 'AUTO_APPLY' | 'TAILOR_AND_APPLY', task_input: object }

// Flow:
// 1. getAuthUser — verify token
// 2. checkRailwayQuota(user_id, user_email) — check daily railway_minutes limit
// 3. Call Railway API to trigger automation container run
// 4. Store railway_run_id in tasks.railway_job_id
// 5. Insert row in railway_sessions
// 6. Return { success: true, session_id, railway_run_id }

// Response:
{ success: boolean, session_id: string, railway_run_id: string }
```

#### `POST /api/railway/stop`
```typescript
// Request body: { task_id: string, session_id: string }
// Flow: call Railway API to stop run, update railway_sessions.ended_at, compute duration, update railway_daily_usage
```

#### `GET /api/railway/status`
```typescript
// Query: ?task_id=xxx
// Returns: { status, progress, current_job, logs[], latest_screenshot_base64? }
```

#### `GET /api/railway/stream` (Server-Sent Events)
```typescript
// Query: ?session_id=xxx
// Streams: { type: 'screenshot', data: base64JPEG, timestamp } every ~1 second
// Streams: { type: 'log', message, level } for task log events
// Streams: { type: 'done', status } when automation ends
```

### Other — UNCHANGED

---

## 7. lib/api-auth.ts — UNCHANGED

---

## 8. NEW: lib/railway.ts

```typescript
// Railway API helpers

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
RAILWAY_API_TOKEN = process.env.RAILWAY_API_TOKEN
RAILWAY_PROJECT_ID = process.env.RAILWAY_PROJECT_ID
RAILWAY_SERVICE_ID = process.env.RAILWAY_SERVICE_ID
RAILWAY_SERVICE_URL = process.env.RAILWAY_SERVICE_URL

// Functions:
checkRailwayQuota(userId: string, userEmail?: string): Promise<{ allowed: boolean, used: number, limit: number }>
// -- super admins get 120 min/day, others use plan_limits.railway_minutes
// -- reads railway_daily_usage for today's usage

incrementRailwayUsage(userId: string, minutes: number): Promise<void>
// -- upserts railway_daily_usage, increments minutes_used

triggerRailwayRun(taskId: string, taskInput: object): Promise<{ runId: string }>
// -- POST to RAILWAY_SERVICE_URL/trigger with task payload + auth

stopRailwayRun(runId: string): Promise<void>
// -- POST to RAILWAY_SERVICE_URL/stop

getRailwayRunStatus(runId: string): Promise<{ status: string, progress: number }>
```

---

## 9. lib/billing.ts — UNCHANGED

---

## 10. context/AuthContext.tsx — UNCHANGED

---

## 11. Components

### NEW: `components/ExecutionModeModal.tsx`

Modal shown when user triggers AUTO_APPLY or TAILOR_AND_APPLY.

```typescript
Props: {
  isOpen: boolean
  onClose: () => void
  onConfirm: (mode: 'own_machine' | 'railway') => void
  railwayConfigured: boolean       // from user_profiles.railway_configured
  planQuota: { used: number, limit: number }  // railway_minutes today
  taskType: 'AUTO_APPLY' | 'TAILOR_AND_APPLY'
}
```

**UI Rules:**
- Show two cards: "Own Machine" and "Railway Cloud"
- Railway card shows today's quota usage (e.g. "3 / 15 min used today")
- If `railwayConfigured === false`: show "Setup Required" badge on Railway card + link to `/agent/setup`
- If Railway quota exhausted: disable Railway card, show "Daily limit reached"
- Default selection: `user_profiles.preferred_execution_mode`
- "Remember my choice" checkbox — saves to `user_profiles.preferred_execution_mode`
- Recommended badge on Railway option
- If user selects `own_machine` → standard .exe flow (existing behavior, unchanged)
- If user selects `railway` → calls `/api/railway/trigger`

---

## 12. NEW: `app/(protected)/agent/setup/page.tsx` — Railway Setup Wizard

Step-by-step guide for users to connect their Railway account.

**Steps:**
1. Create Railway account (link to railway.app)
2. Deploy automation container (one-click deploy button using Railway template URL)
3. Enter Railway Service URL (user pastes their deployed service URL)
4. Test connection (calls `/api/railway/status` with a ping)
5. Done — sets `user_profiles.railway_configured = true`

**Auto-setup option on Agent page:**
- Banner/card at top of agent page: "Run in Cloud — No install needed. Set up Railway in 2 mins →"
- Only shown if `railway_configured === false`

---

## 13. app/(protected)/agent/page.tsx — UPDATED

**Changes (non-breaking, additive only):**
1. On page load: fetch `user_profiles.preferred_execution_mode` and `railway_configured`
2. Add Railway setup banner at top (conditional, dismissible)
3. When user clicks "Start Auto Apply" or "Start Semi-Auto": open `ExecutionModeModal` instead of triggering directly
4. If modal returns `own_machine`: existing trigger flow (unchanged)
5. If modal returns `railway`: call `POST /api/railway/trigger`, then show live screenshot stream panel
6. Live screenshot panel: `<img>` tag updated every second via SSE stream from `/api/railway/stream`
7. Stop button calls `POST /api/railway/stop`
8. Existing logs panel works for both modes (logs still written to `tasks.logs` via `append_task_log`)

**IMPORTANT — DO NOT CHANGE:**
- Existing trigger logic for `own_machine`
- Existing log streaming from Supabase
- Existing pause/stop/resume for local tasks
- Task creation flow

---

## 14. automation/screenshot_streamer.py — NEW

```python
# Runs inside Railway container alongside automation
# Captures screenshots every 1 second and pushes to Supabase realtime channel

import asyncio
from playwright.async_api import Page
import base64
import httpx

SCREENSHOT_INTERVAL = 1.0  # seconds

async def stream_screenshots(page: Page, session_id: str, supabase_url: str, supabase_key: str):
    """
    Takes screenshot of current browser state every SCREENSHOT_INTERVAL seconds.
    Pushes base64 JPEG to Supabase realtime broadcast channel: f"railway_stream_{session_id}"
    Stops when global stop_event is set.
    """
    channel_name = f"railway_stream_{session_id}"
    while not stop_event.is_set():
        try:
            screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(screenshot_bytes).decode()
            # POST to Supabase realtime broadcast
            await push_screenshot(supabase_url, supabase_key, channel_name, b64)
        except Exception as e:
            pass  # page might be navigating — skip frame
        await asyncio.sleep(SCREENSHOT_INTERVAL)
```

---

## 15. taskrunner/task_runner.py — UPDATED

**One change only:** Before running any automation locally, check `task.execution_mode`:
```python
def run_task(task):
    if task.get("execution_mode") == "railway":
        # This task is handled by Railway container — skip local execution
        log.info(f"Task {task['id']} is set to railway mode — skipping local runner")
        return
    # ... existing dispatch logic unchanged ...
```

---

## 16. Subscription Plans & Railway Limits

### Current Plans (unchanged pricing)

| Plan | Price | Railway Min/Day | Notes |
|------|-------|----------------|-------|
| Trial | ₹0 (10 days) | 5 min | One-time trial |
| Free | ₹0 | 5 min | Always free |
| Pro | ₹999/mo · ₹349/wk | 15 min | Good for daily job hunting |
| Premium | ₹1999/mo · ₹699/wk | 30 min | Power users |
| Admin | — | 120 min (2 hrs) | Super admin bypass |

### Recommendation: Keep Existing 4 Plans
- No new plan needed at this stage
- Add `railway_minutes` as a new `action_type` in `plan_limits` table
- Railway is a **feature within existing plans**, not a new plan
- Upgrade prompt: if Free user hits 5-min Railway limit → "Upgrade to Pro for 15 min/day cloud automation"

### Future: Consider "Cloud Pro" at ₹2999/mo with 60 min/day Railway if demand grows

---

## 17. automation/linkedin.py, naukri.py, gmail_client.py, ai_client.py — UNCHANGED

---

## 18. Key Patterns & Conventions — UNCHANGED

---

## 19. Key SQL Migrations

```sql
-- Add execution_mode to tasks
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_mode TEXT DEFAULT 'own_machine';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS railway_job_id TEXT;

-- Add execution preference to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_execution_mode TEXT DEFAULT 'own_machine';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS railway_configured BOOL DEFAULT FALSE;

-- Add railway_minutes to plan_limits (run after seeding)
INSERT INTO plan_limits (plan_id, action_type, daily_limit)
SELECT id, 'railway_minutes', 
  CASE slug 
    WHEN 'trial'   THEN 5
    WHEN 'free'    THEN 5
    WHEN 'normal'  THEN 15
    WHEN 'premium' THEN 30
  END
FROM plans WHERE slug IN ('trial', 'free', 'normal', 'premium');

-- New tables
CREATE TABLE IF NOT EXISTS railway_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  task_id UUID REFERENCES tasks(id),
  railway_run_id TEXT,
  status TEXT DEFAULT 'pending',
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ,
  duration_seconds INT,
  screenshot_count INT DEFAULT 0,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS railway_daily_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  usage_date DATE DEFAULT CURRENT_DATE,
  minutes_used NUMERIC(6,2) DEFAULT 0,
  UNIQUE(user_id, usage_date)
);

-- RLS for new tables
ALTER TABLE railway_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE railway_daily_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own sessions" ON railway_sessions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users see own usage" ON railway_daily_usage FOR ALL USING (auth.uid() = user_id);
```

---

## 20. Dependencies — UNCHANGED

---

## 21. Railway Account Setup (For Admin/Developer)

**One-time setup by you (the developer):**

1. Go to [railway.app](https://railway.app) → create account (free)
2. Create a new Project
3. Add a new Service → deploy from GitHub repo (your automation/ + taskrunner/ folder)
4. Set environment variables in Railway service:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `ANTHROPIC_API_KEY`
   - `SCREENSHOT_MODE=true`
5. Enable "Public Networking" on the service → copy the public URL
6. From Account Settings → Tokens → create API token
7. Copy: **API Token**, **Project ID**, **Service ID**, **Service URL**
8. Add all 4 to your `.env.local`

**Users do NOT need a Railway account.** They just use your deployed Railway service via your web app. The "Railway Setup" for users is just entering the service URL you provide them (or it's hardcoded — your choice).

---

## 22. Recent Session Changes

| Change | File(s) | What Changed |
|--------|---------|-------------|
| Cutoff marks sent to AI | `lib/ai.ts`, `page.tsx`, `route.ts` | Added `cutoff_marks` to `StudentInput` |
| Model routing | `lib/ai.ts`, `ai_client.py`, `gmail_client.py` | Haiku for parsing; Sonnet for reasoning |
| Model constants exported | `lib/ai.ts`, `interview-prep/route.ts` | `HAIKU_MODEL`/`SONNET_MODEL` exported |
| Dream College Feasibility | `lib/ai.ts`, `page.tsx`, `route.ts` | Step 5 Pathfinder; `FavoriteCollegeAnalysis` type |
| JSON truncation fix | `lib/ai.ts` | `predictCareer` 3000→8000, `predictPlacement` 3000→6000 |
| `_validate_fill` helper | `automation/ai_client.py` | Logs fills; Haiku to CONFIRM/CORRECT |
| `_build_user_profile` fallback | `automation/linkedin.py` | Extracts profile from resume_text |
| **Railway execution mode** | Multiple (see sections 6-16) | Cloud browser option; screenshot streaming; Railway quota per plan |

---

*Last updated: March 25, 2026*
