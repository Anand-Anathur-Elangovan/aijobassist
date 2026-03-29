import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { getAuthUser } from "@/lib/api-auth";

const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
);

export async function POST(req: NextRequest) {
  const user = await getAuthUser(req);
  if (!user) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }

  try {
    const body = await req.json();
    const tailored_text: string = body?.tailored_text ?? "";
    const company: string       = (body?.company ?? "").trim();
    const role: string          = (body?.role    ?? "").trim();

    if (!tailored_text.trim()) {
      return NextResponse.json({ error: "tailored_text is required" }, { status: 400 });
    }

    // Build a clear, automation-friendly title
    const title =
      company && role
        ? `${company} — ${role}`
        : company || role || "Tailored Resume";

    const { data, error } = await supabaseAdmin
      .from("resumes")
      .insert({
        user_id:     user.id,
        title,
        parsed_text: tailored_text,
        content:     { tailored: true, company, role, source: "resume_studio" },
      })
      .select("id")
      .single();

    if (error) throw error;

    return NextResponse.json({ id: data.id, title });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
