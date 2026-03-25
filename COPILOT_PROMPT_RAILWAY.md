# VantaHire — Railway Cloud Execution Mode Feature
## Copilot Prompt for Claude Sonnet 4.6

> Read CODEBASE_CONTEXT.md fully before writing a single line of code.
> This feature is purely ADDITIVE. Do NOT break or modify existing automation flows.

---

## What You Are Building

Add a **"Run on Railway" option** to VantaHire so users can run their job automation in the cloud instead of on their local machine. When a user triggers AUTO_APPLY or TAILOR_AND_APPLY, they now choose where the automation runs:

- **Own Machine** → existing behavior, unchanged (user runs the .exe locally)
- **Railway Cloud** → automation runs on Railway server, user watches a live screenshot stream in the browser

This is optional and recommended. Users on all plans get Railway access with daily minute limits.

---

## Execution Rules (CRITICAL)

- If `execution_mode = 'own_machine'` → do exactly what the code does today. Touch nothing.
- If `execution_mode = 'railway'` → trigger Railway API, stream screenshots back.
- These two paths must NEVER interfere. A flag in the task row (`execution_mode`) separates them.
- The `.exe` / `taskrunner/task_runner.py` must check `execution_mode` and skip Railway tasks silently.

---

## Daily Railway Minute Limits by Plan

| Plan slug | railway_minutes/day |
|-----------|---------------------|
| trial | 5 |
| free | 5 |
| normal (Pro) | 15 |
| premium | 30 |
| super admin | 120 (2 hours) — hardcoded bypass in lib/railway.ts |

Super admins: `kaviyasaravanan01@gmail.com`, `anandanathurelangovan94@gmail.com` — bypass all quota checks.

---

## Files to Create

### 1. `schema_railway.sql`

```sql
-- Add to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_mode TEXT DEFAULT 'own_machine';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS railway_job_id TEXT;

-- Add to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_execution_mode TEXT DEFAULT 'own_machine';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS railway_configured BOOL DEFAULT FALSE;

-- Add railway_minutes to plan_limits for all plans
INSERT INTO plan_limits (plan_id, action_type, daily_limit)
SELECT p.id, 'railway_minutes',
  CASE p.slug
    WHEN 'trial'   THEN 5
    WHEN 'free'    THEN 5
    WHEN 'normal'  THEN 15
    WHEN 'premium' THEN 30
    ELSE 5
  END
FROM plans p
WHERE p.slug IN ('trial', 'free', 'normal', 'premium')
ON CONFLICT (plan_id, action_type) DO NOTHING;

-- Railway sessions table
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

-- Daily usage tracker for Railway minutes
CREATE TABLE IF NOT EXISTS railway_daily_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  usage_date DATE DEFAULT CURRENT_DATE,
  minutes_used NUMERIC(6,2) DEFAULT 0,
  UNIQUE(user_id, usage_date)
);

-- RLS
ALTER TABLE railway_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE railway_daily_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users own sessions" ON railway_sessions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users own usage" ON railway_daily_usage FOR ALL USING (auth.uid() = user_id);
```

---

### 2. `lib/railway.ts`

```typescript
import { getServiceSupabase } from './api-auth'

const RAILWAY_SERVICE_URL = process.env.RAILWAY_SERVICE_URL!
const RAILWAY_API_TOKEN = process.env.RAILWAY_API_TOKEN!
const SUPER_ADMINS = ['kaviyasaravanan01@gmail.com', 'anandanathurelangovan94@gmail.com']
const ADMIN_DAILY_LIMIT = 120 // minutes

export interface RailwayQuotaCheck {
  allowed: boolean
  used: number      // minutes used today
  limit: number     // daily limit in minutes
  remaining: number
}

// Check if user can use Railway today (respects plan limits)
export async function checkRailwayQuota(userId: string, userEmail?: string): Promise<RailwayQuotaCheck> {
  const supabase = getServiceSupabase()

  // Super admin bypass — 120 min/day
  if (userEmail && SUPER_ADMINS.includes(userEmail)) {
    const { data } = await supabase
      .from('railway_daily_usage')
      .select('minutes_used')
      .eq('user_id', userId)
      .eq('usage_date', new Date().toISOString().split('T')[0])
      .single()
    const used = data?.minutes_used ?? 0
    return { allowed: used < ADMIN_DAILY_LIMIT, used, limit: ADMIN_DAILY_LIMIT, remaining: Math.max(0, ADMIN_DAILY_LIMIT - used) }
  }

  // Get plan limit for railway_minutes
  const { data: sub } = await supabase
    .from('subscriptions')
    .select('plan_id')
    .eq('user_id', userId)
    .in('status', ['active', 'past_due'])
    .single()

  let limit = 5 // default free limit
  if (sub?.plan_id) {
    const { data: planLimit } = await supabase
      .from('plan_limits')
      .select('daily_limit')
      .eq('plan_id', sub.plan_id)
      .eq('action_type', 'railway_minutes')
      .single()
    if (planLimit) limit = planLimit.daily_limit
  }

  // Get today's usage
  const today = new Date().toISOString().split('T')[0]
  const { data: usage } = await supabase
    .from('railway_daily_usage')
    .select('minutes_used')
    .eq('user_id', userId)
    .eq('usage_date', today)
    .single()

  const used = usage?.minutes_used ?? 0
  return { allowed: used < limit, used, limit, remaining: Math.max(0, limit - used) }
}

// Increment Railway usage (called when session ends)
export async function incrementRailwayUsage(userId: string, minutes: number): Promise<void> {
  const supabase = getServiceSupabase()
  const today = new Date().toISOString().split('T')[0]
  await supabase.rpc('increment_railway_minutes', { p_user_id: userId, p_date: today, p_minutes: minutes })
  // RPC: INSERT INTO railway_daily_usage(user_id, usage_date, minutes_used) VALUES(p_user_id, p_date, p_minutes)
  //      ON CONFLICT (user_id, usage_date) DO UPDATE SET minutes_used = railway_daily_usage.minutes_used + EXCLUDED.minutes_used
}

// Trigger Railway automation run
export async function triggerRailwayRun(taskId: string, taskInput: object, sessionId: string): Promise<{ runId: string }> {
  const res = await fetch(`${RAILWAY_SERVICE_URL}/trigger`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${RAILWAY_API_TOKEN}`
    },
    body: JSON.stringify({ task_id: taskId, session_id: sessionId, task_input: taskInput })
  })
  if (!res.ok) throw new Error(`Railway trigger failed: ${res.status}`)
  return res.json()
}

// Stop a running Railway job
export async function stopRailwayRun(runId: string): Promise<void> {
  await fetch(`${RAILWAY_SERVICE_URL}/stop`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${RAILWAY_API_TOKEN}` },
    body: JSON.stringify({ run_id: runId })
  })
}
```

---

### 3. `app/api/railway/trigger/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'
import { checkRailwayQuota, triggerRailwayRun } from '@/lib/railway'

export async function POST(req: NextRequest) {
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { task_id, task_type, task_input } = await req.json()
  if (!task_id || !task_type) return NextResponse.json({ error: 'task_id and task_type required' }, { status: 400 })

  // Check Railway quota
  const quota = await checkRailwayQuota(user.id, user.email)
  if (!quota.allowed) {
    return NextResponse.json({
      error: `Daily Railway limit reached (${quota.used}/${quota.limit} min used). Upgrade your plan for more.`
    }, { status: 429 })
  }

  const supabase = getServiceSupabase()

  // Create railway_session row
  const { data: session, error: sessionErr } = await supabase
    .from('railway_sessions')
    .insert({ user_id: user.id, task_id, status: 'pending' })
    .select()
    .single()
  if (sessionErr) return NextResponse.json({ error: 'Failed to create session' }, { status: 500 })

  // Update task with execution_mode = railway
  await supabase
    .from('tasks')
    .update({ execution_mode: 'railway', status: 'RUNNING' })
    .eq('id', task_id)

  try {
    const { runId } = await triggerRailwayRun(task_id, task_input, session.id)

    // Store Railway run ID
    await supabase
      .from('railway_sessions')
      .update({ railway_run_id: runId, status: 'running' })
      .eq('id', session.id)

    await supabase
      .from('tasks')
      .update({ railway_job_id: runId })
      .eq('id', task_id)

    return NextResponse.json({ success: true, session_id: session.id, railway_run_id: runId, quota })
  } catch (err: any) {
    await supabase.from('railway_sessions').update({ status: 'failed', error: err.message }).eq('id', session.id)
    await supabase.from('tasks').update({ status: 'FAILED', error: err.message }).eq('id', task_id)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
```

---

### 4. `app/api/railway/stop/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'
import { stopRailwayRun, incrementRailwayUsage } from '@/lib/railway'

export async function POST(req: NextRequest) {
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { task_id, session_id } = await req.json()
  const supabase = getServiceSupabase()

  // Get session to find run_id and start time
  const { data: session } = await supabase
    .from('railway_sessions')
    .select('*')
    .eq('id', session_id)
    .eq('user_id', user.id)
    .single()

  if (!session) return NextResponse.json({ error: 'Session not found' }, { status: 404 })

  // Stop the Railway run
  if (session.railway_run_id) {
    await stopRailwayRun(session.railway_run_id)
  }

  // Calculate duration and update records
  const endedAt = new Date()
  const durationSeconds = Math.floor((endedAt.getTime() - new Date(session.started_at).getTime()) / 1000)
  const minutesUsed = Math.ceil(durationSeconds / 60)

  await supabase.from('railway_sessions').update({
    status: 'stopped',
    ended_at: endedAt.toISOString(),
    duration_seconds: durationSeconds
  }).eq('id', session_id)

  await supabase.from('tasks').update({ status: 'DONE', stop_requested: true }).eq('id', task_id)

  // Increment Railway usage
  await incrementRailwayUsage(user.id, minutesUsed)

  return NextResponse.json({ success: true, duration_seconds: durationSeconds, minutes_used: minutesUsed })
}
```

---

### 5. `app/api/railway/stream/route.ts` (Server-Sent Events)

```typescript
import { NextRequest } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'

export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const user = await getAuthUser(req)
  if (!user) return new Response('Unauthorized', { status: 401 })

  const sessionId = req.nextUrl.searchParams.get('session_id')
  if (!sessionId) return new Response('session_id required', { status: 400 })

  const supabase = getServiceSupabase()

  // Subscribe to Supabase realtime broadcast channel for this session
  // The Railway container pushes screenshots to channel: `railway_stream_{session_id}`
  const encoder = new TextEncoder()

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: object) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`))
      }

      // Poll task table for screenshots + logs (simple polling approach)
      // The Railway container writes screenshots as base64 to a Supabase column
      let running = true
      const interval = setInterval(async () => {
        if (!running) return

        // Get latest task state
        const { data: task } = await supabase
          .from('tasks')
          .select('status, progress, current_job, logs')
          .eq('railway_job_id', sessionId)
          .single()

        // Get latest screenshot from railway_sessions
        const { data: session } = await supabase
          .from('railway_sessions')
          .select('status, screenshot_count')
          .eq('id', sessionId)
          .single()

        if (task) {
          send({ type: 'status', status: task.status, progress: task.progress, current_job: task.current_job })
        }

        if (session?.status === 'completed' || session?.status === 'failed' || session?.status === 'stopped') {
          send({ type: 'done', status: session.status })
          running = false
          clearInterval(interval)
          controller.close()
        }
      }, 1000)

      // Clean up if client disconnects
      req.signal.addEventListener('abort', () => {
        running = false
        clearInterval(interval)
        controller.close()
      })
    }
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    }
  })
}
```

---

### 6. `components/ExecutionModeModal.tsx`

```typescript
'use client'
import { useState } from 'react'
import Link from 'next/link'

interface Props {
  isOpen: boolean
  onClose: () => void
  onConfirm: (mode: 'own_machine' | 'railway') => void
  railwayConfigured: boolean
  quota: { used: number; limit: number; remaining: number }
  taskType: 'AUTO_APPLY' | 'TAILOR_AND_APPLY'
  defaultMode: 'own_machine' | 'railway'
}

export default function ExecutionModeModal({ isOpen, onClose, onConfirm, railwayConfigured, quota, taskType, defaultMode }: Props) {
  const [selected, setSelected] = useState<'own_machine' | 'railway'>(defaultMode)
  const [remember, setRemember] = useState(false)

  if (!isOpen) return null

  const railwayDisabled = !railwayConfigured || quota.remaining <= 0

  const handleConfirm = () => {
    onConfirm(selected)
    // If remember is checked, caller saves to user_profiles.preferred_execution_mode
    if (remember) {
      fetch('/api/user/preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferred_execution_mode: selected })
      })
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-1">Where should automation run?</h2>
        <p className="text-sm text-gray-500 mb-6">Choose how to run <strong>{taskType === 'AUTO_APPLY' ? 'Auto Apply' : 'Tailor & Apply'}</strong></p>

        <div className="space-y-3 mb-6">
          {/* Own Machine */}
          <button
            onClick={() => setSelected('own_machine')}
            className={`w-full text-left p-4 rounded-xl border-2 transition-all ${
              selected === 'own_machine' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold text-gray-900">💻 Own Machine</p>
                <p className="text-sm text-gray-500 mt-1">Runs on your computer via the installed agent. You see Chrome open live.</p>
              </div>
              {selected === 'own_machine' && <span className="text-blue-500 text-lg">✓</span>}
            </div>
          </button>

          {/* Railway Cloud */}
          <button
            onClick={() => !railwayDisabled && setSelected('railway')}
            disabled={railwayDisabled}
            className={`w-full text-left p-4 rounded-xl border-2 transition-all relative ${
              selected === 'railway' ? 'border-violet-500 bg-violet-50' :
              railwayDisabled ? 'border-gray-200 opacity-60 cursor-not-allowed' :
              'border-gray-200 hover:border-violet-300'
            }`}
          >
            <div className="absolute top-3 right-3 flex gap-2">
              <span className="bg-violet-100 text-violet-700 text-xs font-medium px-2 py-0.5 rounded-full">⭐ Recommended</span>
              {selected === 'railway' && <span className="text-violet-500 text-lg">✓</span>}
            </div>
            <p className="font-semibold text-gray-900">☁️ Railway Cloud</p>
            <p className="text-sm text-gray-500 mt-1">Runs in the cloud. No install needed. Watch live in browser.</p>
            
            {!railwayConfigured ? (
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full">Setup Required</span>
                <Link href="/agent/setup" className="text-xs text-violet-600 underline" onClick={onClose}>Set up in 2 min →</Link>
              </div>
            ) : quota.remaining <= 0 ? (
              <p className="text-xs text-red-500 mt-2">Daily limit reached ({quota.used}/{quota.limit} min used)</p>
            ) : (
              <p className="text-xs text-gray-400 mt-2">{quota.remaining} min remaining today ({quota.used}/{quota.limit} used)</p>
            )}
          </button>
        </div>

        {/* Remember choice */}
        <label className="flex items-center gap-2 text-sm text-gray-600 mb-6 cursor-pointer">
          <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} className="rounded" />
          Remember my choice
        </label>

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={selected === 'railway' && railwayDisabled}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            Start {selected === 'railway' ? 'on Railway' : 'on My Machine'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

---

### 7. `app/(protected)/agent/setup/page.tsx` — Railway Setup Wizard

Build a clean step-by-step page with these 4 steps:

```
Step 1: "We've already set up Railway for you — you're using VantaHire's shared cloud."
        [Informational — no action needed from user]

Step 2: Test Connection
        Button: "Test Railway Connection" → calls GET /api/railway/status?ping=true
        If success: green checkmark "Connected!"
        If fail: red "Cannot connect — contact support"

Step 3: Done
        "You're all set! Railway is connected."
        Sets user_profiles.railway_configured = true via PATCH /api/user/preferences
        Button: "Go to Agent →" (links to /agent)
```

**Note to Copilot:** Users do NOT manage Railway themselves. The Railway service is deployed by the VantaHire developer (admin). Users just need to verify the connection works. The setup wizard is mostly informational + a connection test.

Also add a banner on `app/(protected)/agent/page.tsx`:
```
If user_profiles.railway_configured === false:
  Show yellow banner: "☁️ Run automation in the cloud — no install needed. Set up takes 1 min."
  With button: "Set Up Railway →" linking to /agent/setup
  With dismiss (X) button — stores dismissed in localStorage
```

---

### 8. Agent page updates — `app/(protected)/agent/page.tsx`

**ADD these to state:**
```typescript
const [showExecutionModal, setShowExecutionModal] = useState(false)
const [pendingTaskType, setPendingTaskType] = useState<'AUTO_APPLY' | 'TAILOR_AND_APPLY' | null>(null)
const [executionMode, setExecutionMode] = useState<'own_machine' | 'railway'>('own_machine')
const [railwayConfigured, setRailwayConfigured] = useState(false)
const [railwayQuota, setRailwayQuota] = useState({ used: 0, limit: 5, remaining: 5 })
const [railwaySessionId, setRailwaySessionId] = useState<string | null>(null)
const [liveScreenshot, setLiveScreenshot] = useState<string | null>(null)
const [railwayStatus, setRailwayStatus] = useState<'idle' | 'running' | 'done'>('idle')
```

**MODIFY the trigger handler** (wrap existing trigger logic, do NOT remove it):
```typescript
// When user clicks "Start Auto Apply" or "Start Semi-Auto":
// 1. Set pendingTaskType
// 2. Open ExecutionModeModal
// 3. On modal confirm with 'own_machine': run existing trigger flow (unchanged)
// 4. On modal confirm with 'railway': call triggerRailway()
```

**ADD Railway trigger function:**
```typescript
async function triggerRailway(taskType: string, taskInput: object) {
  setRailwayStatus('running')
  const res = await fetch('/api/railway/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session?.access_token}` },
    body: JSON.stringify({ task_id: currentTaskId, task_type: taskType, task_input: taskInput })
  })
  const data = await res.json()
  if (!res.ok) { toast.error(data.error); return }
  setRailwaySessionId(data.session_id)
  startScreenshotStream(data.session_id)
}
```

**ADD screenshot stream function:**
```typescript
function startScreenshotStream(sessionId: string) {
  const evtSource = new EventSource(`/api/railway/stream?session_id=${sessionId}`)
  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'screenshot') setLiveScreenshot(msg.data)
    if (msg.type === 'done') { setRailwayStatus('done'); evtSource.close() }
  }
}
```

**ADD live screenshot panel in JSX** (only shown when `executionMode === 'railway' && railwayStatus !== 'idle'`):
```tsx
{executionMode === 'railway' && railwayStatus !== 'idle' && (
  <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50 p-4">
    <div className="flex items-center justify-between mb-3">
      <h3 className="font-semibold text-violet-800">☁️ Live View — Railway</h3>
      {railwayStatus === 'running' && (
        <button onClick={stopRailway} className="text-sm text-red-600 border border-red-300 px-3 py-1 rounded-lg hover:bg-red-50">
          Stop
        </button>
      )}
    </div>
    {liveScreenshot ? (
      <img src={`data:image/jpeg;base64,${liveScreenshot}`} alt="Live automation view" className="w-full rounded-lg border" />
    ) : (
      <div className="h-48 flex items-center justify-center text-violet-400 text-sm">
        Waiting for browser to start...
      </div>
    )}
  </div>
)}
```

---

### 9. `automation/screenshot_streamer.py` — NEW

```python
"""
Runs inside Railway container alongside the automation.
Takes screenshots every 1 second and pushes to Supabase.
"""
import asyncio
import base64
import httpx
import os

SCREENSHOT_INTERVAL = 1.0
stop_event = asyncio.Event()

async def stream_screenshots(page, session_id: str):
    """
    Call this as a background task while automation runs.
    Pushes base64 JPEG screenshots to railway_sessions via Supabase REST.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    count = 0

    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            try:
                screenshot_bytes = await page.screenshot(type="jpeg", quality=55)
                b64 = base64.b64encode(screenshot_bytes).decode()
                count += 1

                # Store latest screenshot in railway_sessions
                await client.patch(
                    f"{supabase_url}/rest/v1/railway_sessions?id=eq.{session_id}",
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    },
                    json={
                        "latest_screenshot": b64,
                        "screenshot_count": count
                    }
                )
            except Exception:
                pass  # Page may be mid-navigation — skip frame
            await asyncio.sleep(SCREENSHOT_INTERVAL)
```

> Add `latest_screenshot TEXT` column to `railway_sessions` table. The SSE stream route reads this column every second and sends it to the client.

---

### 10. `taskrunner/task_runner.py` — ONE CHANGE ONLY

At the very top of `run_task(task)`, add:

```python
def run_task(task):
    # If task is set to run on Railway, skip local execution
    if task.get("execution_mode") == "railway":
        print(f"[SKIP] Task {task['id']} is execution_mode=railway — handled by Railway cloud, not local runner")
        return
    
    # ... all existing code below unchanged ...
```

---

## Additional SQL RPC to add

```sql
-- Called by incrementRailwayUsage in lib/railway.ts
CREATE OR REPLACE FUNCTION increment_railway_minutes(
  p_user_id UUID,
  p_date DATE,
  p_minutes NUMERIC
) RETURNS VOID AS $$
BEGIN
  INSERT INTO railway_daily_usage (user_id, usage_date, minutes_used)
  VALUES (p_user_id, p_date, p_minutes)
  ON CONFLICT (user_id, usage_date)
  DO UPDATE SET minutes_used = railway_daily_usage.minutes_used + EXCLUDED.minutes_used;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

---

## DO NOT TOUCH

- `automation/linkedin.py` — unchanged
- `automation/naukri.py` — unchanged
- `automation/gmail_client.py` — unchanged
- `automation/ai_client.py` — unchanged
- `automation/human.py` — unchanged
- `taskrunner/main.py` — unchanged (only task_runner.py gets the skip check)
- `taskrunner/api_client.py` — unchanged
- `lib/ai.ts` — unchanged
- `lib/billing.ts` — unchanged
- `lib/api-auth.ts` — unchanged
- All existing API routes — unchanged
- `app/(protected)/agent/page.tsx` existing trigger + log + pause/stop/resume logic for own_machine — unchanged

---

## Testing Checklist

- [ ] Own machine trigger still works exactly as before
- [ ] Railway modal appears when clicking Auto Apply or Tailor & Apply
- [ ] If railway_configured = false → Railway card shows "Setup Required"
- [ ] If quota exhausted → Railway card is disabled
- [ ] Railway trigger calls /api/railway/trigger and returns session_id
- [ ] Screenshot stream shows live image updating every ~1 second
- [ ] Stop button calls /api/railway/stop and ends session
- [ ] Minutes are deducted from railway_daily_usage after stop
- [ ] Admin users get 120 min limit
- [ ] Free/trial users get 5 min limit
- [ ] Pro users get 15 min limit
- [ ] Premium users get 30 min limit
- [ ] "Remember my choice" saves to user_profiles.preferred_execution_mode
- [ ] Agent setup page shows and sets railway_configured = true after test
- [ ] task_runner.py skips tasks with execution_mode = 'railway'

---

*Copilot Prompt — VantaHire Railway Execution Mode — March 25, 2026*
