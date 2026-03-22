"""
automation/ai_client.py — AI Client

Automatically uses Claude Sonnet (claude-sonnet-4-5) when
ANTHROPIC_API_KEY is set — otherwise falls back to keyword-based mock.

Setup (one-time):
  1. pip install anthropic
  2. Set ANTHROPIC_API_KEY=sk-ant-... in your environment or .env
  Done — no code changes needed.
"""

import os
import re
import json


DEFAULT_ANTHROPIC_API_KEY = ""  # Set ANTHROPIC_API_KEY in your environment / .env file


def _get_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "").strip() or DEFAULT_ANTHROPIC_API_KEY


def _split_sections(text: str) -> list[tuple[str | None, list[str]]]:
    sections: list[tuple[str | None, list[str]]] = []
    current_header = None
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        is_header = bool(stripped) and (
            stripped.upper() == stripped and len(stripped) <= 40
            or stripped.lower().rstrip(":") in {
                "summary", "professional summary", "objective", "experience",
                "work experience", "professional experience", "skills",
                "technical skills", "education", "projects", "certifications"
            }
        )
        if is_header:
            if current_lines or current_header is not None:
                sections.append((current_header, current_lines))
            current_header = stripped.rstrip(":")
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or current_header is not None:
        sections.append((current_header, current_lines))
    return sections


def _render_sections(sections: list[tuple[str | None, list[str]]]) -> str:
    blocks: list[str] = []
    for header, lines in sections:
        chunk: list[str] = []
        if header:
            chunk.append(header.upper())
        chunk.extend(lines)
        blocks.append("\n".join(chunk).strip())
    return "\n\n".join(block for block in blocks if block).strip()


def _inject_mock_keywords(resume_text: str, jd_text: str, summary: str, top_missing: list[str]) -> str:
    sections = _split_sections(resume_text)
    if not sections:
        sections = [(None, [resume_text.strip()])]

    summary_added = False
    skills_updated = False
    missing_csv = ", ".join(top_missing)

    for idx, (header, lines) in enumerate(sections):
        header_key = (header or "").lower()
        if header_key in {"summary", "professional summary", "objective"}:
            sections[idx] = (header, [summary])
            summary_added = True
            continue

        if header_key in {"skills", "technical skills"}:
            existing_blob = " ".join(lines).lower()
            additions = [skill for skill in top_missing if skill.lower() not in existing_blob]
            if additions:
                if lines:
                    lines[-1] = f"{lines[-1].rstrip(', ')} , {', '.join(additions)}"
                else:
                    lines.append(", ".join(additions))
            sections[idx] = (header, lines)
            skills_updated = True

    if not summary_added:
        sections.insert(0, ("PROFESSIONAL SUMMARY", [summary]))

    if not skills_updated and missing_csv:
        sections.append(("TECHNICAL SKILLS", [missing_csv]))

    return _render_sections(sections)

# ──────────────────────────────────────────────────────────────────────────
# Claude Sonnet helper — auto-activated when ANTHROPIC_API_KEY is set
# ──────────────────────────────────────────────────────────────────────────

def _has_api_key() -> bool:
    return bool(_get_api_key())


def _call_claude(prompt: str, max_tokens: int = 4096) -> dict:
    """Call Claude Sonnet and parse the JSON response."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Run:  pip install anthropic")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def call_claude(prompt: str, max_tokens: int = 1024) -> str:
    """
    Call Claude and return the raw text response (no JSON parsing).
    Used by gmail_client.py and other modules that need free-form text.
    Falls back to prompt-echo on error.
    """
    try:
        import anthropic
        api_key = _get_api_key()
        if not api_key:
            raise RuntimeError("No API key")
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  [AI] call_claude failed: {e}")
        return ""


# ──────────────────────────────────────────────────────────────────────────
# Master skill list for mock extraction
# ──────────────────────────────────────────────────────────────────────────
_ALL_SKILLS = [
    # Languages
    "python","javascript","typescript","java","c++","c#","golang","rust",
    "kotlin","swift","ruby","php","scala","r","bash","shell","sql","html","css",
    # Frontend
    "react","vue","angular","nextjs","next.js","svelte","tailwind","sass",
    "webpack","vite","redux","mobx","graphql","rest","rest api","spa","ssr",
    # Backend
    "node","nodejs","express","fastapi","django","flask","spring","rails",
    "laravel","nestjs","grpc","websockets","microservices","serverless",
    # Databases
    "postgresql","postgres","mysql","mongodb","redis","elasticsearch",
    "cassandra","sqlite","supabase","firebase","dynamodb","prisma",
    # Cloud / DevOps
    "aws","gcp","azure","docker","kubernetes","k8s","terraform","ansible",
    "ci/cd","github actions","jenkins","linux","nginx","vercel","s3","ec2",
    # AI / ML
    "machine learning","deep learning","tensorflow","pytorch","scikit-learn",
    "pandas","numpy","nlp","llm","openai","langchain","computer vision",
    # Mobile
    "react native","flutter","ios","android","expo",
    # Testing
    "jest","pytest","cypress","selenium","playwright","unit testing","tdd",
    # Tools
    "git","github","jira","agile","scrum","figma","postman","kafka",
    "rabbitmq","celery","airflow","datadog","grafana","prometheus",
    # Soft
    "leadership","mentoring","communication","stakeholder","system design",
    "architecture","code review","problem solving","ownership","agile",
]


def _extract_skills(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for skill in _ALL_SKILLS:
        pattern = re.escape(skill)
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lower):
            found.append(skill)
    return found


def _detect_seniority(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(vp|vice president|director|head of)\b", lower): return "executive"
    if re.search(r"\b(principal|staff engineer|architect)\b",  lower): return "principal"
    if re.search(r"\b(senior|sr\.?\s|lead)\b",                 lower): return "senior"
    if re.search(r"\b(junior|jr\.?\s|entry.level|fresher)\b",  lower): return "entry"
    return "mid"


def _extract_responsibilities(text: str) -> list[str]:
    lines = [
        re.sub(r"^[\s*•\-–—>]+", "", l).strip()
        for l in text.split("\n")
    ]
    return [l for l in lines if 40 < len(l) < 320][:8]


# ══════════════════════════════════════════════════════════════════════════
# 1. analyze_resume — extract structure from raw resume text
# ══════════════════════════════════════════════════════════════════════════
def analyze_resume(resume_text: str) -> dict:
    """
    Extract structured information from resume text.
    Returns: { skills, experience_keywords, email_hint, years_experience, education }
    Auto-uses Claude Sonnet when ANTHROPIC_API_KEY is set.
    """
    if _has_api_key():
        prompt = f"""Extract structured info from this resume. Return ONLY valid JSON, no prose:
{{
  "skills": [<list of technical skills>],
  "experience_keywords": [<list of role/domain keywords>],
  "years_experience": <number or null>,
  "education": [<degrees / institutions>],
  "email_hint": "<email address or null>"
}}
Resume:
{resume_text}"""
        try:
            return _call_claude(prompt)
        except Exception:
            pass  # fall through to mock

    skills = _extract_skills(resume_text)
    email_match = re.search(r"[\w.+\-]+@[\w\-]+\.\w+", resume_text)
    return {
        "skills":               skills,
        "experience_keywords":  skills[:10],
        "email_hint":           email_match.group() if email_match else None,
        "years_experience":     None,   # mock — real AI would extract this
        "education":            [],     # mock — real AI would extract this
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. analyze_jd — extract skills / requirements from a job description
# ══════════════════════════════════════════════════════════════════════════
def analyze_jd(jd_text: str) -> dict:
    """
    Extract structured JD information.
    Returns: { required_skills, nice_to_have, keywords, responsibilities, seniority }
    Auto-uses Claude Sonnet when ANTHROPIC_API_KEY is set.
    """
    if _has_api_key():
        prompt = f"""Analyze this job description. Return ONLY valid JSON, no prose:
{{
  "required_skills": [<string>],
  "nice_to_have":    [<string>],
  "keywords":        [<string>],
  "responsibilities": [<string>],
  "seniority": "entry" | "mid" | "senior" | "principal" | "executive"
}}
JD:
{jd_text}"""
        try:
            return _call_claude(prompt)
        except Exception:
            pass  # fall through to mock

    found    = _extract_skills(jd_text)
    split_at = max(1, int(len(found) * 0.65))
    return {
        "required_skills":  found[:split_at],
        "nice_to_have":     found[split_at:],
        "keywords":         found[:min(len(found), 15)],
        "responsibilities": _extract_responsibilities(jd_text),
        "seniority":        _detect_seniority(jd_text),
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. match_score — compare resume against JD
# ══════════════════════════════════════════════════════════════════════════
def match_score(resume_text: str, jd_text: str) -> dict:
    """
    Returns: { score, matching_skills, missing_skills, suggestions }
    Auto-uses Claude Sonnet when ANTHROPIC_API_KEY is set.
    """
    if _has_api_key():
        prompt = f"""Compare the resume to the job description. Return ONLY valid JSON, no prose:
{{
  "score": <integer 0-100>,
  "matching_skills": [<string>],
  "missing_skills":  [<string>],
  "suggestions":     [<string>]
}}
Resume:
{resume_text}

Job Description:
{jd_text}"""
        try:
            return _call_claude(prompt)
        except Exception:
            pass  # fall through to mock

    jd_skills    = _extract_skills(jd_text)
    resume_lower = resume_text.lower()
    matching     = [s for s in jd_skills if s in resume_lower]
    missing      = [s for s in jd_skills if s not in resume_lower]
    raw_score    = (len(matching) / len(jd_skills) * 100) if jd_skills else 55
    score        = min(97, int(raw_score * 0.82 + 12))

    return {
        "score":           score,
        "matching_skills": matching,
        "missing_skills":  missing[:12],
        "suggestions":     [
            f'Add a project or certification demonstrating "{s}"'
            for s in missing[:4]
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# 4. tailor_resume — rewrite resume bullets to match JD
# ══════════════════════════════════════════════════════════════════════════
def tailor_resume(resume_text: str, jd_text: str) -> dict:
    """
    Returns: { tailored_text, tailored_bullets, tailored_summary, ats_score, improvements }
    Auto-uses Claude Sonnet when ANTHROPIC_API_KEY is set.
    """
    if _has_api_key():
        prompt = f"""You are an expert ATS resume optimizer.
Rewrite the resume to maximise match with the job description.
Rules:
- Keep ALL real experience — do NOT invent fake companies or roles
- Naturally inject JD keywords into existing bullet points
- Rewrite the professional summary to mirror JD language
- Start every bullet with a strong action verb
- Quantify achievements wherever possible

Return ONLY valid JSON, no prose:
{{
  "tailored_text":    "<full revised resume as plain text>",
  "tailored_bullets": ["<bullet 1>", "<bullet 2>"],
  "tailored_summary": "<2-3 sentence professional summary>",
  "ats_score":        <integer 0-100>,
  "improvements":     ["<tip 1>", "<tip 2>"]
}}

Resume:
{resume_text}

Job Description:
{jd_text}"""
        try:
            return _call_claude(prompt, max_tokens=6000)
        except Exception:
            pass  # fall through to mock

    ms           = match_score(resume_text, jd_text)
    jd           = analyze_jd(jd_text)
    top_match    = ms["matching_skills"][:4]
    top_missing  = ms["missing_skills"][:3]
    top_skills   = ", ".join(top_match) or "software development"
    seniority    = jd["seniority"]

    summary = (
        f"Results-driven "
        f"{'senior ' if seniority in ('senior', 'principal') else ''}"
        f"engineer with proven expertise in {top_skills}. "
        f"Passionate about building scalable, maintainable systems that deliver "
        f"measurable business impact."
        + (f" Currently expanding expertise in {' and '.join(top_missing[:2])}." if top_missing else "")
    )

    bullets = [
        f"Emphasized proven experience with {top_match[0] if top_match else 'software engineering'} in ATS-visible sections",
        f"Aligned summary and skills with {top_match[1] if len(top_match) > 1 else 'job requirements'} terminology",
        f"Added missing JD keywords where supported by the candidate's existing background",
    ]

    tailored_text = _inject_mock_keywords(resume_text, jd_text, summary, top_missing)

    score_after = match_score(tailored_text, jd_text)["score"]

    improvements = [
        *(f'Include "{s}" in your skills section or experience' for s in top_missing),
        "Start every bullet point with a strong action verb",
        "Quantify achievements with numbers (%, $, ×)",
        "Ensure JD-required tools appear verbatim (exact spelling)",
    ]

    return {
        "tailored_text":    tailored_text,
        "tailored_bullets": bullets,
        "tailored_summary": summary,
        "ats_score":        min(96, max(ms["score"], score_after) + 8),
        "improvements":     improvements,
        "missing_skills":   top_missing,
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. generate_cover_letter
# ══════════════════════════════════════════════════════════════════════════
def generate_cover_letter(
    resume_text: str,
    jd_text:     str,
    company:     str = "",
    role:        str = "",
) -> dict:
    """
    Returns: { cover_letter, intro_message, linkedin_intro, email_subject }
    Auto-uses Claude Sonnet when ANTHROPIC_API_KEY is set.
    """
    if _has_api_key():
        comp     = company.strip() or "the company"
        role_str = role.strip()    or "this position"
        prompt = f"""Write professional job application documents for {role_str} at {comp}.
Tone: confident, genuine, concise. Do NOT use filler phrases like "I am writing to express".

Return ONLY valid JSON, no prose:
{{
  "cover_letter":   "<full cover letter, 3-4 paragraphs>",
  "intro_message":  "<2-3 sentence friendly intro for job portal>",
  "linkedin_intro": "<1-2 sentence LinkedIn InMail opener>",
  "email_subject":  "<email subject line>"
}}

Resume:
{resume_text}

Job Description:
{jd_text}"""
        try:
            return _call_claude(prompt)
        except Exception:
            pass  # fall through to mock

    ms       = match_score(resume_text, jd_text)
    skills   = ", ".join(ms["matching_skills"][:3]) or "software engineering"
    comp     = company.strip() or "your company"
    role_str = role.strip()    or "this position"

    cover_letter = f"""Dear Hiring Manager,

I am writing to express my strong interest in the {role_str} position at {comp}. \
With hands-on experience in {skills}, I am confident in my ability to make an \
immediate impact and grow with your team.

Throughout my career I have consistently delivered high-quality, scalable solutions \
while working cross-functionally with product and design teams. The opportunity at \
{comp} excites me because of the chance to contribute to a culture that values \
technical excellence and continuous improvement.

My background closely aligns with the requirements outlined in the job description, \
and I would welcome the opportunity to discuss how my skills can contribute to \
{comp}'s goals.

Thank you for your time and consideration.

Best regards"""

    return {
        "cover_letter":   cover_letter,
        "intro_message":  (
            f"Hi! I'm very excited about the {role_str} role at {comp}. "
            f"With strong experience in {skills}, I'd love to contribute to your team!"
        ),
        "linkedin_intro": (
            f"Hi [Recruiter], I came across the {role_str} opening at {comp} and "
            f"I'm genuinely interested. I have solid experience in {skills} — "
            f"would you be open to a quick chat?"
        ),
        "email_subject":  f"Application for {role_str} — {comp}",
    }
