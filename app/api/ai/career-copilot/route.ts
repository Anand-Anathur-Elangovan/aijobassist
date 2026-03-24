import { NextRequest, NextResponse } from "next/server";
import { predictCareer, type StudentInput } from "@/lib/ai";
import { getAuthUser, getServiceSupabase } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
    const input: StudentInput = {
      student_name:   body.student_name   ?? "",
      state:          body.state          ?? "",
      board:          body.board          ?? "CBSE",
      marks_10th:     body.marks_10th     ? Number(body.marks_10th)  : undefined,
      marks_12th:     body.marks_12th     ? Number(body.marks_12th)  : undefined,
      stream_12th:    body.stream_12th    ?? undefined,
      entrance_exams: Array.isArray(body.entrance_exams) ? body.entrance_exams : [],
      community:      body.community      ?? "OC",
      quota:          Array.isArray(body.quota) ? body.quota : [],
      interests:      Array.isArray(body.interests) ? body.interests : [],
    };

    if (!input.state.trim()) {
      return NextResponse.json({ error: "state is required" }, { status: 400 });
    }

    // Run AI prediction (has built-in fallback — never throws)
    const result = await predictCareer(input);

    // Persist student profile (upsert) and prediction history in background
    try {
      const sb = getServiceSupabase();

      // Upsert student profile
      const { data: profile } = await sb
        .from("student_profiles")
        .upsert({
          user_id:        user.id,
          student_name:   input.student_name,
          state:          input.state,
          board:          input.board,
          marks_10th:     input.marks_10th ?? null,
          marks_12th:     input.marks_12th ?? null,
          stream_12th:    input.stream_12th ?? null,
          entrance_exams: input.entrance_exams,
          community:      input.community,
          quota:          input.quota,
          interests:      input.interests,
          updated_at:     new Date().toISOString(),
        }, { onConflict: "user_id" })
        .select("id")
        .single();

      // Store prediction history
      await sb.from("career_predictions").insert({
        user_id:            user.id,
        student_profile_id: profile?.id ?? null,
        input_snapshot:     input,
        courses:            result.courses,
        colleges:           result.colleges,
        exam_roadmap:       result.exam_roadmap,
        strategy:           result.strategy,
        is_fallback:        result.is_fallback ?? false,
      });
    } catch (dbErr) {
      // Non-fatal: prediction already computed, just log
      console.error("[career-copilot] DB persist error:", dbErr);
    }

    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    console.error("[career-copilot] Unexpected error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// GET — returns saved student profile + last prediction
export async function GET(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const sb = getServiceSupabase();

    const [{ data: profile }, { data: lastPrediction }] = await Promise.all([
      sb.from("student_profiles").select("*").eq("user_id", user.id).single(),
      sb
        .from("career_predictions")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(1)
        .single(),
    ]);

    return NextResponse.json({ profile: profile ?? null, last_prediction: lastPrediction ?? null });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
