// app/api/railway/trigger/route.ts
// POST — Start a Railway cloud automation job

import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'
import { checkRailwayQuota, triggerRailwayRun } from '@/lib/railway'

export async function POST(req: NextRequest) {
  // ── Auth ───────────────────────────────────────────────────
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  // ── Parse body ─────────────────────────────────────────────
  let body: { task_id?: string; task_type?: string; task_input?: Record<string, unknown> }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  const { task_id, task_type, task_input } = body
  if (!task_id || !task_type) {
    return NextResponse.json({ error: 'task_id and task_type are required' }, { status: 400 })
  }

  // ── Railway quota check ────────────────────────────────────
  const quota = await checkRailwayQuota(user.id, user.email ?? undefined)
  if (!quota.allowed) {
    return NextResponse.json(
      {
        error:     'Daily Railway quota exceeded',
        used:      quota.used,
        limit:     quota.limit,
        remaining: quota.remaining,
      },
      { status: 429 }
    )
  }

  const supabase = getServiceSupabase()

  // ── Verify the task belongs to this user ───────────────────
  const { data: task, error: taskErr } = await supabase
    .from('tasks')
    .select('id, user_id, input')
    .eq('id', task_id)
    .eq('user_id', user.id)
    .single()

  if (taskErr || !task) {
    return NextResponse.json({ error: 'Task not found' }, { status: 404 })
  }

  // ── Create railway_session row ─────────────────────────────
  const { data: session, error: sessionErr } = await supabase
    .from('railway_sessions')
    .insert({
      user_id: user.id,
      task_id,
      status:  'pending',
    })
    .select('id')
    .single()

  if (sessionErr || !session) {
    return NextResponse.json({ error: 'Failed to create Railway session' }, { status: 500 })
  }

  // ── Update task: set execution_mode = 'railway', inject session_id into input ────
  // Keep status as PENDING so the Railway polling loop picks it up cleanly.
  await supabase
    .from('tasks')
    .update({
      execution_mode: 'railway',
      input: { ...(task.input as object ?? {}), ...(task_input ?? {}), session_id: session.id },
    })
    .eq('id', task_id)

  // ── Trigger Railway service ────────────────────────────────
  try {
    const mergedInput = {
      ...(task.input ?? {}),
      ...(task_input ?? {}),
      user_id:    user.id,
      task_id,
      session_id: session.id,
    }

    const { runId } = await triggerRailwayRun(task_id, mergedInput, session.id)

    // Store run ID back in the session and in the task
    await Promise.all([
      supabase
        .from('railway_sessions')
        .update({ railway_run_id: runId, status: 'running' })
        .eq('id', session.id),
      supabase
        .from('tasks')
        .update({ railway_job_id: runId })
        .eq('id', task_id),
    ])

    return NextResponse.json({
      success:        true,
      session_id:     session.id,
      railway_run_id: runId,
      quota: {
        used:      quota.used,
        limit:     quota.limit,
        remaining: quota.remaining,
      },
    })
  } catch (err) {
    // Rollback: mark session failed, task back to PENDING
    await Promise.all([
      supabase
        .from('railway_sessions')
        .update({ status: 'failed', error: String(err) })
        .eq('id', session.id),
      supabase
        .from('tasks')
        .update({ execution_mode: 'own_machine', status: 'PENDING' })
        .eq('id', task_id),
    ])

    return NextResponse.json(
      { error: 'Failed to start Railway job', detail: String(err) },
      { status: 502 }
    )
  }
}
