import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { getAuthUser, enforceQuota } from "@/lib/api-auth";
import { SONNET_MODEL } from "@/lib/ai";

type Question = {
  category: string;
  question: string;
  answer: string;
};

type PrepResult = {
  questions: Question[];
  key_topics: string[];
  preparation_tips: string[];
};

function mockInterviewPrep(): PrepResult {
  return {
    questions: [
      {
        category: "Behavioral",
        question: "Tell me about yourself and your professional background.",
        answer:
          "Start with your most recent role and work backwards. Highlight key achievements, relevant skills, and connect your experience to the role you're applying for. Keep it under 2 minutes.",
      },
      {
        category: "Behavioral",
        question: "Describe a challenging project you worked on and how you overcame obstacles.",
        answer:
          "Use the STAR format: Situation — briefly describe the context. Task — explain your responsibility. Action — detail the specific steps you took. Result — quantify the outcome (saved X hours, improved Y by Z%).",
      },
      {
        category: "Situational",
        question: "How do you prioritize tasks when you have multiple deadlines?",
        answer:
          "Describe your prioritization framework (urgency vs. importance matrix, daily planning, etc.). Give a real example. Mention communication — proactively flag conflicts early rather than missing deadlines silently.",
      },
      {
        category: "Technical",
        question: "Walk me through your experience with the core technologies mentioned in this role.",
        answer:
          "Prepare specific projects where you used each key skill from the job description. Quantify your experience (e.g., '3 years', 'led a team of 5', 'scaled to 1M users').",
      },
      {
        category: "Role-specific",
        question: "Why are you interested in this role and this company?",
        answer:
          "Research the company's mission, recent news, and the team. Connect your career goals to what this role offers. Show genuine enthusiasm — mention specific aspects of their work that excite you.",
      },
      {
        category: "Behavioral",
        question: "How do you handle disagreement or conflict with a colleague?",
        answer:
          "Focus on communication and outcomes. Describe how you listen to understand (not just to respond), find common ground, and escalate constructively when needed. End with a positive resolution.",
      },
    ],
    key_topics: [
      "Your top 3-5 relevant skills from the job description",
      "Company background, recent news, and culture",
      "Your most quantifiable achievements",
      "Gaps in your experience and how to address them",
      "Thoughtful questions to ask the interviewer",
    ],
    preparation_tips: [
      "Research the company: LinkedIn, Glassdoor, recent press releases, their product.",
      "Prepare 5-7 STAR stories covering leadership, conflict, failure, and success.",
      "Practice out loud — timing matters; aim for 60-90s answers.",
      "Prepare 3-4 smart questions to ask the interviewer at the end.",
      "Review the job description and map every bullet to a concrete example from your experience.",
      "Add your API key (ANTHROPIC_API_KEY) to get personalized questions tailored to this specific role.",
    ],
  };
}

export async function POST(req: NextRequest) {
  try {
    // Auth + quota (allow unauthenticated requests to use the mock fallback)
    const user = await getAuthUser(req);
    if (user && process.env.ANTHROPIC_API_KEY?.trim()) {
      const quotaError = await enforceQuota(user.id, "jd_analysis", user.email ?? undefined);
      if (quotaError) return quotaError;
    }

    const { jd_text, resume_text, company, role } = await req.json();
    if (!jd_text || jd_text.trim().length < 50) {
      return NextResponse.json(
        { error: "Please provide a full job description (at least 50 characters)." },
        { status: 400 }
      );
    }

    if (!process.env.ANTHROPIC_API_KEY?.trim()) {
      return NextResponse.json(mockInterviewPrep());
    }

    const resumeSection = resume_text?.trim()
      ? `\nCandidate Resume:\n${resume_text.slice(0, 2000)}`
      : "";

    const companyLine = company?.trim()   ? `\nCompany:       ${company.trim()}`  : "";
    const roleLine    = role?.trim()      ? `\nRole applying: ${role.trim()}`     : "";

    const prompt = `You are an expert interview coach preparing a candidate for a specific job interview.
${companyLine}${roleLine}

Job Description:
${jd_text.slice(0, 4000)}
${resumeSection}

Generate exactly 10 highly likely interview questions for this specific role with strong suggested answers.
Questions must be tailored to the actual JD — not generic.${company?.trim() ? ` Include 1-2 company-specific questions about ${company.trim()}'s work, culture, or products.` : ""}
Cover: Technical skills from the JD, Behavioral (STAR format), Situational, and Role-specific.

Return ONLY valid JSON, no prose:
{
  "questions": [
    {
      "category": "<Technical|Behavioral|Situational|Role-specific>",
      "question": "<specific interview question tailored to this JD>",
      "answer":   "<suggested answer 3-6 sentences, use STAR format for behavioral>"
    }
  ],
  "key_topics": ["<specific topic from this JD to prepare>"],
  "preparation_tips": ["<actionable tip specific to this role>"]
}`;

    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const msg = await client.messages.create({
      model: SONNET_MODEL,  // interview prep = complex reasoning → Sonnet
      max_tokens: 5000,
      messages: [{ role: "user", content: prompt }],
    });

    let raw = (msg.content[0] as { text: string }).text.trim();
    raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    const result: PrepResult = JSON.parse(raw);

    return NextResponse.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[interview-prep] Error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
