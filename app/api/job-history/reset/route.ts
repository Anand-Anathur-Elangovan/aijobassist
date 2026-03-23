// app/api/job-history/reset/route.ts
// Lets the user clear their job-seen history so previously skipped /
// applied URLs are retried on the next bot run.

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL =
  process.env.NEXT_PUBLIC_SUPABASE_URL ||
  "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY =
  process.env.SUPABASE_SERVICE_ROLE_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";

export async function DELETE(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
  const {
    data: { user },
  } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  if (!user)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Optional query params:
  //   ?platform=naukri|linkedin   — restrict to one platform
  //   ?type=smart_match           — delete only smart_match skip rows
  const platform  = req.nextUrl.searchParams.get("platform");
  const resetType = req.nextUrl.searchParams.get("type");

  let query = sb.from("job_history").delete().eq("user_id", user.id);
  if (platform) query = query.eq("platform", platform);
  if (resetType) query = query.eq("skip_reason", resetType);

  const { error } = await query;
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const scope = [
    platform ? `for ${platform}` : null,
    resetType === "smart_match" ? "(Smart Match skips only)" : null,
  ].filter(Boolean).join(" ") || "all";

  return NextResponse.json({
    success: true,
    message: `Job history reset ${scope} successfully.`,
  });
}
