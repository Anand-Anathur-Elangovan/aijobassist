// app/api/railway/status/route.ts
// GET — Get Railway job status, task progress, and latest screenshot
//       Also handles ?ping=true to test Railway service connectivity

import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'
import { pingRailwayService } from '@/lib/railway'

export async function GET(req: NextRequest) {
  // ── Auth ───────────────────────────────────────────────────
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { searchParams } = new URL(req.url)
  const ping    = searchParams.get('ping') === 'true'
  const taskId  = searchParams.get('task_id')
  const sessionId = searchParams.get('session_id')

  // ── Ping mode: just test Railway service connectivity ──────
  if (ping) {
    const reachable = await pingRailwayService()
    return NextResponse.json({ reachable })
  }

  if (!taskId && !sessionId) {
    return NextResponse.json(
      { error: 'task_id or session_id is required' },
      { status: 400 }
    )
  }

  const supabase = getServiceSupabase()

  // ── Fetch session ──────────────────────────────────────────
  let sessionQuery = supabase
    .from('railway_sessions')
    .select('id, status, started_at, ended_at, duration_seconds, latest_screenshot, screenshot_count, error, railway_run_id')
    .eq('user_id', user.id)

  if (sessionId) {
    sessionQuery = sessionQuery.eq('id', sessionId)
  } else {
    sessionQuery = sessionQuery.eq('task_id', taskId)
  }

  const { data: session } = await sessionQuery
    .order('created_at', { ascending: false })
    .limit(1)
    .single()

  // ── Fetch task progress ────────────────────────────────────
  let taskData = null
  if (taskId) {
    const { data: task } = await supabase
      .from('tasks')
      .select('status, progress, current_job, logs')
      .eq('id', taskId)
      .eq('user_id', user.id)
      .single()
    taskData = task
  }

  return NextResponse.json({
    session:            session ?? null,
    status:             session?.status ?? 'unknown',
    progress:           taskData?.progress ?? 0,
    current_job:        taskData?.current_job ?? null,
    logs:               taskData?.logs ?? [],
    latest_screenshot:  session?.latest_screenshot ?? null,
  })
}
