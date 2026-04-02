// app/api/railway/quota/route.ts
// GET — Return today's Railway quota for the authenticated user (admin-aware)

import { NextRequest, NextResponse } from 'next/server'
import { getAuthUser } from '@/lib/api-auth'
import { checkRailwayQuota } from '@/lib/railway'

export async function GET(req: NextRequest) {
  const user = await getAuthUser(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const quota = await checkRailwayQuota(user.id, user.email ?? undefined)
  return NextResponse.json({
    used:      quota.used,
    limit:     quota.limit,
    remaining: quota.remaining,
    allowed:   quota.allowed,
  })
}
