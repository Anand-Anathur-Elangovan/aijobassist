import { NextRequest, NextResponse } from "next/server";
import { analyzeJD } from "@/lib/ai";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (user) {
      const quotaError = await enforceQuota(user.id, "jd_analysis", user.email ?? undefined);
      if (quotaError) return quotaError;
    }

    const body = await req.json();
    const jd_text: string = body?.jd_text ?? "";
    if (!jd_text.trim()) {
      return NextResponse.json({ error: "jd_text is required" }, { status: 400 });
    }
    const result = await analyzeJD(jd_text);
    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
