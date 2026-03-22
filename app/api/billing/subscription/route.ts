// app/api/billing/subscription/route.ts
// GET  — current subscription + usage
// POST — cancel subscription

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";

function getSupabase() {
  return createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
}

async function getUser(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) return null;
  const sb = getSupabase();
  const { data: { user } } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  return user;
}

export async function GET(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = getSupabase();

  // Get subscription with plan
  const { data: sub } = await sb
    .from("subscriptions")
    .select("*, plans(*)")
    .eq("user_id", user.id)
    .in("status", ["active", "past_due"])
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  // Get today's usage
  const { data: usage } = await sb
    .from("daily_usage")
    .select("action_type, count")
    .eq("user_id", user.id)
    .eq("usage_date", new Date().toISOString().slice(0, 10));

  // Get plan limits
  let planId = sub?.plan_id;
  if (!planId) {
    const { data: freePlan } = await sb.from("plans").select("id").eq("slug", "free").single();
    planId = freePlan?.id;
  }

  const { data: limits } = await sb
    .from("plan_limits")
    .select("action_type, daily_limit")
    .eq("plan_id", planId);

  // Get payment history
  const { data: payments } = await sb
    .from("payments")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(10);

  return NextResponse.json({
    subscription: sub,
    usage: usage ?? [],
    limits: limits ?? [],
    payments: payments ?? [],
  });
}

export async function POST(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { action } = await req.json();

  if (action === "cancel") {
    const sb = getSupabase();
    await sb
      .from("subscriptions")
      .update({ status: "cancelled", cancelled_at: new Date().toISOString() })
      .eq("user_id", user.id)
      .in("status", ["active", "past_due"]);

    await sb.from("notifications").insert({
      user_id: user.id,
      type: "general",
      title: "Subscription Cancelled",
      message: "Your subscription has been cancelled. You'll be moved to the Free plan.",
    });

    return NextResponse.json({ success: true });
  }

  return NextResponse.json({ error: "Unknown action" }, { status: 400 });
}
