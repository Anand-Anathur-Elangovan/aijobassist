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
│   │   ├── agent/page.tsx      # Task runner / bot control panel
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
│   │   ├── ai/
│   │   │   ├── analyze-jd/route.ts
│   │   │   ├── career-copilot/route.ts
│   │   │   ├── cover-letter/route.ts
│   │   │   ├── interview-prep/route.ts
│   │   │   ├── match-score/route.ts
│   │   │   ├── parse-resume/route.ts
│   │   │   ├── placement-prep/route.ts
│   │   │   ├── skill-gap/route.ts
│   │   │   ├── tailor-resume/route.ts
│   │   │   └── tailor-session/route.ts
│   │   ├── billing/
│   │   │   ├── create-order/route.ts
│   │   │   ├── quota/
│   │   │   ├── subscription/
│   │   │   ├── verify-payment/
│   │   │   └── webhook/
│   │   ├── gmail/trigger/
│   │   └── job-history/reset/
│   ├── contact/page.tsx
│   ├── landing/page.tsx        # Public landing page
│   ├── login/page.tsx          # Supabase Auth login/signup
│   ├── onboarding/page.tsx     # First-time user setup
│   ├── privacy/page.tsx
│   ├── refund/page.tsx
│   └── terms/page.tsx
├── automation/                 # Python bot (Playwright browser automation)
│   ├── ai_client.py            # Claude API wrapper — all AI logic
│   ├── gmail_client.py         # Gmail IMAP/SMTP scanner & responder
│   ├── human.py                # Human-like interaction helpers (delays, scrolling)
│   ├── linkedin.py             # LinkedIn job search + apply automation
│   ├── naukri.py               # Naukri.com apply automation
│   ├── resume_parser.py        # PDF/DOCX → text extraction
│   └── resume_tailor.py        # Standalone Claude resume optimizer (uses anthropic SDK)
├── components/
│   ├── AuthGuard.tsx           # Redirects unauthenticated users to /login
│   ├── NavBar.tsx              # Top navigation bar
│   └── SubscriptionGuard.tsx   # Blocks access based on plan features
├── context/
│   └── AuthContext.tsx         # Supabase session state + refreshSession hook
├── lib/
│   ├── ai.ts                   # ALL AI functions — Claude Haiku/Sonnet routing
│   ├── api-auth.ts             # Server-side auth, quota enforcement, getServiceSupabase
│   ├── billing.ts              # Subscription, quota, Razorpay helpers
│   └── supabase.ts             # Supabase browser client
├── taskrunner/                 # Python task scheduler (polls Supabase)
│   ├── main.py                 # Infinite loop — polls tasks, spawns workers
│   ├── task_runner.py          # Dispatches task types to automation modules
│   ├── api_client.py           # Supabase REST calls from Python
│   ├── build_agent.py          # PyInstaller build script
│   └── agent_entry.py          # Entry point for compiled EXE
├── middleware.ts               # Session cookie refresh (no redirects — AuthGuard handles that)
├── next.config.js
├── tailwind.config.ts
├── schema.sql                  # Core tables
├── schema_additions.sql        # Extended tables + RPC functions
├── schema_billing.sql          # Billing/subscription tables
└── schema_career_copilot.sql   # Career Copilot tables
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
```

**Super admins (bypass all quotas):**
- `kaviyasaravanan01@gmail.com`
- `anandanathurelangovan94@gmail.com`

---

## 4. Database Schema

### Core Tables (`schema.sql`)

**`resumes`**
```
id, user_id, title, content JSONB, parsed_text TEXT, created_at, updated_at
```

**`jobs`**
```
id, user_id, company, role, url, status TEXT DEFAULT 'SAVED', metadata JSONB, created_at, updated_at
```

**`applications`**
```
id, user_id, job_id, resume_id, stage TEXT DEFAULT 'APPLIED', notes,
payload JSONB, cover_letter_id, jd_text, ats_score, follow_up_at,
applied_at, updated_at
```

**`tasks`**
```
id, user_id, application_id, type TEXT, status task_status DEFAULT 'PENDING',
input JSONB, output JSONB, error TEXT,
logs JSONB DEFAULT '[]',           -- append-only bot log stream
progress INT DEFAULT 0,            -- 0-100
current_job TEXT,                  -- "Company — Role" being processed
custom_prompt_override TEXT,       -- user can update mid-run
paused BOOLEAN DEFAULT FALSE,
stop_requested BOOLEAN DEFAULT FALSE,
created_at, completed_at
```
- `task_status` ENUM: `PENDING | RUNNING | DONE | FAILED`
- RPC: `append_task_log(task_id UUID, entry JSONB)` — atomic log append

### Extended Tables (`schema_additions.sql`)

**`job_history`**
```
id, user_id, platform TEXT, job_url TEXT,
status TEXT DEFAULT 'skipped',
  -- 'applied' | 'skipped' | 'smart_match' | 'mode_skip'
skip_reason TEXT, metadata JSONB, created_at
UNIQUE(user_id, platform, job_url)
```

**`resume_versions`**
```
id, user_id, resume_id, job_id, version_name,
original_text, tailored_text, tailored_content JSONB,
ats_score INT, missing_skills TEXT[], created_at
```

**`cover_letters`**
```
id, user_id, job_id,
type TEXT  -- 'cover_letter' | 'intro_message' | 'linkedin_intro' | 'email_followup'
content TEXT, metadata JSONB, created_at
```

**`jd_analyses`** (cached to avoid re-calling AI for same JD)
```
id, user_id, job_id, jd_text,
required_skills TEXT[], nice_to_have TEXT[], keywords TEXT[],
responsibilities TEXT[], seniority TEXT, created_at
```

**`company_watchlist`**
```
id, user_id, company, keywords TEXT[], platform TEXT DEFAULT 'both', active BOOL, created_at
UNIQUE(user_id, company)
```

**`notifications`**
```
id, user_id,
type TEXT  -- 'new_job' | 'application_complete' | 'follow_up' | 'resume_ready' | 'interview' | 'general'
title, message, read BOOL DEFAULT FALSE, metadata JSONB, created_at
```

### Billing Tables (`schema_billing.sql`)

**`plans`**
```
id, slug TEXT UNIQUE, name, description,
price_monthly INT,   -- paise (INR): 99900 = ₹999
price_weekly INT,
is_active BOOL, sort_order INT,
features JSONB, created_at
```
Seeded plans:
| slug | name | Monthly | Weekly |
|------|------|---------|--------|
| `trial` | Free Trial | ₹0 (10 days) | — |
| `free` | Free | ₹0 | — |
| `normal` | Pro | ₹999 | ₹349 |
| `premium` | Premium | ₹1999 | ₹699 |

**`plan_limits`**
```
id, plan_id, action_type TEXT, daily_limit INT
UNIQUE(plan_id, action_type)
```
Action types: `auto_apply | semi_auto | ai_tailor | gmail_scan | cover_letter | jd_analysis`

Daily limits:
| action | trial | free | pro | premium |
|--------|-------|------|-----|---------|
| auto_apply | 10 | 0 | 25 | 80 |
| semi_auto | 20 | 10 | 75 | 200 |
| ai_tailor | 5 | 1 | 15 | 40 |
| gmail_scan | 5 | 3 | 25 | 75 |
| cover_letter | 5 | 2 | 15 | 40 |
| jd_analysis | 10 | 5 | 50 | 999 |

**`subscriptions`**
```
id, user_id, plan_id, status TEXT DEFAULT 'active',
  -- 'active' | 'cancelled' | 'expired' | 'past_due'
billing_cycle TEXT  -- 'weekly' | 'monthly' | 'trial'
razorpay_subscription_id, razorpay_customer_id,
trial_ends_at, current_period_start, current_period_end,
cancelled_at, created_at, updated_at
UNIQUE INDEX on (user_id) WHERE status IN ('active', 'past_due')
```

**`usage_events`** — granular log of every billable action
```
id, user_id, action_type, metadata JSONB, created_at
```

**`daily_usage`** — fast materialized counter for quota checks
```
id, user_id, action_type, usage_date DATE, count INT
UNIQUE(user_id, action_type, usage_date)
```

**`payments`** — Razorpay payment records
```
id, user_id, subscription_id, razorpay_payment_id, razorpay_order_id,
razorpay_signature, amount INT (paise), currency TEXT, status, metadata JSONB, created_at
```

**`user_profiles`**
```
id, user_id UNIQUE, full_name, phone, country TEXT DEFAULT 'India',
avatar_url, onboarding_done BOOL, role TEXT DEFAULT 'user',
  -- 'user' | 'admin'
job_preferences JSONB,  -- desired_roles, locations, etc. (30+ fields from dashboard)
app_mode TEXT DEFAULT 'job_seeker',
  -- 'job_seeker' | 'student'
created_at, updated_at
```

**Supabase RPC Functions:**
- `check_quota(user_id, action_type)` → `{ allowed, used, limit, remaining }`
- `increment_usage(user_id, action_type)` → `INT` (new count)
- `append_task_log(task_id, entry)` → `VOID` (atomic log append)
- `handle_new_user()` — trigger: creates user_profile + trial subscription on signup

### Career Copilot Tables (`schema_career_copilot.sql`)

**`student_profiles`**
```
id, user_id UNIQUE,
student_name, state, board TEXT DEFAULT 'CBSE',
marks_10th NUMERIC(5,2), marks_12th NUMERIC(5,2),
stream_12th TEXT,    -- 'CS Group' | 'PCM' | 'PCB' | 'PCMB' | 'Commerce' | 'Arts / Humanities'
entrance_exams TEXT[], community TEXT DEFAULT 'OC',
quota TEXT[], interests TEXT[],
favorite_colleges TEXT[],     -- added in session — for Dream College Feasibility
created_at, updated_at
```

**`career_predictions`**
```
id, user_id, student_profile_id,
input_snapshot JSONB,
courses JSONB,         -- CareerCourseResult[]
colleges JSONB,        -- CareerCollegeResult[]
exam_roadmap JSONB,    -- CareerExamRoadmap[]
strategy JSONB,        -- CareerStrategy
favorite_college_analysis JSONB,  -- FavoriteCollegeAnalysis[] (added in session)
is_fallback BOOL DEFAULT FALSE,
created_at
```

---

## 5. lib/ai.ts — AI Functions

### Model Constants (exported)
```typescript
export const HAIKU_MODEL  = "claude-haiku-4-5";   // cheap, fast
export const SONNET_MODEL = "claude-sonnet-4-5";  // accurate, expensive
```

### Internal Helper
```typescript
callClaude(prompt: string, maxTokens = 4096, model = SONNET_MODEL): Promise<string>
```

### Exported Interfaces

**`StudentInput`**
```typescript
{
  student_name, state, board,
  marks_10th?, marks_12th?, stream_12th?,
  cutoff_marks?: { math?, physics?, chemistry?, neet? },  // ← added in session
  entrance_exams: string[],
  community, quota: string[], interests: string[],
  favorite_colleges?: string[]
}
```

**`CareerPredictionResult`**
```typescript
{
  courses: CareerCourseResult[],
  colleges: CareerCollegeResult[],
  exam_roadmap: CareerExamRoadmap[],
  strategy: CareerStrategy,
  favorite_college_analysis?: FavoriteCollegeAnalysis[],
  message?, is_fallback?
}
```

**`FavoriteCollegeAnalysis`**
```typescript
{
  college_name, feasibility: "Reachable"|"Stretch"|"Very Tough"|"Out of Range",
  your_estimated_cutoff, required_cutoff, gap_summary,
  historical_cutoffs: { year, cutoff, category }[],
  alternative_routes: string[],
  similar_colleges: string[],
  accessible_branches: string[]
}
```

**`PlacementPrepInput`**
```typescript
{ college, degree, branch, graduation_year, cgpa?, placement_exams: string[], target_role? }
```

**`PlacementPrepResult`**
```typescript
{
  amcat_prep: PlacementResource[],
  elitmus_prep: PlacementResource[],
  campus_drive_calendar: DriveTiming[],
  off_campus_portals: OffCampusPortal[],
  four_week_plan: PlacementWeekPlan[],
  hr_tips: string[], resume_tips: string[], is_fallback?
}
```

### Exported Functions & Model Routing

| Function | Model | maxTokens | Task |
|----------|-------|-----------|------|
| `analyzeJD(jdText)` | **Haiku** | 1024 | Extract required_skills, nice_to_have, keywords, seniority |
| `matchScore(resumeText, jdText)` | **Haiku** | 1024 | ATS score 0-100, matching/missing skills |
| `tailorResume(resumeText, jdText, customPrompt?)` | **Sonnet** | 4096 | Rewrite resume bullets + summary |
| `generateCoverLetter(resumeText, jdText, company?, role?)` | **Sonnet** | 2048 | Cover letter + LinkedIn intro + email subject |
| `predictCareer(input: StudentInput)` | **Sonnet** | 8000 | College Pathfinder — courses, colleges, exams, strategy, dream college feasibility |
| `skillGapWithLearning(resumeText, jdText)` | **Sonnet** | 3000 | Match score + 2-week learning plan |
| `predictPlacement(input: PlacementPrepInput)` | **Sonnet** | 6000 | Placement prep — AMCAT/eLitmus, campus calendar, 4-week plan |

**All functions have keyword-based mock fallbacks when `ANTHROPIC_API_KEY` is absent.**

---

## 6. API Routes

### AI Routes (all require `Authorization: Bearer <token>`)

| Route | Method | Quota Action | Key Inputs | Returns |
|-------|--------|-------------|------------|---------|
| `/api/ai/analyze-jd` | POST | `jd_analysis` | `jd_text` | `JDAnalysis` |
| `/api/ai/match-score` | POST | `jd_analysis` | `resume_text, jd_text` | `MatchScoreResult` |
| `/api/ai/tailor-resume` | POST | `ai_tailor` | `resume_text, jd_text, custom_prompt?` | `TailoredResumeResult` |
| `/api/ai/cover-letter` | POST | `cover_letter` | `resume_text, jd_text, company?, role?` | `CoverLetterResult` |
| `/api/ai/skill-gap` | POST | `jd_analysis` | `resume_text, jd_text` | `SkillGapResult` |
| `/api/ai/parse-resume` | POST | — | `file` (multipart PDF/DOCX) | `{ text, skills[], ... }` |
| `/api/ai/interview-prep` | POST | `jd_analysis` | `jd_text, resume_text?, company?, role?` | `{ questions[10], key_topics, preparation_tips }` — uses **Sonnet** directly via Anthropic SDK |
| `/api/ai/career-copilot` | GET | — | Bearer token | `{ profile, last_prediction }` |
| `/api/ai/career-copilot` | POST | — | All `StudentInput` fields + `cutoff_marks?` + `favorite_colleges?` | `CareerPredictionResult` — upserts `student_profiles`, inserts `career_predictions` |
| `/api/ai/placement-prep` | POST | — | `PlacementPrepInput` fields | `PlacementPrepResult` |
| `/api/ai/tailor-session` | POST | `ai_tailor` | session-based tailoring | session result |

### Billing Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/billing/create-order` | POST | Create Razorpay order |
| `/api/billing/verify-payment` | POST | Verify Razorpay signature, activate subscription |
| `/api/billing/webhook` | POST | Razorpay webhook handler |
| `/api/billing/subscription` | GET | Get current user subscription |
| `/api/billing/quota` | GET | Get current quota usage |

### Other
- `/api/agent-key` — Agent API key management
- `/api/gmail/trigger` — Trigger Gmail scan
- `/api/job-history/reset` — Reset job history

---

## 7. lib/api-auth.ts

```typescript
getServiceSupabase()                              // returns service-role Supabase client
getAuthUser(req: NextRequest)                     // extracts user from Bearer token
enforceQuota(userId, actionType, userEmail?)      // returns null (allowed) or NextResponse 429
```

Super admins bypass `enforceQuota` entirely.

---

## 8. lib/billing.ts

```typescript
getPlans()                           // all active plans
getPlanLimits(planId)                // limits for a plan
getUserSubscription(userId)          // active subscription with plan details
getSubscriptionWithPlan(userId)      // subscription + plan, falls back to free
checkUserQuota(userId, actionType)   // QuotaCheck { allowed, used, limit, remaining }
createRazorpayOrder(amount, userId)  // creates order via Razorpay
```

---

## 9. context/AuthContext.tsx

```typescript
// Exports:
useAuth() → { user: User|null, session: Session|null, loading: boolean, refreshSession() }
AuthProvider   // wraps app in app/layout.tsx
```

---

## 10. Components

**`AuthGuard`** — Wraps `(protected)/layout.tsx`. Redirects to `/login` if no session.

**`NavBar`** — Top nav; shows links based on `user.app_mode`. `job_seeker` links differ from `student` links.

**`SubscriptionGuard`** — Checks `features` JSONB on active plan. Blocks page if feature not enabled.

---

## 11. automation/ai_client.py

**Model constants:**
```python
HAIKU_MODEL  = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-5"
```

**Circuit breaker:** `_API_DISABLED` global — set True on permanent API errors (quota, invalid key, rate limit). All calls skip immediately.

**Core helpers:**
```python
_call_claude(prompt, max_tokens=4096, model=SONNET_MODEL) → dict   # JSON response
call_claude(prompt, max_tokens=1024, model=SONNET_MODEL)  → str    # raw text
_has_api_key()  → bool
```

**Function → Model routing:**

| Function | Model | Tokens | Purpose |
|----------|-------|--------|---------|
| `analyze_resume(text)` | **Haiku** | default | skills, years_exp, email, education |
| `extract_education(text)` | **Haiku** | 1500 | structured education entries |
| `extract_employment(text)` | **Haiku** | 2000 | structured employment entries |
| `analyze_jd(text)` | **Haiku** | default | required_skills, nice_to_have, seniority |
| `match_score(resume, jd)` | **Haiku** | default | score 0-100, matching/missing skills |
| `analyze_and_fill_form(html, profile)` | **Haiku** | 1500 | CSS selectors + fill actions for ATS forms |
| `claude_answer_question(q, opts, profile)` | **Haiku** | 200 | pick best option or compose short answer |
| `_validate_fill(field, value)` | **Haiku** | 60 | CONFIRM or CORRECT a fill value vs resume |
| `tailor_resume(resume, jd)` | **Sonnet** | 6000 | full resume rewrite |
| `generate_cover_letter(resume, jd, co, role)` | **Sonnet** | default | cover letter + intro + linkedin |
| `interview_prep(jd, resume?)` | **Sonnet** | 5000 | 10 questions + STAR answers |

**`claude_answer_question` direct-lookup fields (no API call):**
LinkedIn URL, GitHub URL, Portfolio URL, Name, Email, Phone, Expected CTC, Current CTC, Gender/Diversity — these are read directly from `user_profile` dict and validated with `_validate_fill`.

**`_validate_fill` logic:**
1. Always prints `[FILL] 'question' → Field: 'value'`
2. Skips Claude for unambiguous fields (URLs, Name, Email, Phone, CTC, Gender)
3. For substantive fields (City, Company, Position, YoE, Notice, Education, School, GradYear): calls Claude Haiku with `max_tokens=60` → `CONFIRM` or `CORRECT: <value>`

---

## 12. automation/linkedin.py

**Key functions:**
- `apply_linkedin_jobs(task_input)` — main entrypoint; searches + applies to jobs
- `_build_user_profile(task_input)` — builds profile dict from `task_input`; if key fields empty AND resume_text present AND not already extracted → extracts from resume once (cached in `task_input["_user_profile_cache"]`)
- `claude_answer_question` used for: free-text unknown fields, radio buttons, dropdowns where direct lookup fails

**task_input keys used:**
```
user_id, task_id, resume_file_url, resume_text, full_name, email, phone,
linkedin_url, github_url, portfolio_url, current_city, current_company,
current_position, years_experience, notice_period, salary_expectation,
current_ctc, highest_education, school, graduation_year, degree, major,
job_title_keywords[], locations[], apply_types[]: 'easy_apply'|'external',
max_jobs INT, min_match_score INT (0-100)
```

---

## 13. automation/naukri.py

Applies to Naukri.com listings. Uses `analyze_and_fill_form` (Haiku) for company ATS forms. Falls back to dumb fill if Claude fails.

---

## 14. automation/gmail_client.py

**Functions:**
```python
_ai_classify(subject, body)      → str   # uses Haiku — ACKNOWLEDGMENT|INTERVIEW_INVITE|REJECTION|SCHEDULE_REQUEST|OFFER|GENERAL
_ai_generate_reply(...)          → str   # uses Sonnet — 3-5 sentence professional reply
_ai_summarise(subject, body)     → str   # uses Haiku — one-sentence summary
scan_job_emails(gmail, password) → list  # IMAP scan; returns classified emails
send_reply(gmail, password, ...)         # SMTP reply send
```

---

## 15. automation/resume_tailor.py

Standalone module. Uses `anthropic` SDK directly (not requests). `_call_claude` always uses `claude-sonnet-4-5` (tailoring needs accuracy). Provides `tailor_resume_for_job(pdf_path, jd_text)` pipeline: PDF→text → match score before → Claude tailoring → match score after.

---

## 16. taskrunner/

**`main.py`** — polls Supabase every N seconds for `PENDING` tasks → calls `task_runner.run_task(task)`

**`task_runner.py`** — dispatches by `task.type`:
| Task Type | Handler | Quota Action |
|-----------|---------|-------------|
| `AUTO_APPLY` | `_handle_auto_apply` | `auto_apply` |
| `TAILOR_AND_APPLY` | `_handle_tailor_and_apply` (sets `tailor_resume=True`) | `semi_auto` |
| `TAILOR_RESUME` | `_handle_tailor_resume` | `ai_tailor` |
| `GMAIL_DAILY_CHECK` | `_handle_gmail_daily_check` | `gmail_scan` |

**`api_client.py`** — Supabase REST helpers (no Claude):
```python
SUPABASE_URL, HEADERS (service role)
fetch_pending_tasks()
fetch_latest_resume(user_id)
update_task(task_id, status, output?, error?)
push_log(task_id, msg, level?)
check_quota(user_id, action_type)
fetch_user_email(user_id)
```

---

## 17. app/(protected)/career-copilot/page.tsx

### State
```typescript
mode: "pathfinder" | "placement"
step: 1|2|3|4|5   // FormStep
form: StudentForm  // { student_name, state, board, marks_10th, marks_12th, stream_12th,
                   //   entrance_exams[], community, quota[], interests[], favorite_colleges[] }
cutoffMarks: { math, physics, chemistry, neet }  // separate state, NOT in form
result: CareerPredictionResult | null
activeTab: "courses"|"colleges"|"exams"|"strategy"|"favorites"
placementForm: PlacementForm
placementResult: PlacementPrepResult | null
favCollegeInput: string
showCutoff: boolean
```

### Steps (Pathfinder)
1. **Personal Info** — name, state, board, community, quota
2. **Academic Marks** — 10th %, 12th %, stream, Cutoff Calculator (expandable — math/physics/chemistry/neet inputs, compute TN TNEA cutoff on-the-fly)
3. **Entrance Exams** — multi-select JEE/NEET/VITEEE etc.
4. **Interests** — 59 preset + custom add
5. **Dream Colleges** — add up to 5, analyzed by AI for feasibility

### Cutoff Calculator (in Step 2)
- Local state `cutoffMarks` — **NOT in form**, sent separately in POST body as `cutoff_marks`
- Compute TN TNEA formula: `Maths÷2 + Physics÷4 + Chemistry÷4` (State Board max 200)
- NEET tier preview (680+, 600+, 500+, 400+)
- On submit: `cutoff_marks` is included in `handlePredict()` POST body

### Results Tabs
- 🎓 Courses, 🏛️ Colleges, 📝 Exam Prep, 🗺️ Strategy
- ⭐ My Colleges (conditional — only shown when `result.favorite_college_analysis?.length > 0`)

### FavoriteCollegeCard
Expandable card showing: feasibility badge + gap summary, your cutoff vs required, historical cutoffs table (3 years), alternative routes, similar colleges (chips), accessible branches (chips).

### FEASIBILITY_COLORS
```typescript
"Reachable" → emerald, "Stretch" → amber, "Very Tough" → orange, "Out of Range" → red
```

---

## 18. Key Patterns & Conventions

### Authentication Flow
1. `middleware.ts` refreshes session cookies on every request (no redirects)
2. `AuthGuard` client-side redirects to `/login` if `!user && !loading`
3. API routes call `getAuthUser(req)` → verify Bearer token via Supabase service role

### API Route Pattern
```typescript
const user = await getAuthUser(req);
if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
const quotaError = await enforceQuota(user.id, "action_type", user.email);
if (quotaError) return quotaError;
// ... do work ...
```

### Python Model Routing Decision
- **Haiku**: extraction, parsing, classification, form-filling Q&A, match scoring, validation
- **Sonnet**: tailoring resumes, cover letters, interview prep, career/placement prediction

### Supabase Client Separation
- `lib/supabase.ts` → browser client (anon key) — used in client components
- `lib/api-auth.ts` `getServiceSupabase()` → service-role client — used only in server/API routes
- `taskrunner/api_client.py` → service-role REST calls from Python bot

### task_input Dict (passed to automation modules)
All 30+ fields from `user_profiles.job_preferences` JSONB are flattened into `task_input`. The bot reads: `resume_file_url`, `full_name`, `email`, `phone`, `linkedin_url`, `github_url`, `portfolio_url`, `current_city`, `current_company`, `current_position`, `years_experience`, `notice_period`, `salary_expectation`, `current_ctc`, `highest_education`, `school`, `graduation_year`, `degree`, `major`, `job_title_keywords`, `locations`, `apply_types`, `max_jobs`, `min_match_score`.

---

## 19. Key SQL Migrations Run in This Project

```sql
-- student_profiles: added in session
ALTER TABLE student_profiles ADD COLUMN IF NOT EXISTS favorite_colleges jsonb DEFAULT '[]';

-- career_predictions: added in session
ALTER TABLE career_predictions ADD COLUMN IF NOT EXISTS favorite_college_analysis jsonb;
```

---

## 20. Dependencies (`package.json`)

```json
{
  "@anthropic-ai/sdk": "^0.80.0",
  "@supabase/auth-helpers-nextjs": "^0.15.0",
  "@supabase/ssr": "^0.3.0",
  "@supabase/supabase-js": "^2.43.4",
  "mammoth": "^1.12.0",      // DOCX → text
  "pdf-parse": "^2.4.5",     // PDF → text
  "razorpay": "^2.9.6",
  "next": "14.2.35",
  "react": "^18",
  "react-dom": "^18"
}
```

---

## 21. Recent Session Changes (to keep in sync)

| Change | File(s) | What Changed |
|--------|---------|-------------|
| Cutoff marks sent to AI | `lib/ai.ts`, `page.tsx`, `route.ts` | Added `cutoff_marks` to `StudentInput`; `handlePredict` sends it; route extracts it; prompt includes subject marks + NEET score |
| Model routing | `lib/ai.ts`, `ai_client.py`, `gmail_client.py` | Haiku for parsing/extraction/Q&A; Sonnet for complex reasoning/writing |
| Model constants exported | `lib/ai.ts`, `interview-prep/route.ts` | `HAIKU_MODEL`/`SONNET_MODEL` now exported; interview-prep route uses `SONNET_MODEL` import |
| Dream College Feasibility | `lib/ai.ts`, `page.tsx`, `route.ts` | Step 5 in Pathfinder; `FavoriteCollegeAnalysis` type; `⭐ My Colleges` tab |
| JSON truncation fix | `lib/ai.ts` | `predictCareer` 3000→8000, `predictPlacement` 3000→6000 tokens |
| `_validate_fill` helper | `automation/ai_client.py` | Logs all direct fills; calls Haiku to CONFIRM/CORRECT substantive fields |
| `_build_user_profile` fallback | `automation/linkedin.py` | Extracts profile from resume_text when dashboard fields empty |
| **Railway Cloud Execution** | Multiple | See Section 22 below |

---

## 22. Railway Cloud Execution Feature

### New Files Created
| File | Purpose |
|------|---------|
| `schema_railway.sql` | SQL to run in Supabase: adds columns to tasks + user_profiles, new tables, RPC |
| `lib/railway.ts` | Server-side Railway helpers: quota check, increment, trigger, stop, ping |
| `app/api/railway/trigger/route.ts` | POST — creates session, updates task, calls Railway service |
| `app/api/railway/stop/route.ts` | POST — stops run, computes duration, increments usage |
| `app/api/railway/status/route.ts` | GET — returns session status + task progress + screenshot. Also handles `?ping=true` |
| `app/api/railway/stream/route.ts` | GET SSE — polls `railway_sessions.latest_screenshot` every 1s, streams events |
| `components/ExecutionModeModal.tsx` | Modal: choose Own Machine vs Railway Cloud, quota bar, remember choice |
| `app/(protected)/agent/setup/page.tsx` | 3-step wizard: info → test connection → done (sets railway_configured=true) |
| `automation/screenshot_streamer.py` | Runs in Railway container; pushes base64 JPEG screenshots to Supabase every 1s |
| `.env.local` | Mock Railway env vars (see Section 3) |

### Modified Files
| File | Change |
|------|--------|
| `app/(protected)/agent/page.tsx` | Added Railway banner, Cloud Quick Launch panel, live screenshot viewer, logs panel, SSE stream, ExecutionModeModal |
| `taskrunner/task_runner.py` | Added `execution_mode='railway'` skip guard at top of `run_task()` |

### New DB Columns (run schema_railway.sql)
- `tasks.execution_mode TEXT DEFAULT 'own_machine'`
- `tasks.railway_job_id TEXT`
- `user_profiles.preferred_execution_mode TEXT DEFAULT 'own_machine'`
- `user_profiles.railway_configured BOOL DEFAULT FALSE`
- New table: `railway_sessions` (id, user_id, task_id, railway_run_id, status, started_at, ended_at, duration_seconds, screenshot_count, latest_screenshot, error)
- New table: `railway_daily_usage` (id, user_id, usage_date, minutes_used)
- New plan_limits rows: `action_type='railway_minutes'` per plan (trial/free=5, pro=15, premium=30)
- New RPC: `increment_railway_minutes(p_user_id, p_date, p_minutes)`

### Railway Minute Limits
| Plan | Minutes/day |
|------|-------------|
| Trial / Free | 5 |
| Pro (normal) | 15 |
| Premium | 30 |
| Super admin | 120 (hardcoded bypass in lib/railway.ts) |

---

*Last updated: March 25, 2026*
