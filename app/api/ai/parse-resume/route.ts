import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function POST(req: NextRequest) {
  try {
    const { resume_id, file_url, user_id } = await req.json();
    if (!file_url || !user_id) {
      return NextResponse.json({ error: "file_url and user_id are required" }, { status: 400 });
    }

    // Download the file
    const fileResp = await fetch(file_url);
    if (!fileResp.ok) {
      return NextResponse.json({ error: "Could not download resume file" }, { status: 502 });
    }
    const buffer = Buffer.from(await fileResp.arrayBuffer());

    // Derive extension from the stored filename (most reliable) or fall back to URL pathname
    const storedName = (file_url ? new URL(file_url).pathname : "").split("/").pop() ?? "";
    const ext = storedName.split(".").pop()?.toLowerCase() ?? "";

    let parsedText = "";

    if (ext === "pdf") {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const pdfParse = require("pdf-parse");
      const data = await pdfParse(buffer);
      parsedText = (data.text || "").trim();
    } else if (ext === "docx" || ext === "doc") {
      // mammoth handles both .docx (OOXML) and legacy .doc (binary Word)
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mammoth = require("mammoth");
      const result = await mammoth.extractRawText({ buffer });
      parsedText = (result.value || "").trim();
    } else {
      // .txt or any other text-based format — read as UTF-8
      parsedText = buffer.toString("utf-8").trim();
    }

    if (!parsedText) {
      return NextResponse.json({ error: "Could not extract text from file" }, { status: 422 });
    }

    // Update the resumes row with parsed_text
    let query = supabaseAdmin
      .from("resumes")
      .update({ parsed_text: parsedText })
      .eq("user_id", user_id);

    if (resume_id) {
      query = query.eq("id", resume_id);
    }

    const { error: dbError } = await query;
    if (dbError) {
      console.error("[parse-resume] DB update error:", dbError.message);
      // Still return the text — caller can use it even if DB write failed
    }

    return NextResponse.json({ parsed_text: parsedText, length: parsedText.length });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[parse-resume] Error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
