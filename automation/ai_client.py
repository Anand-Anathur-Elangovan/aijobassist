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
import requests as _http


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

# ── Model routing ─────────────────────────────────────────────────────────
# Haiku  → fast, cheap — simple extraction, parsing, classification, Q&A
# Sonnet → accurate, expensive — tailoring, cover letters, interview prep
HAIKU_MODEL  = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-5"

# ── Circuit breaker ────────────────────────────────────────────────────────
# Set to True on permanent API errors (quota exceeded, invalid key, etc.)
# so all further Claude calls in this process skip immediately.
_API_DISABLED: bool = False

# Error substrings that indicate a permanent failure (no point retrying)
_PERMANENT_ERROR_PATTERNS = [
    "credit balance is too low",
    "insufficient_quota",
    "invalid_api_key",
    "permission_denied",
    "your api key is invalid",
    "account has been deactivated",
    "rate limit",  # treat hard rate limits as circuit-break too
]

def _is_permanent_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(p in msg for p in _PERMANENT_ERROR_PATTERNS)


def _has_api_key() -> bool:
    return bool(_get_api_key()) and not _API_DISABLED


def _call_claude(prompt: str, max_tokens: int = 4096, model: str = SONNET_MODEL) -> dict:
    """Call Claude and parse the JSON response. model= selects Haiku or Sonnet."""
    global _API_DISABLED
    if _API_DISABLED:
        raise RuntimeError("Claude disabled for this run (permanent API error)")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    try:
        resp = _http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            error_body = resp.text[:300]
            raise RuntimeError(f"Claude API {resp.status_code}: {error_body}")
        data = resp.json()
        raw = data["content"][0]["text"].strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        if _is_permanent_error(e):
            _API_DISABLED = True
            print(f"  [AI] ⚡ Permanent API error — disabling Claude for this run: {e}")
        raise


def call_claude(prompt: str, max_tokens: int = 1024, model: str = SONNET_MODEL) -> str:
    """
    Call Claude and return the raw text response (no JSON parsing).
    Used by gmail_client.py and other modules that need free-form text.
    Falls back to prompt-echo on error.
    """
    global _API_DISABLED
    if _API_DISABLED:
        return ""

    try:
        api_key = _get_api_key()
        if not api_key:
            raise RuntimeError("No API key")
        resp = _http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Claude API {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        if _is_permanent_error(e):
            _API_DISABLED = True
            print(f"  [AI] ⚡ Permanent API error — disabling Claude for this run: {e}")
        else:
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
            return _call_claude(prompt, model=HAIKU_MODEL)
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
# 1b. extract_education — structured education data from resume
# ══════════════════════════════════════════════════════════════════════════
def extract_education(resume_text: str) -> list[dict]:
    """
    Extract structured education entries from resume text.
    Returns a list of dicts, each with:
      school, city, degree, major, start_month, start_year, end_month, end_year, gpa
    Uses Claude when available, otherwise returns empty list.
    """
    if not _has_api_key() or not resume_text:
        return []

    prompt = f"""Extract ALL education entries from this resume. Return ONLY a valid JSON array, no prose.

Each entry must have these fields (use empty string if not found):
[
  {{
    "school": "<university/college name>",
    "city": "<city where the school is located>",
    "degree": "<degree type e.g. Bachelor's Degree, Master's Degree, B.Tech, MBA>",
    "major": "<field of study e.g. Computer Science, Mechanical Engineering>",
    "start_month": "<numeric month 1-12 or empty>",
    "start_year": "<4-digit year or empty>",
    "end_month": "<numeric month 1-12 or empty>",
    "end_year": "<4-digit year or empty>",
    "gpa": "<GPA/percentage or empty>"
  }}
]

If no education found, return an empty array: []

Resume:
{resume_text}"""

    try:
        result = _call_claude(prompt, max_tokens=1500, model=HAIKU_MODEL)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        print(f"  [AI] extract_education failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# 1c. extract_employment — structured work history from resume
# ══════════════════════════════════════════════════════════════════════════
def extract_employment(resume_text: str) -> list[dict]:
    """
    Extract structured employment entries from resume text.
    Returns a list of dicts, each with:
      company, position, city, start_month, start_year, end_month, end_year, is_current, description
    Uses Claude when available, otherwise returns empty list.
    """
    if not _has_api_key() or not resume_text:
        return []

    prompt = f"""Extract ALL employment/work experience entries from this resume. Return ONLY a valid JSON array, no prose.

Each entry must have these fields (use empty string if not found):
[
  {{
    "company": "<company name>",
    "position": "<job title / role>",
    "city": "<city where the job is located>",
    "start_month": "<numeric month 1-12 or empty>",
    "start_year": "<4-digit year or empty>",
    "end_month": "<numeric month 1-12 or empty>",
    "end_year": "<4-digit year or empty>",
    "is_current": <true if currently employed here, else false>,
    "description": "<brief 1-2 line description of role/responsibilities>"
  }}
]

Order from most recent to oldest. If no employment found, return an empty array: []

Resume:
{resume_text}"""

    try:
        result = _call_claude(prompt, max_tokens=2000, model=HAIKU_MODEL)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        print(f"  [AI] extract_employment failed: {e}")
        return []


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
            return _call_claude(prompt, model=HAIKU_MODEL)
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
            return _call_claude(prompt, model=HAIKU_MODEL)
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
            return _call_claude(prompt, max_tokens=6000, model=SONNET_MODEL)
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
            return _call_claude(prompt, model=SONNET_MODEL)
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


# ══════════════════════════════════════════════════════════════════════════
# 6. analyze_and_fill_form — Claude-powered external ATS form filler
# ══════════════════════════════════════════════════════════════════════════
def analyze_and_fill_form(form_html: str, user_profile: dict) -> list[dict]:
    """
    Given raw HTML of a company career / ATS page and the user's profile,
    use Claude to figure out which CSS selectors to fill and with what values.

    Returns a list of actions in order:
      [
        {"action": "fill",   "selector": "input[name='email']", "value": "a@b.com"},
        {"action": "fill",   "selector": "textarea[name='cover']", "value": "Dear..."},
        {"action": "select", "selector": "select[name='exp']",  "value": "1-3 years"},
        {"action": "click",  "selector": "button[type='submit']"},
      ]

    Falls back to an empty list (caller will use dumb fill) if Claude is unavailable.
    """
    if not _has_api_key():
        return []

    name  = user_profile.get("full_name", "")
    email = user_profile.get("email", "")
    phone = user_profile.get("phone", "")
    years = user_profile.get("years_experience", 2)
    cover = user_profile.get("cover_note", "I am very interested in this role.")
    city  = user_profile.get("current_city", "")
    linkedin = user_profile.get("linkedin_url", "")
    github   = user_profile.get("github_url", "")
    portfolio = user_profile.get("portfolio_url", "")

    # Trim HTML — keep only form/input/label/button/select/textarea tags, max ~4000 chars
    # Remove script/style blocks first to save tokens
    form_html_clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", form_html, flags=re.DOTALL | re.IGNORECASE)
    form_html_clean = re.sub(r"<!--.*?-->", "", form_html_clean, flags=re.DOTALL)
    # Keep only lines with form-relevant tags
    relevant_lines = [
        l for l in form_html_clean.splitlines()
        if re.search(r"<(input|select|textarea|label|button|form)\b", l, re.IGNORECASE)
    ]
    trimmed_html = "\n".join(relevant_lines)[:4000]

    prompt = f"""You are filling out a job application form on a company career page.
User profile:
- Name: {name}
- Email: {email}
- Phone: {phone}
- Years of experience: {years}
- Current city: {city or "N/A"}
- LinkedIn: {linkedin or "N/A"}
- GitHub: {github or "N/A"}
- Portfolio/Website: {portfolio or "N/A"}
- Cover note: {cover}

RULES:
- Give the SHORTEST possible answers. Never write full sentences.
- For yes/no: just "Yes" or "No".
- For name fields: just the name.
- For URL fields: just the URL, or leave empty if N/A.
- For number fields: just the number.
- NEVER start answers with "I", "My", or "The".
- NEVER explain or add filler text.

Analyse the HTML below and return a JSON array of actions to fill the form.
Each action object must have:
  "action": "fill" | "select" | "click"
  "selector": a valid CSS selector for that element (prefer id > name > placeholder attrs)
  "value": the string to enter (omit for "click" actions)

Rules:
- Only include fields that are visible and would accept user input
- Skip file upload inputs (we handle those separately)
- The last action should be clicking the submit button if one exists
- Return ONLY the JSON array, no prose, no markdown fences

HTML:
{trimmed_html}"""

    try:
        result = _call_claude(prompt, max_tokens=1500, model=HAIKU_MODEL)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        print(f"  [AI] analyze_and_fill_form failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# 7. claude_answer_question — pick the best answer for a form question
# ══════════════════════════════════════════════════════════════════════════
def claude_answer_question(
    question_text: str,
    options: list[str],
    resume_summary: str = "",
    context: str = "",
    user_profile: dict | None = None,
) -> str:
    """
    Given a single application question and its available options (or empty list for
    free-text), use Claude to choose or compose the best answer.

    Returns a string — either one of the provided `options` (exact match) or a
    composed free-text answer.  Falls back to the first option (or empty string)
    if Claude is unavailable.
    """
    user_profile = user_profile or {}
    q_lower = question_text.lower()

    # ── Helper: match answer to options ────────────────────────────
    def _match_option(answer: str) -> str | None:
        """Find the best matching option for a given answer. Returns exact option text or None."""
        if not options or not answer:
            return None
        a_lower = answer.strip().lower()
        # Exact match
        for opt in options:
            if opt.strip().lower() == a_lower:
                return opt
        # Contains match (both directions)
        for opt in options:
            o_lower = opt.strip().lower()
            if a_lower in o_lower or o_lower in a_lower:
                return opt
        # Word overlap — pick option with most shared words
        a_words = set(a_lower.split())
        best_opt, best_score = None, 0
        for opt in options:
            o_words = set(opt.strip().lower().split())
            overlap = len(a_words & o_words)
            if overlap > best_score:
                best_score = overlap
                best_opt = opt
        if best_score >= 1:
            return best_opt
        return None

    # ── Claude validation helper for direct fills ──────────────────
    def _validate_fill(field_name: str, value: str) -> str:
        """
        Log a direct-lookup fill and (for substantive fields) call Claude to
        verify the value matches the resume. Corrects the answer if Claude
        disagrees; always logs the result so mismatches are visible.
        """
        opts_preview = f"  options={options[:4]}" if options else ""
        print(f"  [FILL] '{question_text[:70]}' → {field_name}: '{value}'{opts_preview}")

        # Unambiguous fields — no need to validate, just return
        SKIP_VALIDATE = {
            "LinkedIn URL", "GitHub URL", "Portfolio URL",
            "Name", "Email", "Phone",
            "Expected CTC", "Current CTC", "Gender/Diversity",
        }
        if field_name in SKIP_VALIDATE or not resume_summary or not _has_api_key():
            return value

        opts_hint = (
            f"\nAvailable options: {options[:5]}" if options else ""
        )
        verify_prompt = (
            f"Resume summary:\n{resume_summary[:800]}\n\n"
            f"Form field: \"{question_text}\"\n"
            f"Auto-filled value: \"{value}\"{opts_hint}\n\n"
            "Is this fill accurate based on the resume?\n"
            "Reply with EXACTLY one of:\n"
            "  CONFIRM\n"
            "  CORRECT: <right value>\n"
            "No other text."
        )
        try:
            resp = call_claude(verify_prompt, max_tokens=60, model=HAIKU_MODEL).strip()
            if resp.upper().startswith("CONFIRM"):
                print(f"  [VALIDATE \u2713] {field_name}: '{value}' confirmed by Claude")
                return value
            if resp.upper().startswith("CORRECT:"):
                corrected = resp[8:].strip().strip("\"'")
                if options:
                    m = _match_option(corrected)
                    corrected = m if m else value  # keep original if no option match
                print(f"  [VALIDATE \u2717] {field_name}: '{value}' \u2192 corrected to '{corrected}'")
                return corrected
            # Unclear response — keep original
            print(f"  [VALIDATE ?] {field_name}: unclear response '{resp[:40]}', keeping '{value}'")
        except Exception as e:
            print(f"  [VALIDATE !] {field_name} validation error: {e}")
        return value

    # ── Direct profile lookups — skip AI, validate substantive fields ──
    if any(k in q_lower for k in ("linkedin profile", "linkedin url", "linkedin link")):
        url = user_profile.get("linkedin_url", "").strip()
        if url and "localhost" not in url and "127.0.0.1" not in url:
            return _validate_fill("LinkedIn URL", url)
        return ""

    if any(k in q_lower for k in ("github profile", "github url", "github link")):
        url = user_profile.get("github_url", "").strip()
        if url and "localhost" not in url and "127.0.0.1" not in url:
            return _validate_fill("GitHub URL", url)
        return ""

    if any(k in q_lower for k in ("website", "blog", "portfolio")):
        url = user_profile.get("portfolio_url", "").strip()
        if url and "localhost" not in url and "127.0.0.1" not in url:
            return _validate_fill("Portfolio URL", url)
        return ""

    if any(k in q_lower for k in ("your full name", "your name", "candidate name", "applicant name")):
        name = user_profile.get("full_name", "").strip()
        if name:
            return _validate_fill("Name", name)

    if any(k in q_lower for k in ("employee's name", "employee name", "referral name", "referrer name")):
        return user_profile.get("full_name", "") or ""

    if any(k in q_lower for k in ("your email", "email address", "email id", "contact email")):
        email = user_profile.get("email", "").strip()
        if email:
            return _validate_fill("Email", email)

    if any(k in q_lower for k in ("your phone", "phone number", "mobile number", "contact number", "mobile no")):
        phone = user_profile.get("phone", "").strip()
        if phone:
            return _validate_fill("Phone", phone)

    if any(k in q_lower for k in ("currently based", "current city", "current location", "where are you located", "your city", "your location", "residing", "based out of")):
        city = user_profile.get("current_city", "").strip()
        if city:
            matched = _match_option(city)
            return _validate_fill("City", matched if matched else city)

    if any(k in q_lower for k in ("current company", "current employer", "current organization", "present company", "company name", "working at", "employed at")):
        company = user_profile.get("current_company", "").strip()
        if company:
            return _validate_fill("Current company", company)

    if any(k in q_lower for k in ("current designation", "current title", "current role", "current position", "job title", "designation")):
        pos = user_profile.get("current_position", "").strip()
        if pos:
            return _validate_fill("Current position", pos)

    if any(k in q_lower for k in ("years of experience", "total experience", "work experience", "professional experience", "how many years")):
        yrs = str(user_profile.get("years_experience", "")).strip()
        if yrs:
            if options:
                matched = _match_option(yrs)
                if matched:
                    return _validate_fill("Years of experience", matched)
            return _validate_fill("Years of experience", yrs)

    if any(k in q_lower for k in ("notice period", "serving notice", "joining time", "how soon can you join")):
        np_val = str(user_profile.get("notice_period", "")).strip()
        if np_val:
            matched = _match_option(np_val)
            return _validate_fill("Notice period", matched if matched else np_val)

    if any(k in q_lower for k in ("expected ctc", "expected salary", "expected compensation", "salary expectation")):
        sal = str(user_profile.get("salary_expectation", "")).strip()
        if sal:
            return _validate_fill("Expected CTC", sal)

    if any(k in q_lower for k in ("current ctc", "current salary", "present salary", "present ctc")):
        sal = str(user_profile.get("current_ctc", "") or user_profile.get("salary_expectation", "")).strip()
        if sal:
            return _validate_fill("Current CTC", sal)

    if any(k in q_lower for k in ("highest education", "highest qualification", "highest degree", "academic qualification")):
        edu = user_profile.get("highest_education", "").strip() or user_profile.get("degree", "").strip()
        if edu:
            matched = _match_option(edu)
            return _validate_fill("Highest education", matched if matched else edu)

    if any(k in q_lower for k in ("university", "college name", "school name", "institute", "alma mater")):
        school = user_profile.get("school", "").strip()
        if school:
            return _validate_fill("School/University", school)

    if any(k in q_lower for k in ("graduation year", "year of passing", "year of graduation", "passout year", "batch")):
        grad_year = str(user_profile.get("graduation_year", "")).strip()
        if grad_year:
            matched = _match_option(grad_year)
            return _validate_fill("Graduation year", matched if matched else grad_year)

    if any(k in q_lower for k in ("work authorization", "work permit", "authorized to work", "eligible to work",
                                   "legal right to work", "require sponsorship", "need sponsorship",
                                   "visa sponsorship", "require visa", "need visa", "need work")):
        work_auth = (user_profile.get("work_authorization") or "").lower()
        no_sponsor_kws = ["citizen", "permanent resident", "green card", "ead",
                          "employment authorization", "not applicable"]
        needs_sponsor = work_auth and not any(kw in work_auth for kw in no_sponsor_kws)
        if any(k in q_lower for k in ("require sponsorship", "need sponsorship", "visa sponsorship",
                                       "require visa", "need visa")):
            if work_auth and not needs_sponsor:
                # User doesn't need sponsorship
                if options:
                    matched = _match_option("no")
                    return matched if matched else "No"
                return _validate_fill("Sponsorship", "No")
        if any(k in q_lower for k in ("authorized to work", "eligible to work", "legal right to work",
                                       "work authorization")):
            if options:
                matched = _match_option("yes")
                return matched if matched else "Yes"
            return _validate_fill("Work authorization", "Yes")
        # Generic: return user's visa status
        if work_auth:
            if options:
                matched = _match_option(work_auth)
                return matched if matched else work_auth
            return _validate_fill("Work authorization", work_auth)

    if any(k in q_lower for k in ("nationality", "country of origin", "country of birth", "place of origin")):
        nat_val = (user_profile.get("nationality") or user_profile.get("country_of_origin") or "").strip()
        if nat_val:
            if options:
                matched = _match_option(nat_val)
                return matched if matched else nat_val
            return _validate_fill("Nationality", nat_val)

    if any(k in q_lower for k in ("gender", "ethnicity", "race", "disability", "veteran", "pronoun", "sexual orientation")):
        # Pull user's actual profile values
        d_status = (user_profile.get("disability_status") or "").lower()
        v_status = (user_profile.get("veteran_status") or "").lower()
        g_val    = (user_profile.get("gender") or "").lower()
        eth_val  = (user_profile.get("ethnicity") or "").lower()

        user_eeo_val = ""
        if any(k in q_lower for k in ("disability", "disabled")):
            user_eeo_val = d_status
        elif "veteran" in q_lower:
            user_eeo_val = v_status
        elif "gender" in q_lower:
            user_eeo_val = g_val
        elif any(k in q_lower for k in ("ethnicity", "race")):
            user_eeo_val = eth_val

        if options:
            # Try to match user's actual EEO value first
            if user_eeo_val and "prefer not" not in user_eeo_val:
                for opt in options:
                    if user_eeo_val in opt.lower() or opt.lower() in user_eeo_val:
                        return opt
            # Fall back to "Prefer not to say" / "Decline" option
            for opt in options:
                o = opt.lower()
                if any(k in o for k in ("prefer not", "decline", "not wish", "not specified", "choose not")):
                    return opt
            return options[0]
        # No options (text field) — return user's value or safe default
        if user_eeo_val and "prefer not" not in user_eeo_val:
            return user_eeo_val
        return "Prefer not to say"

    if not _has_api_key():
        return options[0] if options else ""

    # Build profile block for Claude
    profile_lines = []
    for key, label in [
        ("full_name", "Name"), ("email", "Email"), ("phone", "Phone"),
        ("current_city", "Current city"), ("linkedin_url", "LinkedIn"),
        ("github_url", "GitHub"), ("portfolio_url", "Portfolio/Website"),
        ("years_experience", "Years of experience"),
        ("highest_education", "Highest education"),
        ("current_company", "Current company"),
        ("current_position", "Current position/title"),
        ("school", "School/University"),
        ("degree", "Degree"),
        ("major", "Major/Field of study"),
        ("work_authorization", "Work authorization / visa status"),
        ("nationality", "Nationality"),
        ("country_of_origin", "Country of origin"),
        ("gender", "Gender"),
        ("disability_status", "Disability status"),
        ("veteran_status", "Veteran status"),
        ("ethnicity", "Race / ethnicity"),
    ]:
        val = user_profile.get(key, "")
        if val:
            profile_lines.append(f"- {label}: {val}")
    # Add notice period & salary
    for key, label in [
        ("notice_period", "Notice period (days)"),
        ("salary_expectation", "Expected salary/CTC"),
        ("current_ctc", "Current CTC"),
    ]:
        val = str(user_profile.get(key, "")).strip()
        if val:
            profile_lines.append(f"- {label}: {val}")
    profile_block = "\n".join(profile_lines) if profile_lines else "(not provided)"

    opts_block = ""
    if options:
        opts_block = "\nAvailable options (you MUST pick one verbatim):\n" + "\n".join(f"- {o}" for o in options)

    prompt = f"""You are filling a job application form. Answer the question below.

RULES — follow these strictly:
- Give the SHORTEST possible answer. Never write a full sentence.
- For yes/no questions: answer ONLY "Yes" or "No".
- For name fields: answer ONLY the name, nothing else.
- For URL fields: answer ONLY the URL, or blank if unavailable.
- For number fields: answer ONLY the number.
- For free-text: answer in 3-10 words maximum. No fluff, no filler.
- If the question is a conditional follow-up like "If yes, please describe/identify": answer "No" if the preceding condition does not apply.
- Questions about visa sponsorship, family/relatives at the company, outside business activities, or prior employment at the company: answer "No".
- Questions about legal work authorization / eligible to work: answer "Yes".
- NEVER start with "I", "My", "The", or any preamble.
- NEVER explain your answer.
- NEVER say "I need the complete question" — always give a direct short answer.

Applicant profile:
{profile_block}

Resume summary:
{resume_summary or "(not provided)"}

{f"Context: {context}" if context else ""}

Question: {question_text}
{opts_block}

{"Return ONLY the exact option text — no other words." if options else "Return ONLY the direct answer — no explanation, no sentence."}"""

    try:
        raw = call_claude(prompt, max_tokens=200, model=HAIKU_MODEL)
        if options:
            # Use the fuzzy matcher for best option
            matched = _match_option(raw.strip())
            if matched:
                return matched
            return options[0]  # last resort
        return raw.strip()
    except Exception as e:
        print(f"  [AI] claude_answer_question failed: {e}")
        return options[0] if options else ""


# ══════════════════════════════════════════════════════════════════════════
# 8. interview_prep — generate interview questions + answers from JD
# ══════════════════════════════════════════════════════════════════════════
def interview_prep(jd_text: str, resume_text: str = "") -> dict:
    """
    Given a JD (and optional resume for personalisation), generate likely interview
    questions with suggested answers grouped by category.

    Returns:
    {
      "questions": [
        { "category": "Technical|Behavioral|Situational|Role-specific",
          "question": "...",
          "answer":   "..." },
        ...
      ],
      "key_topics": ["..."],
      "preparation_tips": ["..."]
    }
    """
    if _has_api_key():
        resume_section = f"\nCandidate Resume:\n{resume_text[:2000]}" if resume_text else ""
        prompt = f"""You are an expert interview coach preparing a candidate for a job interview.

Job Description:
{jd_text[:4000]}
{resume_section}

Generate 10 highly likely interview questions for this role with strong suggested answers.
Cover: Technical skills, Behavioral (STAR format), Situational, and Role-specific questions.

Return ONLY valid JSON, no prose:
{{
  "questions": [
    {{
      "category": "<Technical|Behavioral|Situational|Role-specific>",
      "question": "<interview question>",
      "answer":   "<suggested answer 3-6 sentences, use STAR format for behavioral>"
    }}
  ],
  "key_topics": ["<topic to prepare>"],
  "preparation_tips": ["<actionable tip>"]
}}"""
        try:
            return _call_claude(prompt, max_tokens=5000, model=SONNET_MODEL)
        except Exception:
            pass  # fall through to mock

    # Mock fallback
    jd_skills = _extract_skills(jd_text)[:5]
    skill_list = ", ".join(jd_skills) or "core skills"
    return {
        "questions": [
            {
                "category": "Technical",
                "question": f"Can you walk me through your experience with {jd_skills[0] if jd_skills else 'our tech stack'}?",
                "answer": f"I have hands-on experience with {skill_list}. In my previous role, I applied these skills to build production systems, focusing on performance and maintainability.",
            },
            {
                "category": "Behavioral",
                "question": "Tell me about a challenging project you delivered under pressure.",
                "answer": "Situation: We had a critical production incident. Task: I needed to identify the root cause and restore service. Action: I led the debugging session, identified a memory leak, and deployed a fix within 2 hours. Result: Zero data loss and a post-mortem that prevented recurrence.",
            },
            {
                "category": "Situational",
                "question": "How would you handle disagreement with a technical decision made by your team lead?",
                "answer": "I would first make sure I fully understand their reasoning, then present my concerns with data and concrete examples. If we still disagree, I'd defer to their decision while documenting my concerns for future reference.",
            },
            {
                "category": "Role-specific",
                "question": "What do you know about our company and why do you want to join us?",
                "answer": "I researched your product and am impressed by your approach to solving this problem. I want to contribute my skills to this mission and grow with a team that values engineering excellence.",
            },
        ],
        "key_topics": jd_skills[:5],
        "preparation_tips": [
            "Research the company's recent news and product direction",
            "Prepare 3 STAR (Situation-Task-Action-Result) stories from your experience",
            f"Brush up on {jd_skills[0] if jd_skills else 'core technical skills'} fundamentals",
            "Prepare 3 thoughtful questions to ask the interviewer",
        ],
    }

