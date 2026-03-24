import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { getAuthUser } from "@/lib/api-auth";

const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
);

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Verify gmail settings exist and are active
    const { data: settings, error: settingsErr } = await supabaseAdmin
      .from("gmail_settings")
      .select("gmail_address, active")
      .eq("user_id", user.id)
      .single();

    if (settingsErr || !settings?.gmail_address) {
      return NextResponse.json(
        { error: "Gmail not configured. Set up Gmail credentials in Settings → Gmail tab first." },
        { status: 400 },
      );
    }
    if (!settings.active) {
      return NextResponse.json(
        { error: "Gmail scanning is disabled. Enable it in Settings → Gmail tab." },
        { status: 400 },
      );
    }

    // Check if a Gmail check is already running or pending
    const { data: existing } = await supabaseAdmin
      .from("tasks")
      .select("id, status")
      .eq("user_id", user.id)
      .eq("type", "GMAIL_DAILY_CHECK")
      .in("status", ["PENDING", "RUNNING"])
      .limit(1);

    if (existing && existing.length > 0) {
      return NextResponse.json({
        message: `Gmail check already ${existing[0].status.toLowerCase()}`,
        task_id: existing[0].id,
        already_running: true,
      });
    }

    // Create a new GMAIL_DAILY_CHECK task
    const { data: task, error: insertErr } = await supabaseAdmin
      .from("tasks")
      .insert({
        user_id: user.id,
        type: "GMAIL_DAILY_CHECK",
        status: "PENDING",
        input: { triggered_manually: true },
      })
      .select("id")
      .single();

    if (insertErr || !task) {
      throw new Error(insertErr?.message ?? "Failed to create task");
    }

    return NextResponse.json({
      message: `Gmail check queued for ${settings.gmail_address}`,
      task_id: task.id,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
