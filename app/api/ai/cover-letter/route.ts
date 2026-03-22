import { NextRequest, NextResponse } from "next/server";
import { generateCoverLetter } from "@/lib/ai";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (user) {
      const quotaError = await enforceQuota(user.id, "cover_letter", user.email ?? undefined);
      if (quotaError) return quotaError;
    }

    const body        = await req.json();
    const resume_text: string = body?.resume_text ?? "";
    const jd_text:     string = body?.jd_text     ?? "";
    const company:     string = body?.company     ?? "";
    const role:        string = body?.role        ?? "";
    if (!resume_text.trim() || !jd_text.trim()) {
      return NextResponse.json(
        { error: "resume_text and jd_text are required" },
        { status: 400 },
      );
    }
    const result = await generateCoverLetter(resume_text, jd_text, company, role);
    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
