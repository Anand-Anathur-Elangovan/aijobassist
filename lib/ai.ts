/**
 * lib/ai.ts — AI Client
 *
 * Automatically uses Claude Sonnet (claude-sonnet-4-5) when
 * ANTHROPIC_API_KEY is set in .env.local — otherwise falls back to the
 * keyword-based mock so the app keeps working with zero API key.
 *
 * Setup (one-time):
 *   1. npm install @anthropic-ai/sdk
 *   2. Add  ANTHROPIC_API_KEY=sk-ant-...  to .env.local
 *   Done — no code changes needed.
 */

// ── Types ─────────────────────────────────────────────────────────────────

export interface JDAnalysis {
  required_skills:  string[];
  nice_to_have:     string[];
  keywords:         string[];
  responsibilities: string[];
  seniority: "entry" | "mid" | "senior" | "principal" | "executive";
}

export interface MatchScoreResult {
  score:           number;   // 0 – 100
  matching_skills: string[];
  missing_skills:  string[];
  suggestions:     string[];
}

export interface TailoredResumeResult {
  tailored_text:     string;
  tailored_bullets:  string[];
  tailored_summary:  string;
  ats_score:         number;
  improvements:      string[];
  added_keywords?:   string[];
}

export interface CoverLetterResult {
  cover_letter:   string;
  intro_message:  string;
  linkedin_intro: string;
  email_subject:  string;
}

// ── Master skill/keyword list for mock extraction ─────────────────────────

const ALL_SKILLS: string[] = [
  // Languages
  "python","javascript","typescript","java","c++","c#","golang","rust","kotlin",
  "swift","ruby","php","scala","r","bash","shell","sql","html","css",
  // Frontend
  "react","vue","angular","next.js","nextjs","svelte","tailwind","sass","webpack",
  "vite","redux","mobx","graphql","rest api","rest","api design","spa","ssg","ssr",
  // Backend
  "node","nodejs","express","fastapi","django","flask","spring","rails","laravel",
  "nestjs","grpc","websockets","microservices","serverless",
  // Databases
  "postgresql","postgres","mysql","mongodb","redis","elasticsearch","cassandra",
  "sqlite","supabase","firebase","dynamodb","prisma","sequelize","typeorm",
  // Cloud / DevOps
  "aws","gcp","azure","docker","kubernetes","k8s","terraform","ansible","ci/cd",
  "github actions","jenkins","linux","nginx","vercel","cloudflare","s3","ec2",
  // AI / ML
  "machine learning","deep learning","tensorflow","pytorch","scikit-learn","pandas",
  "numpy","nlp","llm","openai","langchain","hugging face","computer vision","mlops",
  // Mobile
  "react native","flutter","ios","android","expo",
  // Testing
  "jest","pytest","cypress","selenium","playwright","unit testing","tdd","bdd",
  // Tools / Process
  "git","github","jira","agile","scrum","figma","postman","kafka","rabbitmq",
  "celery","airflow","datadog","grafana","prometheus",
  // Soft skills
  "communication","leadership","mentoring","stakeholder management",
  "product management","cross-functional","ownership","problem solving",
  "system design","architecture","code review",
];

// ── Claude Sonnet real-API helper ─────────────────────────────────────────
// Auto-activated when ANTHROPIC_API_KEY is present in environment.

async function callClaude(prompt: string, maxTokens = 4096): Promise<string> {
  // Dynamic import so the SDK is only loaded when actually needed
  const Anthropic = (await import("@anthropic-ai/sdk")).default;
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const msg = await client.messages.create({
    model: "claude-sonnet-4-5",
    max_tokens: maxTokens,
    messages: [{ role: "user", content: prompt }],
  });
  return (msg.content[0] as { type: string; text: string }).text;
}

function hasApiKey(): boolean {
  return !!(process.env.ANTHROPIC_API_KEY?.trim());
}

function parseJSON<T>(raw: string): T {
  // Strip accidental markdown code fences
  const cleaned = raw
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
  return JSON.parse(cleaned) as T;
}

// ── Private mock helpers ──────────────────────────────────────────────────

function extractSkills(text: string): string[] {
  const lower = text.toLowerCase();
  return ALL_SKILLS.filter((s) => lower.includes(s));
}

function extractResponsibilities(text: string): string[] {
  return text
    .split(/\n/)
    .map((l) => l.replace(/^[\s*•\-–—>]+/, "").trim())
    .filter((l) => l.length > 40 && l.length < 320)
    .slice(0, 8);
}

function detectSeniority(text: string): JDAnalysis["seniority"] {
  const lower = text.toLowerCase();
  if (/\b(vp|vice president|director|head of)\b/.test(lower)) return "executive";
  if (/\b(principal|staff engineer|architect)\b/.test(lower)) return "principal";
  if (/\b(senior|sr\.?\s|lead)\b/.test(lower))                return "senior";
  if (/\b(junior|jr\.?\s|entry.level|graduate|fresher|0[-–]2 year)\b/.test(lower)) return "entry";
  return "mid";
}

// ═════════════════════════════════════════════════════════════════════════
// 1. analyzeJD
// ═════════════════════════════════════════════════════════════════════════

export async function analyzeJD(jdText: string): Promise<JDAnalysis> {
  if (hasApiKey()) {
    const prompt = `Analyze this job description and return ONLY valid JSON with no extra text:
{
  "required_skills": string[],
  "nice_to_have": string[],
  "keywords": string[],
  "responsibilities": string[],
  "seniority": "entry" | "mid" | "senior" | "principal" | "executive"
}
Job Description:
${jdText}`;
    return parseJSON<JDAnalysis>(await callClaude(prompt, 1024));
  }
  // ── Mock fallback ────────────────────────────────────────────────────
  const found     = extractSkills(jdText);
  const splitAt   = Math.ceil(found.length * 0.65);
  return {
    required_skills:  found.slice(0, splitAt),
    nice_to_have:     found.slice(splitAt),
    keywords:         found.slice(0, Math.min(found.length, 15)),
    responsibilities: extractResponsibilities(jdText),
    seniority:        detectSeniority(jdText),
  };
}


// ═════════════════════════════════════════════════════════════════════════
// 2. matchScore
// ═════════════════════════════════════════════════════════════════════════

export async function matchScore(
  resumeText: string,
  jdText:     string,
): Promise<MatchScoreResult> {
  if (hasApiKey()) {
    const prompt = `Compare this resume against the job description.
Return ONLY valid JSON with no extra text:
{
  "score": number (0-100 ATS match),
  "matching_skills": string[],
  "missing_skills": string[],
  "suggestions": string[]
}
Resume:
${resumeText}

Job Description:
${jdText}`;
    return parseJSON<MatchScoreResult>(await callClaude(prompt, 1024));
  }
  // ── Mock fallback ────────────────────────────────────────────────────
  const jdSkills    = extractSkills(jdText);
  const resumeLower = resumeText.toLowerCase();
  const matching    = jdSkills.filter((s) => resumeLower.includes(s));
  const missing     = jdSkills.filter((s) => !resumeLower.includes(s));
  const raw         = jdSkills.length > 0 ? (matching.length / jdSkills.length) * 100 : 55;
  const score       = Math.min(97, Math.round(raw * 0.82 + 12));
  return {
    score,
    matching_skills: matching,
    missing_skills:  missing.slice(0, 12),
    suggestions:     missing
      .slice(0, 4)
      .map((s) => `Add a project, skill, or certification demonstrating "${s}"`),
  };
}


// ═════════════════════════════════════════════════════════════════════════
// 3. tailorResume
// ═════════════════════════════════════════════════════════════════════════

export async function tailorResume(
  resumeText: string,
  jdText:     string,
  customPrompt = "",
): Promise<TailoredResumeResult> {
  if (hasApiKey()) {
    const extra = customPrompt.trim() ? `\n\nExtra instruction: ${customPrompt}` : "";
    const prompt = `You are an expert ATS resume optimizer.
Rewrite the candidate's resume to maximise ATS match with the job description.
Rules:
- Preserve ALL real companies, roles, dates — do NOT invent experience
- Inject JD keywords naturally into existing bullets
- Open every bullet with a strong action verb + quantified result
- Add a 2-3 sentence professional summary aligned to the JD
- Output ATS-friendly plain text (no tables, no columns)${extra}
Return ONLY valid JSON with no extra text:
{
  "tailored_text": string,
  "tailored_bullets": string[],
  "tailored_summary": string,
  "ats_score": number,
  "improvements": string[]
}
Resume:
${resumeText}

Job Description:
${jdText}`;
    return parseJSON<TailoredResumeResult>(await callClaude(prompt, 4096));
  }
  // ── Mock fallback ────────────────────────────────────────────────────

  const ms         = await matchScore(resumeText, jdText);
  const jd         = await analyzeJD(jdText);
  const topMatch   = ms.matching_skills.slice(0, 4);
  const topMissing = ms.missing_skills.slice(0, 3);
  const topSkills  = topMatch.join(", ") || "software development";

  const tailored_summary =
    `Results-driven ${jd.seniority === "senior" || jd.seniority === "principal" ? jd.seniority + " " : ""}` +
    `engineer with proven expertise in ${topSkills}. ` +
    `Passionate about building scalable, maintainable systems that deliver measurable business impact.` +
    (topMissing.length
      ? ` Currently expanding proficiency in ${topMissing.slice(0, 2).join(" and ")}.`
      : "");

  const tailored_bullets = [
    `Developed and maintained high-performance ${topMatch[0] || "backend"} services, improving system reliability by 30% and reducing latency by 25%`,
    `Designed and implemented ${topMatch[1] || "cloud"} infrastructure, cutting deployment time from hours to minutes`,
    `Collaborated cross-functionally with product and design teams to deliver ${jd.seniority}-level features on time and within scope`,
    `Optimised ${topMatch[2] || "database"} queries and caching strategies, achieving a 2× throughput improvement`,
    `Established ${topMatch[3] || "CI/CD"} pipelines and testing standards, increasing code coverage to 85%`,
    ...(jd.responsibilities.slice(0, 2).map(
      (r) => `${r.charAt(0).toUpperCase()}${r.slice(1, 90)}${r.length > 90 ? "…" : ""}`,
    )),
  ];

  const tailored_text =
    `PROFESSIONAL SUMMARY\n${tailored_summary}\n\nKEY ACHIEVEMENTS\n` +
    tailored_bullets.map((b) => `• ${b}`).join("\n");

  return {
    tailored_text,
    tailored_bullets,
    tailored_summary,
    ats_score:    Math.min(96, ms.score + 12),
    improvements: [
      ...topMissing.map((s) => `Include "${s}" in your skills section or work experience`),
      "Start every bullet point with a strong action verb (Built, Designed, Led, Reduced…)",
      "Quantify every achievement: add % / $ / x multipliers where possible",
      "Ensure all JD-required tools appear verbatim (exact spelling) in your resume",
    ],
  };
}


// ═════════════════════════════════════════════════════════════════════════
// 4. generateCoverLetter
// ═════════════════════════════════════════════════════════════════════════

export async function generateCoverLetter(
  resumeText: string,
  jdText:     string,
  company:    string,
  role:       string,
): Promise<CoverLetterResult> {
  if (hasApiKey()) {
    const prompt = `Write tailored hiring documents for a candidate applying to ${role} at ${company}.
Return ONLY valid JSON with no extra text:
{
  "cover_letter": string,
  "intro_message": string (2-3 sentences for email body),
  "linkedin_intro": string (1-2 sentences for LinkedIn InMail),
  "email_subject": string
}
Resume:
${resumeText}

Job Description:
${jdText}`;
    return parseJSON<CoverLetterResult>(await callClaude(prompt, 2048));
  }
  // ── Mock fallback ────────────────────────────────────────────────────
  const ms       = await matchScore(resumeText, jdText);
  const skills   = ms.matching_skills.slice(0, 3).join(", ") || "software engineering";
  const compName = company.trim() || "your company";
  const roleName = role.trim()    || "this position";

  const cover_letter =
`Dear Hiring Manager,

I am writing to express my strong interest in the ${roleName} position at ${compName}. With hands-on experience in ${skills}, I am confident in my ability to make an immediate impact and grow with your team.

Throughout my career I have consistently delivered high-quality, scalable solutions while working collaboratively across engineering and product teams. What draws me particularly to ${compName} is the opportunity to contribute to a culture that values technical excellence and continuous improvement.

My background aligns closely with the requirements outlined in the job description. I am eager to bring my problem-solving skills and passion for building impactful products to ${compName}, and I would welcome the opportunity to discuss how I can contribute to your team's goals.

Thank you for your time and consideration. I look forward to hearing from you.

Best regards`;

  const intro_message =
    `Hi, I'm very excited about the ${roleName} role at ${compName}. ` +
    `With strong experience in ${skills}, I believe I can add real value to your team. ` +
    `Would love to connect!`;

  const linkedin_intro =
    `Hi [Recruiter Name], I came across the ${roleName} opening at ${compName} and I'm genuinely interested. ` +
    `I have solid experience in ${skills} and would love to learn more. ` +
    `Would you be open to a quick chat?`;

  const email_subject = `Application for ${roleName} — ${compName}`;

  return { cover_letter, intro_message, linkedin_intro, email_subject };
}
