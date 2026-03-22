// app/api/billing/quota/route.ts
// Check & increment usage quota

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";

export async function GET(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
  const { data: { user } } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const actionType = req.nextUrl.searchParams.get("action");
  if (!actionType) return NextResponse.json({ error: "action query param required" }, { status: 400 });

  const { data } = await sb.rpc("check_quota", {
    p_user_id: user.id,
    p_action_type: actionType,
  });

  return NextResponse.json(data ?? { allowed: false, used: 0, limit: 0, remaining: 0 });
}

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
  const { data: { user } } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { action_type } = await req.json();
  if (!action_type) return NextResponse.json({ error: "action_type required" }, { status: 400 });

  // Check quota first
  const { data: quota } = await sb.rpc("check_quota", {
    p_user_id: user.id,
    p_action_type: action_type,
  });

  if (!quota?.allowed) {
    return NextResponse.json({
      error: "Quota exceeded",
      ...quota,
    }, { status: 429 });
  }

  // Increment
  const { data: newCount } = await sb.rpc("increment_usage", {
    p_user_id: user.id,
    p_action_type: action_type,
  });

  return NextResponse.json({
    success: true,
    count: newCount,
    remaining: Math.max(0, (quota?.limit ?? 0) - (newCount ?? 0)),
  });
}
