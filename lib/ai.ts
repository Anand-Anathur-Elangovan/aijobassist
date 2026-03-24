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

// ── Model routing ────────────────────────────────────────────────────────
// Haiku  → fast, cheap — simple extraction, classification, comparison
// Sonnet → accurate, expensive — complex reasoning, writing, planning
const HAIKU_MODEL  = "claude-haiku-4-5";
const SONNET_MODEL = "claude-sonnet-4-5";

// ── Claude real-API helper ────────────────────────────────────────────────
// Auto-activated when ANTHROPIC_API_KEY is present in environment.

async function callClaude(prompt: string, maxTokens = 4096, model = SONNET_MODEL): Promise<string> {
  // Dynamic import so the SDK is only loaded when actually needed
  const Anthropic = (await import("@anthropic-ai/sdk")).default;
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const msg = await client.messages.create({
    model,
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
    return parseJSON<JDAnalysis>(await callClaude(prompt, 1024, HAIKU_MODEL));
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
    return parseJSON<MatchScoreResult>(await callClaude(prompt, 1024, HAIKU_MODEL));
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


// ═════════════════════════════════════════════════════════════════════════
// 5. predictCareer  — School → College Engine
// ═════════════════════════════════════════════════════════════════════════

export interface StudentInput {
  student_name:      string;
  state:             string;
  board:             string;  // 'CBSE' | 'ICSE' | 'State Board'
  marks_10th?:       number;
  marks_12th?:       number;
  stream_12th?:      string;  // 'PCM' | 'PCB' | 'Commerce' | 'Arts'
  cutoff_marks?: {
    math?:       number;
    physics?:    number;
    chemistry?:  number;
    neet?:       number;
  };
  entrance_exams:    string[];
  community:         string;  // 'OC' | 'BC' | 'MBC' | 'SC' | 'ST'
  quota:             string[];
  interests:         string[];
  favorite_colleges?: string[];
}

export interface CareerCourseResult {
  name:              string;
  probability:       "High" | "Medium" | "Low";
  match_reason:      string;
  future_scope:      string;
  avg_salary_lpa:    string;
  duration:          string;
  top_institutes:    string[];
}

export interface CareerCollegeResult {
  name:              string;
  location:          string;
  state:             string;
  category:          "Dream" | "Moderate" | "Safe";
  probability:       "High" | "Medium" | "Low";
  cutoff_hint:       string;
  fees_range:        string;
  placement_avg_lpa: string;
  college_type:      string;  // 'Govt' | 'Private' | 'Deemed' | 'Central'
  courses_offered:   string[];
}

export interface CareerExamRoadmap {
  exam:                  string;
  importance:            "Critical" | "Important" | "Optional";
  prep_duration:         string;
  key_topics:            string[];
  recommended_resources: string[];
  exam_window:           string;
}

export interface CareerStrategy {
  summary:          string;
  dream_colleges:   string[];
  safe_colleges:    string[];
  action_timeline:  { month: string; action: string }[];
  tips:             string[];
}

export interface FavoriteCollegeHistoricalCutoff {
  year:     string;
  cutoff:   string;
  category: string;
}

export interface FavoriteCollegeAnalysis {
  college_name:          string;
  feasibility:           "Reachable" | "Stretch" | "Very Tough" | "Out of Range";
  your_estimated_cutoff: string;
  required_cutoff:       string;
  gap_summary:           string;
  historical_cutoffs:    FavoriteCollegeHistoricalCutoff[];
  alternative_routes:    string[];
  similar_colleges:      string[];
  accessible_branches:   string[];
}

export interface CareerPredictionResult {
  courses:                    CareerCourseResult[];
  colleges:                   CareerCollegeResult[];
  exam_roadmap:               CareerExamRoadmap[];
  strategy:                   CareerStrategy;
  favorite_college_analysis?: FavoriteCollegeAnalysis[];
  message?:                   string;
  is_fallback?:               boolean;
}

// ── Fallback mock data (returned when AI fails or no API key) ─────────────
function careerFallback(input: StudentInput): CareerPredictionResult {
  const has12th = (input.marks_12th ?? 0) > 0;
  const pct     = input.marks_12th ?? input.marks_10th ?? 75;
  const isPCM   = input.stream_12th === "PCM";
  const isPCB   = input.stream_12th === "PCB";
  const hasNEET = input.entrance_exams.includes("NEET");
  const hasJEE  = input.entrance_exams.includes("JEE Main") || input.entrance_exams.includes("JEE Advanced");

  const courses: CareerCourseResult[] = [
    ...(isPCM || hasJEE ? [{
      name: "B.E / B.Tech Computer Science Engineering",
      probability: (pct >= 85 ? "High" : pct >= 70 ? "Medium" : "Low") as "High"|"Medium"|"Low",
      match_reason: "Strong PCM background aligns with CSE curriculum",
      future_scope: "Software engineering, AI/ML, product management, startups",
      avg_salary_lpa: "6–25 LPA (fresher to 3 years)",
      duration: "4 years",
      top_institutes: ["IITs", "NITs", "BITS Pilani", "VIT", "SRM", "Anna University"],
    }, {
      name: "B.E Electronics & Communication Engineering",
      probability: (pct >= 80 ? "High" : "Medium") as "High"|"Medium"|"Low",
      match_reason: "Good choice for PCM students interested in hardware + software",
      future_scope: "VLSI design, telecom, embedded systems, IoT",
      avg_salary_lpa: "4–15 LPA",
      duration: "4 years",
      top_institutes: ["NITs", "IITs", "Anna University", "College of Engineering Guindy"],
    }] : []),
    ...(isPCB || hasNEET ? [{
      name: "MBBS",
      probability: (pct >= 90 ? "High" : pct >= 75 ? "Medium" : "Low") as "High"|"Medium"|"Low",
      match_reason: "Biology background; NEET score determines admission",
      future_scope: "Clinical practice, specialisation, research, public health",
      avg_salary_lpa: "8–30 LPA (post PG)",
      duration: "5.5 years (incl. internship)",
      top_institutes: ["AIIMS", "JIPMER", "CMC Vellore", "Government Medical Colleges"],
    }, {
      name: "B.Pharm / Pharm.D",
      probability: "Medium" as "Medium",
      match_reason: "Great for PCB students who want healthcare without full MBBS commitment",
      future_scope: "Pharmaceutical industry, hospitals, research",
      avg_salary_lpa: "3–12 LPA",
      duration: "4 years (B.Pharm) / 6 years (Pharm.D)",
      top_institutes: ["JSS College of Pharmacy", "Manipal", "SRM", "Amrita"],
    }] : []),
    {
      name: "BCA / B.Sc Computer Science",
      probability: (pct >= 70 ? "High" : "Medium") as "High"|"Medium"|"Low",
      match_reason: "Accessible route into IT regardless of stream",
      future_scope: "Software development, data analysis, IT support",
      avg_salary_lpa: "3–10 LPA",
      duration: "3 years",
      top_institutes: ["Loyola College", "Madras Christian College", "PSG College of Arts & Science"],
    },
    {
      name: "B.Com / BBA",
      probability: (!has12th || input.stream_12th === "Commerce" ? "High" : "Medium") as "High"|"Medium"|"Low",
      match_reason: "Ideal for Commerce stream or business-oriented students",
      future_scope: "Finance, CA, MBA, entrepreneurship, banking",
      avg_salary_lpa: "3–12 LPA (with CA/MBA adds 20–50 LPA)",
      duration: "3 years",
      top_institutes: ["SRCC Delhi", "Loyola Chennai", "NM College Mumbai"],
    },
  ].slice(0, 5);

  const colleges: CareerCollegeResult[] = [
    {
      name: "IIT Madras",
      location: "Chennai",
      state: "Tamil Nadu",
      category: "Dream",
      probability: (pct >= 95 ? "Medium" : "Low") as "Medium"|"Low",
      cutoff_hint: "JEE Advanced rank < 500 for top branches",
      fees_range: "₹2–3 L / year",
      placement_avg_lpa: "20+ LPA",
      college_type: "Central",
      courses_offered: ["B.Tech CSE", "B.Tech ECE", "B.Tech Mechanical", "B.Tech EE"],
    },
    {
      name: "NIT Trichy",
      location: "Tiruchirappalli",
      state: "Tamil Nadu",
      category: "Moderate",
      probability: (pct >= 85 ? "High" : "Medium") as "High"|"Medium",
      cutoff_hint: "JEE Main rank 3000–15000 for Tamil Nadu home state",
      fees_range: "₹1.7–2.5 L / year",
      placement_avg_lpa: "14 LPA",
      college_type: "Central",
      courses_offered: ["B.Tech CSE", "B.Tech ECE", "B.Tech Civil", "B.Tech Chemical"],
    },
    {
      name: "Anna University (CEG Campus)",
      location: "Chennai",
      state: "Tamil Nadu",
      category: "Moderate",
      probability: (pct >= 80 ? "High" : "Medium") as "High"|"Medium",
      cutoff_hint: "TNEA cutoff 180–195 for CS/IT branches",
      fees_range: "₹80K–1.5 L / year",
      placement_avg_lpa: "8 LPA",
      college_type: "Govt",
      courses_offered: ["B.E CSE", "B.E ECE", "B.E IT", "B.E EEE"],
    },
    {
      name: "VIT Vellore",
      location: "Vellore",
      state: "Tamil Nadu",
      category: "Safe",
      probability: (pct >= 70 ? "High" : "Medium") as "High"|"Medium",
      cutoff_hint: "VITEEE rank based; ~1 lakh+ seats available",
      fees_range: "₹1.9–2.5 L / year",
      placement_avg_lpa: "7 LPA",
      college_type: "Deemed",
      courses_offered: ["B.Tech CSE", "B.Tech AIML", "B.Tech ECE", "B.Tech IT"],
    },
    {
      name: "SRM Institute of Science and Technology",
      location: "Kattankulathur, Chennai",
      state: "Tamil Nadu",
      category: "Safe",
      probability: "High",
      cutoff_hint: "SRMJEE or direct admission; broad intake",
      fees_range: "₹2–3.5 L / year",
      placement_avg_lpa: "6 LPA",
      college_type: "Deemed",
      courses_offered: ["B.Tech CSE", "B.Tech Data Science", "B.Tech ECE", "B.Tech AI"],
    },
  ];

  const exam_roadmap: CareerExamRoadmap[] = [
    ...(isPCM || hasJEE ? [{
      exam: "JEE Main",
      importance: "Critical" as "Critical",
      prep_duration: "12–18 months",
      key_topics: ["Physics: Mechanics, Electrostatics", "Chemistry: Organic, Inorganic", "Maths: Calculus, Algebra, Coordinate Geometry"],
      recommended_resources: ["NCERT (mandatory foundation)", "HC Verma – Physics", "RD Sharma – Maths", "Allen / Resonance coaching material"],
      exam_window: "January & April (two attempts per year)",
    }, {
      exam: "JEE Advanced",
      importance: "Important" as "Important",
      prep_duration: "6 months post JEE Main",
      key_topics: ["Deep conceptual problems in Physics, Chemistry, Maths", "Previous year IIT papers"],
      recommended_resources: ["Irodov – Problems in General Physics", "J.D. Lee – Inorganic Chemistry", "Cengage series"],
      exam_window: "May–June (after JEE Main qualification)",
    }] : []),
    ...(isPCB || hasNEET ? [{
      exam: "NEET UG",
      importance: "Critical" as "Critical",
      prep_duration: "12–24 months",
      key_topics: ["Biology: Human Physiology, Genetics, Ecology", "Physics: Optics, Modern Physics", "Chemistry: Biomolecules, Equilibrium"],
      recommended_resources: ["NCERT Bio (Classes 11 & 12)", "DC Pandey – Physics for NEET", "MTG Complete NEET Guide"],
      exam_window: "May (annually)",
    }] : []),
    {
      exam: `${input.state === "Tamil Nadu" ? "TNEA" : input.state === "Karnataka" ? "KCET" : input.state === "Maharashtra" ? "MHT-CET" : "State Counselling"}`,
      importance: "Important" as "Important",
      prep_duration: "3–6 months",
      key_topics: ["State board syllabus review", "Previous year state exam papers", "Application and counselling process"],
      recommended_resources: ["State board textbooks", "Previous year cut-off analysis", "Official state counselling website"],
      exam_window: "June–July (post 12th results)",
    },
  ];

  const strategy: CareerStrategy = {
    summary: `Based on your ${pct}% marks in ${input.state}, ${input.community} community, and ${input.stream_12th || "chosen"} stream, here is a personalised strategy maximising your college admission chances.`,
    dream_colleges: ["IIT Madras", "NIT Trichy", "BITS Pilani"],
    safe_colleges: ["VIT Vellore", "SRM Chennai", "Amrita University", "Saveetha Engineering"],
    action_timeline: [
      { month: "Now → 3 months", action: "Focus on NCERT mastery + complete one full mock test per week" },
      { month: "3 → 6 months", action: "Join test series; analyse mistakes; revise weak chapters" },
      { month: "6 → 9 months", action: "Solve 10 years of previous question papers; finalise college shortlist" },
      { month: "9 → 12 months", action: "Final revision; fill all exam forms; prepare documents for counselling" },
      { month: "Post exam", action: "Participate in all counselling rounds (state + central); do not miss upgrade rounds" },
    ],
    tips: [
      `Your ${input.community} category quota can give you 5–15% lower cutoff advantage — know all reserved quota seats`,
      "Apply to 10+ colleges across Dream / Moderate / Safe categories — never rely on one",
      "Register for TNEA / state counselling immediately after 12th results",
      ...(input.quota.includes("Sports") ? ["Sports quota seats are limited — apply early and get the certificate authenticated by the District Sports Officer"] : []),
      "Attend college open days and alumni talk to validate your choice before final commitment",
      "If rank is below target: consider lateral entry after Diploma (direct 2nd year B.E admission)",
    ],
  };

  const favorite_college_analysis: FavoriteCollegeAnalysis[] = (input.favorite_colleges ?? []).map((college) => {
    const estCutoff = Math.round((pct || 75) * 1.9);
    const estReq    = 192;
    const gap       = estCutoff - estReq;
    return {
      college_name:          college,
      feasibility:           (gap >= 0 ? "Reachable" : gap >= -15 ? "Stretch" : gap >= -30 ? "Very Tough" : "Out of Range") as "Reachable" | "Stretch" | "Very Tough" | "Out of Range",
      your_estimated_cutoff: `${estCutoff} / 200`,
      required_cutoff:       "~185–196 / 200 (OC general)",
      gap_summary:           gap >= 0
        ? `You are ~${gap} marks above typical cutoff estimates — feasible with strong preparation.`
        : `You need approximately ${Math.abs(gap)} more marks to meet the typical cutoff for CSE/IT branches.`,
      historical_cutoffs: [
        { year: "2024", cutoff: "193.5", category: "OC" },
        { year: "2023", cutoff: "191.0", category: "OC" },
        { year: "2022", cutoff: "189.75", category: "OC" },
      ],
      alternative_routes: [
        "Management Quota: 15% seats — direct admission without cutoff, higher fees apply",
        "NRI Quota: Available with NRI/OCI sponsorship, limited seats",
        input.community !== "OC"
          ? `${input.community} category reservation: cutoff 10–25 marks lower than OC merit list`
          : "Apply under any special quota you qualify for (sports, govt employee, etc.)",
        "Lateral Entry after 3-yr Diploma: Direct 2nd-year B.Tech admission — no TNEA cutoff",
        "Participate in every TNEA counselling round including special rounds & stray vacancy rounds",
      ],
      similar_colleges: [
        "PSG College of Technology, Coimbatore",
        "CIT Coimbatore",
        "Kongu Engineering College, Erode",
        "Sri Krishna College of Technology, Coimbatore",
      ],
      accessible_branches: [
        "B.E Mechanical Engineering (cutoff ~160–175)",
        "B.E Civil Engineering (cutoff ~155–170)",
        "B.E Electrical & Electronics Engineering (cutoff ~170–182)",
      ],
    };
  });

  return {
    courses,
    colleges,
    exam_roadmap,
    strategy,
    ...(favorite_college_analysis.length > 0 && { favorite_college_analysis }),
    message: "Showing sample predictions. Connect your AI key for personalised analysis.",
    is_fallback: true,
  };
}

export async function predictCareer(input: StudentInput): Promise<CareerPredictionResult> {
  if (!hasApiKey()) {
    return careerFallback(input);
  }

  const hasFavColleges = (input.favorite_colleges ?? []).length > 0;
  const cm = input.cutoff_marks ?? {};
  const hasCutoffMarks = !!(cm.math || cm.physics || cm.chemistry);
  const hasNeet = !!cm.neet;
  const prompt = `You are an expert Indian education counsellor with deep knowledge of all Indian state boards, central boards (CBSE/ICSE), college entrance exams (JEE, NEET, VITEEE, BITSAT, KCET, TNEA, MHT-CET, etc.), college cutoffs, placement statistics, and reservation policies (OC/BC/MBC/SC/ST, sports quota, management quota).

Student profile:
- Name: ${input.student_name}
- State: ${input.state}
- Board: ${input.board}
- 10th Marks: ${input.marks_10th ? input.marks_10th + "%" : "Not provided"}
- 12th Marks: ${input.marks_12th ? input.marks_12th + "%" : "Not provided"}
- 12th Stream: ${input.stream_12th || "Not specified"}${hasCutoffMarks ? `\n- Subject Marks (raw): Maths=${cm.math ?? "—"}, Physics=${cm.physics ?? "—"}, Chemistry=${cm.chemistry ?? "—"}` : ""}${hasNeet ? `\n- NEET Score: ${cm.neet}/720` : ""}
- Entrance Exams: ${input.entrance_exams.join(", ") || "None"}
- Community: ${input.community}
- Special Quota: ${input.quota.join(", ") || "None"}
- Interests: ${input.interests.join(", ") || "Open to all"}${hasFavColleges ? `\n- Favorite colleges to analyze: ${(input.favorite_colleges!).join(", ")}` : ""}

Return ONLY valid JSON (no markdown, no explanation). Keep all string values concise (≤120 chars each).
{${hasFavColleges ? `
  "favorite_college_analysis": [
    { "college_name": string, "feasibility": "Reachable"|"Stretch"|"Very Tough"|"Out of Range", "your_estimated_cutoff": string, "required_cutoff": string, "gap_summary": string, "historical_cutoffs": [{"year": string, "cutoff": string, "category": string}], "alternative_routes": string[], "similar_colleges": string[], "accessible_branches": string[] }
  ],` : ""}
  "courses": [
    { "name": string, "probability": "High"|"Medium"|"Low", "match_reason": string, "future_scope": string, "avg_salary_lpa": string, "duration": string, "top_institutes": string[] }
  ],
  "colleges": [
    { "name": string, "location": string, "state": string, "category": "Dream"|"Moderate"|"Safe", "probability": "High"|"Medium"|"Low", "cutoff_hint": string, "fees_range": string, "placement_avg_lpa": string, "college_type": "Govt"|"Private"|"Deemed"|"Central", "courses_offered": string[] }
  ],
  "exam_roadmap": [
    { "exam": string, "importance": "Critical"|"Important"|"Optional", "prep_duration": string, "key_topics": string[], "recommended_resources": string[], "exam_window": string }
  ],
  "strategy": {
    "summary": string,
    "dream_colleges": string[],
    "safe_colleges": string[],
    "action_timeline": [{"month": string, "action": string}],
    "tips": string[]
  }
}

Rules:
- Exactly 4 courses, exactly 5 colleges (mix of state + national), exactly 3 exam roadmaps
- Colleges MUST be realistic given the student's marks and state
- Probability must reflect actual cutoff data and community reservation benefits
- Tips specific to the student's state, community, and quota
- Include at least 2 "Safe" colleges the student can definitely get into
- top_institutes: max 4 items; courses_offered: max 4 items; key_topics: max 4 items; recommended_resources: max 3 items; tips: max 5 items; action_timeline: max 5 items${hasFavColleges ? `\n- For each favorite college: analyze feasibility vs the student's actual marks, community, and quota. Provide last 3 years historical cutoffs (OC + student's category if different), 4-5 specific alternative admission routes (management quota, NRI quota, lateral entry after diploma, special counselling rounds, etc.), 3-4 similar alternative colleges if out of reach, and 2-3 branches in the same college with lower cutoffs. historical_cutoffs: max 3 items; alternative_routes: max 5 items; similar_colleges: max 4 items; accessible_branches: max 3 items.` : ""}
`;

  try {
    const raw = await callClaude(prompt, 8000);
    const result = parseJSON<Omit<CareerPredictionResult, "is_fallback">>(raw);
    return { ...result, is_fallback: false };
  } catch (err) {
    console.error("[predictCareer] AI parse error:", err);
    return careerFallback(input);
  }
}


// ═════════════════════════════════════════════════════════════════════════
// 6. skillGapWithLearning — Match score + 2-week personalised learning plan
// ═════════════════════════════════════════════════════════════════════════

export interface LearningResource {
  skill:         string;
  priority:      "High" | "Medium" | "Low";
  time_to_learn: string;
  resources: Array<{
    platform:     string;
    search_query: string;
    duration:     string;
  }>;
}

export interface SkillGapResult extends MatchScoreResult {
  learning_plan:     LearningResource[];
  two_week_schedule: string[];
}

export async function skillGapWithLearning(
  resumeText: string,
  jdText:     string,
): Promise<SkillGapResult> {
  if (hasApiKey()) {
    const prompt = `Compare this resume against the job description. For each missing skill, create a realistic 2-week self-study plan with specific resource recommendations.

Return ONLY valid JSON with no extra text:
{
  "score": number (0-100 ATS match),
  "matching_skills": string[],
  "missing_skills": string[],
  "suggestions": string[],
  "learning_plan": [
    {
      "skill": string,
      "priority": "High"|"Medium"|"Low",
      "time_to_learn": string (e.g. "2-3 days"),
      "resources": [
        { "platform": string, "search_query": string, "duration": string }
      ]
    }
  ],
  "two_week_schedule": string[] (7 specific, actionable day-range items)
}

Rules:
- learning_plan covers the top 5-6 missing skills by priority
- For each skill provide exactly 3 resources mixing YouTube, Udemy/Coursera, and Official Docs/Practice
- Resources use real search terms people would type into those platforms
- two_week_schedule items are specific (e.g. "Week 1 Day 1-2: React Hooks — FreeCodeCamp 3h crash course + build a counter app")

Resume:
${resumeText.slice(0, 2000)}

Job Description:
${jdText.slice(0, 3000)}`;
    try {
      return parseJSON<SkillGapResult>(await callClaude(prompt, 3000));
    } catch {
      // fall through to mock
    }
  }
  // ── Mock fallback ────────────────────────────────────────────────────
  const base = await matchScore(resumeText, jdText);
  const learning_plan: LearningResource[] = base.missing_skills.slice(0, 6).map((skill, i) => ({
    skill,
    priority: (i < 2 ? "High" : i < 4 ? "Medium" : "Low") as "High" | "Medium" | "Low",
    time_to_learn: i < 2 ? "2-3 days" : "4-5 days",
    resources: [
      { platform: "YouTube",             search_query: `${skill} complete tutorial for beginners 2024`, duration: "3-5 hours" },
      { platform: "Udemy",               search_query: `${skill} masterclass complete course`,           duration: "8-15 hours" },
      { platform: "Official Docs / Practice", search_query: `${skill} official documentation getting started`, duration: "2-3 hours" },
    ],
  }));
  const s0 = base.missing_skills[0] ?? "your top missing skill";
  const s1 = base.missing_skills[1] ?? "second skill";
  const s2 = base.missing_skills[2] ?? "third skill";
  const two_week_schedule = [
    `Week 1 Day 1-2: ${s0} — watch YouTube crash course (3-5h) + build a small follow-along project`,
    `Week 1 Day 3-4: ${s1} — read official docs walkthrough + complete a starter example`,
    `Week 1 Day 5-7: ${s2} + first mini-project combining all 3 skills learned this week`,
    `Week 2 Day 1-2: Deepen ${s0} — start Udemy course, complete first 3 modules`,
    `Week 2 Day 3-4: Build a portfolio project combining ${s0} and ${s1}, push to GitHub with a clear README`,
    `Week 2 Day 5-6: Update your resume to list newly acquired tools + tweak project bullets to match JD keywords`,
    `Week 2 Day 7: Mock interview — explain your new skills out loud; prep "Tell me about your ${s0} experience"`,
  ];
  return { ...base, learning_plan, two_week_schedule };
}


// ═════════════════════════════════════════════════════════════════════════
// 7. predictPlacement — Campus Placement Prep Engine
// ═════════════════════════════════════════════════════════════════════════

export interface PlacementPrepInput {
  college:          string;
  degree:           string;
  branch:           string;
  graduation_year:  number;
  cgpa?:            number;
  placement_exams:  string[];  // ["AMCAT", "eLitmus", "Cocubes"]
  target_role?:     string;
}

export interface PlacementResource {
  topic:    string;
  resource: string;
  platform: string;
  duration: string;
  notes:    string;
}

export interface DriveTiming {
  company:        string;
  typical_months: string;
  role:           string;
  ctc_range:      string;
  eligibility:    string;
}

export interface OffCampusPortal {
  name:  string;
  url:   string;
  focus: string;
  tips:  string;
}

export interface PlacementWeekPlan {
  week:  string;
  tasks: string[];
}

export interface PlacementPrepResult {
  amcat_prep:            PlacementResource[];
  elitmus_prep:          PlacementResource[];
  campus_drive_calendar: DriveTiming[];
  off_campus_portals:    OffCampusPortal[];
  four_week_plan:        PlacementWeekPlan[];
  hr_tips:               string[];
  resume_tips:           string[];
  is_fallback?:          boolean;
}

function placementFallback(input: PlacementPrepInput): PlacementPrepResult {
  const role = input.target_role ?? `${input.branch} Engineer`;
  return {
    amcat_prep: [
      { topic: "Quantitative Aptitude", resource: "AMCAT Sample Papers (amcat.in/practice)", platform: "amcat.in", duration: "5-7 days", notes: "Time & Work, Percentages, Number Series, Permutation & Combination" },
      { topic: "Verbal Ability", resource: "Wren & Martin High School English Grammar", platform: "Book / PDF", duration: "3-4 days", notes: "Sentence correction, comprehension, vocabulary — 30 min/day" },
      { topic: "Logical Reasoning", resource: "R.S. Aggarwal Modern Approach to Verbal Reasoning", platform: "Book / PDF", duration: "4-5 days", notes: "Syllogisms, Blood Relations, Coding-Decoding, Series" },
      { topic: "Coding / Automata Fix", resource: "LeetCode Easy — Arrays & Strings category", platform: "leetcode.com", duration: "1 week (2/day)", notes: "AMCAT tech tests ask you to fix broken code, not write from scratch — practice debugging" },
      { topic: "CS Fundamentals", resource: "GeeksForGeeks — OS, DBMS, OOPs basics", platform: "geeksforgeeks.org", duration: "3 days", notes: "Core CS concepts tested in AMCAT for all tech roles" },
    ],
    elitmus_prep: [
      { topic: "Advanced Mathematics", resource: "CAT Previous Year Quant Section (2018–2023)", platform: "testprepkart.com / Free PDFs", duration: "1 week", notes: "eLitmus difficulty is CAT-level — do not take it lightly; arithmetic shortcuts are essential" },
      { topic: "Problem Solving / Puzzles", resource: "IndiaBix Logical Reasoning Level 3–4", platform: "indiabix.com", duration: "5 days", notes: "Focus on analytical puzzles + seating arrangement — time yourself strictly" },
      { topic: "English Reading Comprehension", resource: "The Hindu editorial daily + RC99 Practice Book", platform: "thehindu.com", duration: "Daily 30 min", notes: "Inference-based questions dominate — practice eliminating wrong answer choices" },
      { topic: "Speed & Accuracy", resource: "Magical Book on Quicker Maths by M. Tyra", platform: "Book", duration: "4 days", notes: "Vedic math shortcuts critical — eLitmus is strict on time" },
    ],
    campus_drive_calendar: [
      { company: "TCS",       typical_months: "Aug–Oct (PPT: July)",    role: "Ninja / Digital / Prime",               ctc_range: "₹3.36–7 LPA",  eligibility: "60% throughout, no active backlogs, all branches" },
      { company: "Infosys",   typical_months: "Sep–Nov",                 role: "Systems Engineer / SP / Power Prog",    ctc_range: "₹3.6–8 LPA",   eligibility: "65% aggregate, no backlogs, B.E/B.Tech/MCA" },
      { company: "Wipro",     typical_months: "Oct–Dec",                 role: "Project Engineer / Turbo / Elite",      ctc_range: "₹3.5–6.5 LPA", eligibility: "60%, no backlogs in last 2 sems, all streams" },
      { company: "Accenture", typical_months: "Aug–Sep (early drive)",   role: "ASE / Associate",                       ctc_range: "₹4.5–8 LPA",   eligibility: "60%, any engineering stream" },
      { company: "Cognizant", typical_months: "Nov–Jan",                 role: "PAT / GenC / GenC Elevate / GenC Pro",  ctc_range: "₹4–5.5 LPA",   eligibility: "60%, CSE/IT/ECE/EEE preferred" },
      { company: "Capgemini", typical_months: "Oct–Nov",                 role: "Analyst / Sr Analyst",                  ctc_range: "₹3.8–5.5 LPA", eligibility: "60%, all engineering branches" },
      { company: "Zoho",      typical_months: "Sep–Nov (ZEAL test)",     role: "Member Technical Staff",                ctc_range: "₹5–15 LPA",    eligibility: "Strong aptitude + coding, 60%+" },
      { company: `${role} Startups`, typical_months: "Year-round (off-campus too)", role, ctc_range: "₹8–25 LPA", eligibility: "GitHub projects + contest rankings often outweigh %" },
    ],
    off_campus_portals: [
      { name: "Naukri Freshers",    url: "naukri.com",        focus: "India's largest portal — filter '0–1 years experience'",   tips: "Complete 100% profile + upload resume for better search visibility; apply within 24h of new postings" },
      { name: "LinkedIn Jobs",      url: "linkedin.com/jobs", focus: "Best for IT, tech, consulting fresher roles",               tips: "Enable 'Open to Work'; filter 'Entry Level' + 'Easy Apply'; connect with college alumni in target companies first" },
      { name: "Internshala Jobs",   url: "internshala.com",   focus: "Fresher-only jobs + internship-to-PPO conversions",        tips: "Set email alerts — these close very fast; apply within 6 hours of new postings" },
      { name: "Unstop (D2C)",       url: "unstop.com",        focus: "Hiring contests, hackathons, and fresher jobs",             tips: "Win company challenges (TCS CodeVita, InfyTQ) — winners get direct interview calls, bypassing written tests" },
      { name: "Instahyre",          url: "instahyre.com",     focus: "AI-matched jobs for freshers — strong for product cos",    tips: "Complete skills test on platform — companies message you directly based on your score" },
      { name: "Cutshort.io",        url: "cutshort.io",       focus: "Tech startup & product company jobs (less MNC noise)",     tips: "Strong GitHub + portfolio increases matches significantly; startups here hire faster than MNCs" },
      { name: "HackerEarth Jobs",   url: "hackerearth.com",   focus: "Coding-challenge-based job matching",                      tips: "Improve HackerEarth ranking — recruiters browse profiles by rank and invite top candidates directly" },
    ],
    four_week_plan: [
      { week: "Week 1 — Resume & Baseline", tasks: [
        "Update resume: one page, quantify every project (e.g. 'Reduced load time 40%'), add GitHub + LinkedIn URLs",
        "Complete 3 AMCAT/eLitmus mock tests — identify and list your weakest sections",
        "Set up profiles on Naukri, LinkedIn, Internshala, Unstop — 100% profile completion",
        "Start 2 LeetCode Easy problems per day (Arrays + Strings focus)",
        "Research the 10 companies most likely to visit your campus — note eligibility criteria for each",
      ]},
      { week: "Week 2 — Aptitude & Skills", tasks: [
        "30 min/day on your weakest aptitude section (Quant / Verbal / Logical)",
        "Solve 10 coding problems covering Arrays, Strings, and Basic Math on LeetCode",
        "Attend an online company info session or recruiter webinar for a target company",
        "Build or update one project — push to GitHub with a clear README + live demo if possible",
        "Apply to 3–5 off-campus roles daily on Naukri and LinkedIn; customise cover note each time",
      ]},
      { week: "Week 3 — Intensive Mock Tests", tasks: [
        "Two full-length timed tests daily (AMCAT or eLitmus official mock pattern)",
        "2 LeetCode Medium problems per day — review optimal solutions, not just 'accepted'",
        "Take actual AMCAT / eLitmus test if not yet done — pH score opens more off-campus doors",
        "Practice 10 HR questions aloud — record yourself, play back and refine",
        "Mock technical interview with a friend or on Pramp.com — DSA + project walkthrough",
      ]},
      { week: "Week 4 — Interview Ready", tasks: [
        "Dress rehearsal: formal attire prepared, document folder ready (all mark sheets, certs)",
        "Prepare 5 STAR stories from your projects (Situation → Task → Action → measurable Result)",
        "Research each shortlisted company's recent news, products, and Glassdoor interview reviews",
        "Final resume review with a senior or mentor — one last polish",
        "Check campus placement portal every morning; reach out to alumni at target companies on LinkedIn",
      ]},
    ],
    hr_tips: [
      "Tell me about yourself: 90 seconds max — Name, Degree + Branch, 1-2 strongest projects, why this company specifically",
      "Why this company? → Name one specific thing you admire: their product, tech stack, recent milestone, or culture value",
      "Salary expected: 'As per company standard' or state the known CTC band; never lowball — it signals lack of awareness",
      "Strengths: one technical ('I debug quickly') + one soft skill ('I communicate blockers early') with a brief example each",
      "Weakness: name a real one (e.g. 'I over-engineer') + what you're actively doing to improve it — shows self-awareness",
      "5-year goal: 'Grow into a senior engineer / tech lead role while contributing to challenging problems here at [company]'",
    ],
    resume_tips: [
      "One page maximum — freshers get 6–10 seconds; use every line wisely on impact, not filler",
      "Lead with a 2-line objective tailored to the specific role — not generic 'seeking a challenging position'",
      "Projects are your experience: Problem → What you built → Measurable result (% improvement / users / accuracy)",
      "Skills: 'Languages: Python, Java | Frameworks: React, FastAPI | Tools: Git, Docker, Supabase' — no rating bars",
      "GPA: include only if ≥ 7.5/10 or ≥ 75% — otherwise leave it off and use the space for a project description",
      "Avoid 'Responsible for', 'Worked on', 'Helped with' — every bullet starts with a strong action verb + quantified result",
    ],
    is_fallback: true,
  };
}

export async function predictPlacement(input: PlacementPrepInput): Promise<PlacementPrepResult> {
  if (!hasApiKey()) {
    return placementFallback(input);
  }
  const prompt = `You are an expert Indian campus placement advisor. A ${input.degree} student in ${input.branch} from "${input.college}" graduating in ${input.graduation_year}${input.cgpa ? ` with CGPA ${input.cgpa}` : ""} wants placement prep${input.target_role ? ` targeting "${input.target_role}" roles` : ""}.

Placement exams: ${input.placement_exams.length > 0 ? input.placement_exams.join(", ") : "AMCAT, eLitmus"}.

Return ONLY valid JSON with no extra text. Keep all string values concise (≤120 chars each).
{
  "amcat_prep":            [{"topic": string, "resource": string, "platform": string, "duration": string, "notes": string}],
  "elitmus_prep":          [{"topic": string, "resource": string, "platform": string, "duration": string, "notes": string}],
  "campus_drive_calendar": [{"company": string, "typical_months": string, "role": string, "ctc_range": string, "eligibility": string}],
  "off_campus_portals":    [{"name": string, "url": string, "focus": string, "tips": string}],
  "four_week_plan":        [{"week": string, "tasks": string[]}],
  "hr_tips":               string[],
  "resume_tips":           string[]
}

Rules:
- AMCAT prep: 5 topics (Quant, Verbal, Logical, Coding/Automata, CS Basics)
- eLitmus prep: 4 topics (Advanced Maths, Problem Solving, English RC, Speed techniques)
- Campus calendar: 6 realistic companies that hire from Indian engineering colleges in ${input.branch}
- Off-campus portals: 5 with fresher-specific tips
- 4-week plan: 4 weeks, max 5 tasks per week, tailored to ${input.branch}
- HR tips: 5 specific fresher interview tips
- Resume tips: 5 specific tips for an engineering fresher resume`;
  try {
    const raw = await callClaude(prompt, 6000);
    return { ...parseJSON<Omit<PlacementPrepResult, "is_fallback">>(raw), is_fallback: false };
  } catch (err) {
    console.error("[predictPlacement] AI parse error:", err);
    return placementFallback(input);
  }
}
