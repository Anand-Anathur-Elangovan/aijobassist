import { NextRequest, NextResponse } from "next/server";
import { suggestKeywords } from "@/lib/ai";
import { getAuthUser } from "@/lib/api-auth";
import { createClient } from "@supabase/supabase-js";

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

    // Fetch parsed_text from the user's most recently updated resume
    const { data: resume } = await supabaseAdmin
      .from("resumes")
      .select("parsed_text")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(1)
      .single();

    if (!resume?.parsed_text?.trim()) {
      return NextResponse.json(
        { error: "No resume found. Please upload a resume first." },
        { status: 400 },
      );
    }

    const keywords = await suggestKeywords(resume.parsed_text);
    return NextResponse.json({ keywords });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
