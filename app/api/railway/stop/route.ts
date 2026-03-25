// app/api/railway/stop/route.ts
// POST — Stop a running Railway cloud automation job and record usage

import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'
import { stopRailwayRun, incrementRailwayUsage } from '@/lib/railway'

export async function POST(req: NextRequest) {
  // ── Auth ───────────────────────────────────────────────────
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  // ── Parse body ─────────────────────────────────────────────
  let body: { task_id?: string; session_id?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  const { task_id, session_id } = body
  if (!session_id) {
    return NextResponse.json({ error: 'session_id is required' }, { status: 400 })
  }

  const supabase = getServiceSupabase()

  // ── Fetch session — verify ownership ───────────────────────
  const { data: session, error: sessionErr } = await supabase
    .from('railway_sessions')
    .select('id, user_id, railway_run_id, started_at, status')
    .eq('id', session_id)
    .eq('user_id', user.id)
    .single()

  if (sessionErr || !session) {
    return NextResponse.json({ error: 'Session not found' }, { status: 404 })
  }

  if (['completed', 'failed', 'stopped'].includes(session.status)) {
    // Already ended — idempotent OK
    return NextResponse.json({ success: true, message: 'Session already ended' })
  }

  // ── Stop the Railway job (best-effort) ─────────────────────
  if (session.railway_run_id) {
    await stopRailwayRun(session.railway_run_id)
  }

  // ── Compute duration ───────────────────────────────────────
  const now              = new Date()
  const startedAt        = new Date(session.started_at)
  const durationSeconds  = Math.round((now.getTime() - startedAt.getTime()) / 1000)
  const minutesUsed      = parseFloat((durationSeconds / 60).toFixed(2))

  // ── Update session ─────────────────────────────────────────
  await supabase
    .from('railway_sessions')
    .update({
      status:           'stopped',
      ended_at:         now.toISOString(),
      duration_seconds: durationSeconds,
    })
    .eq('id', session_id)

  // ── Update task → DONE (or keep as-is if still running partially) ────
  if (task_id) {
    await supabase
      .from('tasks')
      .update({ status: 'DONE', stop_requested: true })
      .eq('id', task_id)
      .eq('user_id', user.id)
  }

  // ── Record Railway usage ───────────────────────────────────
  if (minutesUsed > 0) {
    await incrementRailwayUsage(user.id, minutesUsed)
  }

  return NextResponse.json({
    success:          true,
    duration_seconds: durationSeconds,
    minutes_used:     minutesUsed,
  })
}
