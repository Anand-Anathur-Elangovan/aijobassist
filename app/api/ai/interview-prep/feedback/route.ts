import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { getAuthUser } from "@/lib/api-auth";
import { SONNET_MODEL } from "@/lib/ai";

export type HistoryEntry = {
  question:    string;
  user_answer: string;
  ai_feedback: string;
};

export type FeedbackResult = {
  feedback:          string;  // Detailed evaluation of the user's answer
  score:             number;  // 1-10
  strengths:         string[];
  improvements:      string[];
  follow_up:         string;  // A follow-up question the interviewer might ask next
};

export async function POST(req: NextRequest) {
  try {
    const user = await getAuthUser(req);
    if (!user) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const {
      question,
      user_answer,
      jd_text,
      company,
      role,
      resume_text,
      history = [] as HistoryEntry[],
    } = await req.json();

    if (!question?.trim() || !user_answer?.trim()) {
      return NextResponse.json(
        { error: "Both question and user_answer are required." },
        { status: 400 }
      );
    }

    if (!process.env.ANTHROPIC_API_KEY?.trim()) {
      // Mock fallback when API key not configured
      return NextResponse.json({
        feedback: "Great answer! You covered the key points clearly. To strengthen it further, add a specific metric or outcome from a real project.",
        score: 7,
        strengths: ["Clear structure", "Relevant example given"],
        improvements: ["Add quantifiable outcome (e.g. 'reduced latency by 30%')", "Tie the answer back to the specific role requirements"],
        follow_up: "Can you walk me through how you measured the impact of that decision?",
      } satisfies FeedbackResult);
    }

    // Build conversation history context
    const historyContext = (history as HistoryEntry[]).length > 0
      ? `\n\nPrevious answers in this session:\n${(history as HistoryEntry[]).map((h, i) =>
          `Q${i + 1}: ${h.question}\nCandidate: ${h.user_answer}\nFeedback score: ${h.ai_feedback.match(/\d+\/10/)?.[0] ?? "given"}`
        ).join("\n\n")}`
      : "";

    const resumeContext = resume_text?.trim()
      ? `\nCandidate Resume:\n${resume_text.slice(0, 1500)}`
      : "";

    const companyLine = company?.trim() ? `Company: ${company.trim()}` : "";
    const roleLine    = role?.trim()    ? `Role: ${role.trim()}`       : "";

    const prompt = `You are an expert interview coach evaluating a candidate's answer during a mock interview session.
${companyLine}${companyLine && roleLine ? "\n" : ""}${roleLine}

Job Description:
${(jd_text ?? "").slice(0, 2000)}
${resumeContext}${historyContext}

Current Question: ${question}

Candidate's Answer: ${user_answer}

Evaluate this answer with awareness of what the candidate has already demonstrated in this session.
Be specific, actionable, and encouraging — reference the actual JD requirements in your feedback.

Return ONLY valid JSON:
{
  "feedback": "<2-4 sentence evaluation referencing the JD and what was strong or weak>",
  "score": <integer 1-10>,
  "strengths": ["<specific strength>", "<specific strength>"],
  "improvements": ["<specific actionable improvement>", "<specific improvement>"],
  "follow_up": "<a natural follow-up question an interviewer would likely ask next>"
}`;

    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const msg = await client.messages.create({
      model: SONNET_MODEL,
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }],
    });

    let raw = (msg.content[0] as { text: string }).text.trim();
    raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    const result: FeedbackResult = JSON.parse(raw);

    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[interview-prep/feedback] Error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
