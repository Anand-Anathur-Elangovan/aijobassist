import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser, getServiceSupabase } from '@/lib/api-auth'

export async function POST(req: NextRequest) {
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const { task_id, decision } = body

  if (!task_id || !['approved', 'skipped'].includes(decision)) {
    return NextResponse.json(
      { error: 'task_id and valid decision (approved|skipped) required' },
      { status: 400 }
    )
  }

  const supabase = getServiceSupabase()

  // Verify the task belongs to this user and is currently waiting
  const { data: task } = await supabase
    .from('tasks')
    .select('id, status, user_id')
    .eq('id', task_id)
    .eq('user_id', user.id)
    .single()

  if (!task) {
    return NextResponse.json({ error: 'Task not found' }, { status: 404 })
  }
  if (task.status !== 'WAITING_APPROVAL') {
    return NextResponse.json(
      { error: 'Task is not currently waiting for approval' },
      { status: 400 }
    )
  }

  // Write the decision — the Python bot is polling this field every second
  await supabase
    .from('tasks')
    .update({ approval_decision: decision })
    .eq('id', task_id)

  return NextResponse.json({ success: true, decision })
}
