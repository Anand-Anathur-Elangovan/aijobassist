// lib/railway.ts — Railway Cloud Execution helpers
// Used by /api/railway/* routes — server-side only

import { getServiceSupabase } from './api-auth'

const RAILWAY_SERVICE_URL = process.env.RAILWAY_SERVICE_URL || 'https://vantahire-automation.up.railway.app'
const RAILWAY_API_TOKEN   = process.env.RAILWAY_API_TOKEN   || ''

const SUPER_ADMINS = [
  'kaviyasaravanan01@gmail.com',
  'anandanathurelangovan94@gmail.com',
]
const ADMIN_DAILY_LIMIT_MINUTES = 120 // 2 hours for admins

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export interface RailwayQuotaCheck {
  allowed:   boolean
  used:      number   // minutes used today
  limit:     number   // daily limit in minutes
  remaining: number
}

export interface RailwaySession {
  id:               string
  user_id:          string
  task_id:          string | null
  railway_run_id:   string | null
  status:           'pending' | 'running' | 'completed' | 'failed' | 'stopped'
  started_at:       string
  ended_at:         string | null
  duration_seconds: number | null
  screenshot_count: number
  latest_screenshot:string | null
  error:            string | null
}

// ─────────────────────────────────────────────────────────────
// Quota helpers
// ─────────────────────────────────────────────────────────────

/**
 * Check if user can use Railway today.
 * Super admins → 120 min/day.
 * Others       → from plan_limits.daily_limit where action_type = 'railway_minutes'.
 */
export async function checkRailwayQuota(
  userId:     string,
  userEmail?: string
): Promise<RailwayQuotaCheck> {
  const supabase = getServiceSupabase()
  const today    = new Date().toISOString().split('T')[0]

  // Super admin bypass
  const limit = (userEmail && SUPER_ADMINS.includes(userEmail))
    ? ADMIN_DAILY_LIMIT_MINUTES
    : await getPlanRailwayLimit(userId)

  // Today's usage
  const { data: usage } = await supabase
    .from('railway_daily_usage')
    .select('minutes_used')
    .eq('user_id', userId)
    .eq('usage_date', today)
    .single()

  const used      = Number(usage?.minutes_used ?? 0)
  const remaining = Math.max(0, limit - used)
  return { allowed: used < limit, used, limit, remaining }
}

/** Look up the user's active plan limit for railway_minutes. Falls back to 5 (free). */
async function getPlanRailwayLimit(userId: string): Promise<number> {
  const supabase = getServiceSupabase()

  const { data: sub } = await supabase
    .from('subscriptions')
    .select('plan_id')
    .eq('user_id', userId)
    .in('status', ['active', 'past_due'])
    .single()

  if (!sub?.plan_id) return 5

  const { data: planLimit } = await supabase
    .from('plan_limits')
    .select('daily_limit')
    .eq('plan_id', sub.plan_id)
    .eq('action_type', 'railway_minutes')
    .single()

  return planLimit?.daily_limit ?? 5
}

/**
 * Atomically add minutes to today's Railway usage for the user.
 * Called when a Railway session ends.
 */
export async function incrementRailwayUsage(userId: string, minutes: number): Promise<void> {
  const supabase = getServiceSupabase()
  const today    = new Date().toISOString().split('T')[0]
  await supabase.rpc('increment_railway_minutes', {
    p_user_id: userId,
    p_date:    today,
    p_minutes: minutes,
  })
}

// ─────────────────────────────────────────────────────────────
// Railway service API calls
// ─────────────────────────────────────────────────────────────

/** Trigger the Railway automation service to start a job. */
export async function triggerRailwayRun(
  taskId:    string,
  taskInput: Record<string, unknown>,
  sessionId: string
): Promise<{ runId: string }> {
  const res = await fetch(`${RAILWAY_SERVICE_URL}/trigger`, {
    method:  'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${RAILWAY_API_TOKEN}`,
    },
    body: JSON.stringify({ task_id: taskId, session_id: sessionId, task_input: taskInput }),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Railway trigger failed (${res.status}): ${text}`)
  }

  const data = await res.json()
  return { runId: data.run_id ?? data.runId ?? sessionId }
}

/** Stop a running Railway automation job. */
export async function stopRailwayRun(runId: string): Promise<void> {
  const res = await fetch(`${RAILWAY_SERVICE_URL}/stop`, {
    method:  'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${RAILWAY_API_TOKEN}`,
    },
    body: JSON.stringify({ run_id: runId }),
  })
  // Best-effort — don't throw if stop request fails (job may have already ended)
  if (!res.ok) {
    console.warn(`[railway] stop request returned ${res.status}`)
  }
}

/** Ping the Railway service to verify connectivity. */
export async function pingRailwayService(): Promise<boolean> {
  try {
    const res = await fetch(`${RAILWAY_SERVICE_URL}/health`, {
      method:  'GET',
      headers: { 'Authorization': `Bearer ${RAILWAY_API_TOKEN}` },
      signal:  AbortSignal.timeout(5000), // 5-second timeout
    })
    return res.ok
  } catch {
    return false
  }
}
