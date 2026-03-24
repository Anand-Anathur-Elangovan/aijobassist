import { NextRequest, NextResponse } from "next/server";
import { predictPlacement, type PlacementPrepInput } from "@/lib/ai";
import { getAuthUser } from "@/lib/api-auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
    const input: PlacementPrepInput = {
      college:         body.college         ?? "",
      degree:          body.degree          ?? "B.E./B.Tech",
      branch:          body.branch          ?? "",
      graduation_year: body.graduation_year ? Number(body.graduation_year) : new Date().getFullYear(),
      cgpa:            body.cgpa            ? Number(body.cgpa)           : undefined,
      placement_exams: Array.isArray(body.placement_exams) ? body.placement_exams : ["AMCAT", "eLitmus"],
      target_role:     body.target_role     ?? undefined,
    };

    if (!input.branch.trim()) {
      return NextResponse.json({ error: "Branch / specialization is required." }, { status: 400 });
    }

    const result = await predictPlacement(input);
    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[placement-prep] Error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
