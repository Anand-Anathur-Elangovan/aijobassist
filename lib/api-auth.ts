// lib/api-auth.ts — Server-side auth + quota helpers for API routes

import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const SUPER_ADMINS = [
  "kaviyasaravanan01@gmail.com",
  "anandanathurelangovan94@gmail.com",
];

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";

export function getServiceSupabase() {
  return createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
}

export async function getAuthUser(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) return null;

  const sb = getServiceSupabase();
  const { data: { user } } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  return user;
}

/**
 * Check quota and increment usage for a given action.
 * Returns null if allowed, or a NextResponse with 429 if quota exceeded.
 */
export async function enforceQuota(
  userId: string,
  actionType: string,
  userEmail?: string
): Promise<NextResponse | null> {
  // Super admins bypass all quota limits
  if (userEmail && SUPER_ADMINS.includes(userEmail)) return null;

  const sb = getServiceSupabase();

  const { data: quota } = await sb.rpc("check_quota", {
    p_user_id: userId,
    p_action_type: actionType,
  });

  if (quota && !quota.allowed) {
    return NextResponse.json(
      {
        error: "Daily quota exceeded",
        used: quota.used,
        limit: quota.limit,
        action_type: actionType,
      },
      { status: 429 }
    );
  }

  // Increment usage
  await sb.rpc("increment_usage", {
    p_user_id: userId,
    p_action_type: actionType,
  });

  return null; // allowed
}
