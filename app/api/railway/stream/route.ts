// app/api/railway/stream/route.ts
// GET — Server-Sent Events stream for live Railway screenshots and logs
//       Client connects with ?session_id=xxx
//       Events: 'screenshot', 'log', 'progress', 'done'

import { NextRequest } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'

export const runtime = 'nodejs'

// How often (ms) to poll Supabase for screenshot updates
const POLL_INTERVAL_MS = 1000

// Max stream duration (5 minutes safety cutoff)
const MAX_STREAM_MS = 5 * 60 * 1000

export async function GET(req: NextRequest) {
  // ── Auth ───────────────────────────────────────────────────
  const user = await getAuthUser(req)
  if (!user) {
    return new Response('Unauthorized', { status: 401 })
  }

  const { searchParams } = new URL(req.url)
  const sessionId = searchParams.get('session_id')
  if (!sessionId) {
    return new Response('session_id is required', { status: 400 })
  }

  const supabase = getServiceSupabase()

  // Verify session belongs to user
  const { data: initialSession } = await supabase
    .from('railway_sessions')
    .select('id, user_id, task_id, status')
    .eq('id', sessionId)
    .eq('user_id', user.id)
    .single()

  if (!initialSession) {
    return new Response('Session not found', { status: 404 })
  }

  const taskId = initialSession.task_id

  // ── SSE stream ─────────────────────────────────────────────
  let lastScreenshot:  string | null = null
  let lastLogCount                   = 0
  let lastProgress                   = -1
  const startTime                    = Date.now()

  const stream = new ReadableStream({
    async start(controller) {
      function send(event: string, data: unknown) {
        const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
        controller.enqueue(new TextEncoder().encode(payload))
      }

      // Send initial keepalive comment so the connection is established immediately
      controller.enqueue(new TextEncoder().encode(': connected\n\n'))

      async function poll() {
        // Safety: stop after MAX_STREAM_MS
        if (Date.now() - startTime > MAX_STREAM_MS) {
          send('done', { status: 'timeout', message: 'Stream exceeded maximum duration' })
          controller.close()
          return
        }

        // Fetch latest session data
        const { data: session } = await supabase
          .from('railway_sessions')
          .select('status, latest_screenshot, screenshot_count, error')
          .eq('id', sessionId)
          .single()

        // Push screenshot if it changed
        if (session?.latest_screenshot && session.latest_screenshot !== lastScreenshot) {
          lastScreenshot = session.latest_screenshot
          send('screenshot', {
            data:      session.latest_screenshot,
            count:     session.screenshot_count ?? 0,
            timestamp: new Date().toISOString(),
          })
        }

        // Push task logs and progress if task_id is set
        if (taskId) {
          const { data: task } = await supabase
            .from('tasks')
            .select('progress, current_job, logs, status')
            .eq('id', taskId)
            .single()

          if (task) {
            // Push new log entries
            const logs = (task.logs as Array<{ message: string; level?: string; ts?: string }>) ?? []
            if (logs.length > lastLogCount) {
              const newLogs = logs.slice(lastLogCount)
              for (const entry of newLogs) {
                send('log', {
                  message: entry.message ?? String(entry),
                  level:   entry.level ?? 'info',
                  ts:      entry.ts ?? new Date().toISOString(),
                })
              }
              lastLogCount = logs.length
            }

            // Push progress if changed
            if ((task.progress ?? 0) !== lastProgress) {
              lastProgress = task.progress ?? 0
              send('progress', {
                progress:    lastProgress,
                current_job: task.current_job ?? null,
              })
            }
          }
        }

        // Check if session has ended
        if (session && ['completed', 'failed', 'stopped'].includes(session.status)) {
          send('done', {
            status:  session.status,
            error:   session.error ?? null,
          })
          controller.close()
          return
        }

        // Schedule next poll
        setTimeout(poll, POLL_INTERVAL_MS)
      }

      // Start polling
      await poll()
    },

    cancel() {
      // Client disconnected — nothing to clean up on server side
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type':     'text/event-stream',
      'Cache-Control':    'no-cache, no-transform',
      'Connection':       'keep-alive',
      'X-Accel-Buffering':'no', // disable nginx buffering
    },
  })
}
