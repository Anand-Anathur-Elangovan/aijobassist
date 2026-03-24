import { NextRequest, NextResponse } from "next/server";
import { skillGapWithLearning } from "@/lib/ai";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const quotaError = await enforceQuota(user.id, "jd_analysis", user.email ?? undefined);
    if (quotaError) return quotaError;

    const { jd_text, resume_text } = await req.json();
    if (!jd_text?.trim() || jd_text.trim().length < 50) {
      return NextResponse.json(
        { error: "Please provide a full job description (at least 50 characters)." },
        { status: 400 },
      );
    }

    const result = await skillGapWithLearning(resume_text ?? "", jd_text);
    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[skill-gap] Error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
