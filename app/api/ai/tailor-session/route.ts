import { NextRequest, NextResponse } from "next/server";
import { matchScore, tailorResume } from "@/lib/ai";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";

export async function POST(request: NextRequest) {
  try {
    const user = await getAuthUser(request);
    if (user) {
      const quotaError = await enforceQuota(user.id, "ai_tailor", user.email ?? undefined);
      if (quotaError) return quotaError;
    }

    const body = await request.json();
    const {
      resume_text,
      jd_text,
      custom_prompt,
      action = "tailor",
    }: {
      resume_text: string;
      jd_text: string;
      custom_prompt?: string;
      action?: "score" | "tailor";
    } = body;

    if (!resume_text || !jd_text) {
      return NextResponse.json(
        { error: "resume_text and jd_text are required" },
        { status: 400 }
      );
    }

    if (action === "score") {
      // Fast path — just return match score
      const scoreResult = await matchScore(resume_text, jd_text);
      return NextResponse.json({
        score_before: scoreResult.score,
      matching_skills: scoreResult.matching_skills,
      missing_skills: scoreResult.missing_skills,
        suggestions: scoreResult.suggestions,
      });
    }

    // Full tailor path
    const [scoreBefore, tailorResult] = await Promise.all([
      matchScore(resume_text, jd_text),
      tailorResume(resume_text, jd_text, custom_prompt),
    ]);

    // Score the tailored output
    const scoreAfter = await matchScore(tailorResult.tailored_text, jd_text);

    return NextResponse.json({
      score_before: scoreBefore.score,
      score_after: scoreAfter.score,
      tailored_text: tailorResult.tailored_text,
      tailored_summary: tailorResult.tailored_summary,
      tailored_bullets: tailorResult.tailored_bullets,
      ats_score: tailorResult.ats_score,
      improvements: tailorResult.improvements,
      missing_skills: scoreBefore.missing_skills,
      added_keywords: tailorResult.added_keywords ?? [],
    });
  } catch (err) {
    console.error("[tailor-session]", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
