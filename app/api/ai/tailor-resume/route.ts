import { NextRequest, NextResponse } from "next/server";
import { tailorResume } from "@/lib/ai";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (user) {
      const quotaError = await enforceQuota(user.id, "ai_tailor", user.email ?? undefined);
      if (quotaError) return quotaError;
    }

    const body = await req.json();
    const resume_text: string = body?.resume_text ?? "";
    const jd_text:     string = body?.jd_text     ?? "";
    if (!resume_text.trim() || !jd_text.trim()) {
      return NextResponse.json(
        { error: "Both resume_text and jd_text are required" },
        { status: 400 },
      );
    }
    const result = await tailorResume(resume_text, jd_text);
    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
