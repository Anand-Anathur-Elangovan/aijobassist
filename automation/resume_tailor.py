"""
automation/resume_tailor.py — AI-Powered Resume Tailoring Engine

Full pipeline:
  1. PDF / DOCX / TXT  →  plain text   (via pdfplumber / python-docx)
  2. Match score BEFORE tailoring       (keyword overlap)
  3. Claude Sonnet tailors with JD      (real AI via ANTHROPIC_API_KEY)
  4. Match score AFTER tailoring
  5. Tailored text  →  PDF             (via reportlab)

Public API:
  tailor_resume_for_job(resume_path, jd_text, custom_prompt="", user_prefs={})
    → TailorResult dict

  calculate_match(resume_text, jd_text) → float (0–100)

  text_to_pdf(text, output_path) → output_path

  pdf_to_text(pdf_path) → str
"""

from __future__ import annotations
import os
import json
import re
import time
import tempfile
from dataclasses import dataclass, field, asdict


DEFAULT_ANTHROPIC_API_KEY = ""  # Set ANTHROPIC_API_KEY in your environment / .env file


def _get_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "").strip() or DEFAULT_ANTHROPIC_API_KEY


# ──────────────────────────────────────────────────────────────────────────
# Shared skill list (mirrors ai_client.py)
# ──────────────────────────────────────────────────────────────────────────
_ALL_SKILLS = [
    "python","javascript","typescript","java","c++","c#","golang","rust",
    "kotlin","swift","ruby","php","scala","bash","sql","html","css",
    "react","vue","angular","nextjs","svelte","tailwind","webpack","vite",
    "redux","graphql","rest","rest api","microservices","serverless",
    "node","nodejs","express","fastapi","django","flask","spring",
    "nestjs","grpc","postgresql","mysql","mongodb","redis","elasticsearch",
    "sqlite","supabase","firebase","dynamodb","aws","gcp","azure",
    "docker","kubernetes","terraform","ci/cd","github actions","jenkins",
    "machine learning","deep learning","tensorflow","pytorch","scikit-learn",
    "pandas","numpy","nlp","llm","openai","langchain",
    "react native","flutter","ios","android",
    "jest","pytest","cypress","selenium","playwright","unit testing","tdd",
    "git","github","jira","agile","scrum","figma","kafka","rabbitmq",
    "leadership","mentoring","system design","architecture","ownership",
]


# ──────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class TailorResult:
    original_text:   str
    tailored_text:   str
    tailored_bullets: list[str]     = field(default_factory=list)
    tailored_summary: str           = ""
    improvements:    list[str]      = field(default_factory=list)
    missing_skills:  list[str]      = field(default_factory=list)
    added_keywords:  list[str]      = field(default_factory=list)
    score_before:    float          = 0.0
    score_after:     float          = 0.0
    ats_score:       int            = 0
    tailored_pdf_path: str          = ""  # temp PDF path — caller must delete
    version_name:    str            = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────
# PDF / DOCX → text
# ──────────────────────────────────────────────────────────────────────────
def pdf_to_text(pdf_path: str) -> str:
    """Extract plain text from a PDF file."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip()
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
    except ImportError:
        pass
    raise RuntimeError("Install pdfplumber:  pip install pdfplumber")


def docx_to_text(docx_path: str) -> str:
    """Extract plain text from a DOCX file."""
    try:
        from docx import Document
        doc = Document(docx_path)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except ImportError:
        raise RuntimeError("Install python-docx:  pip install python-docx")


def file_to_text(file_path: str) -> str:
    """Auto-detect format and extract text."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return pdf_to_text(file_path)
    elif ext in (".docx", ".doc"):
        return docx_to_text(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()


# ──────────────────────────────────────────────────────────────────────────
# Match scoring (pure keyword overlap — used for before/after comparison)
# ──────────────────────────────────────────────────────────────────────────
def calculate_match(resume_text: str, jd_text: str) -> float:
    """
    Fast keyword-overlap score (0–100).
    Used to show before/after %. Claude gives a more accurate ATS score.
    """
    jd_lower     = jd_text.lower()
    resume_lower = resume_text.lower()
    jd_skills    = [s for s in _ALL_SKILLS if s in jd_lower]
    if not jd_skills:
        return 55.0
    matched = sum(1 for s in jd_skills if s in resume_lower)
    raw = (matched / len(jd_skills)) * 100
    return round(min(98, max(25, raw * 0.82 + 12)), 1)


def _extract_jd_keywords(jd_text: str) -> list[str]:
    jd_lower = jd_text.lower()
    return [s for s in _ALL_SKILLS if s in jd_lower]


# ──────────────────────────────────────────────────────────────────────────
# Claude Sonnet — real AI tailoring
# ──────────────────────────────────────────────────────────────────────────
def _call_claude(prompt: str, max_tokens: int = 4096) -> str:
    """
    Call Claude Sonnet API (resume tailoring always uses Sonnet for accuracy).
    Requires:
      pip install anthropic
      ANTHROPIC_API_KEY environment variable
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Add it to your .env or environment variables."
        )
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "Anthropic SDK not installed.\n"
            "Run:  pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _tailor_with_claude(
    resume_text: str,
    jd_text: str,
    custom_prompt: str = "",
) -> dict:
    """
    Send resume + JD to Claude Sonnet and get tailored version back as JSON.
    Returns dict with keys:
      tailored_text, tailored_bullets, tailored_summary,
      ats_score, improvements, added_keywords, missing_skills
    """
    extra = f"\n\nExtra user instruction: {custom_prompt}" if custom_prompt.strip() else ""

    prompt = f"""You are an expert ATS resume optimizer and career coach.

TASK: Rewrite the candidate's resume to maximise match with the job description.

RULES:
- Keep ALL real experience — do NOT invent companies, roles, or projects
- Naturally inject JD keywords into existing bullet points
- Rewrite weak bullets with strong action verbs + quantified impact
- Add a 2-3 sentence professional summary at the top aligned with the JD
- Preserve overall structure: Summary, Experience, Skills, Education
- Output must be ATS-friendly plain text (no tables, no columns)
- Keep original employment dates and company names exactly
{extra}

JOB DESCRIPTION:
{jd_text}

CANDIDATE'S CURRENT RESUME:
{resume_text}

Return ONLY valid JSON (no markdown, no extra text) with these exact keys:
{{
  "tailored_text": "<full rewritten resume as plain text>",
  "tailored_summary": "<2-3 sentence summary paragraph>",
  "tailored_bullets": ["<bullet 1>", "<bullet 2>", ...],
  "ats_score": <integer 0-100 estimated ATS match after tailoring>,
  "improvements": ["<what was improved>", ...],
  "added_keywords": ["<keyword injected>", ...],
  "missing_skills": ["<skill in JD but not in resume>", ...]
}}"""

    raw = _call_claude(prompt, max_tokens=4096)

    # Strip any accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: return the raw text wrapped in the expected shape
        return {
            "tailored_text":    raw,
            "tailored_summary": "",
            "tailored_bullets": [],
            "ats_score":        70,
            "improvements":     [],
            "added_keywords":   [],
            "missing_skills":   [],
        }


# ──────────────────────────────────────────────────────────────────────────
# Mock tailoring (used when no API key is set)
# ──────────────────────────────────────────────────────────────────────────
def _tailor_mock(resume_text: str, jd_text: str) -> dict:
    """Keyword-injection mock — used when ANTHROPIC_API_KEY is not set."""
    from automation.ai_client import tailor_resume as _ai_tailor
    result = _ai_tailor(resume_text, jd_text)
    return {
        "tailored_text":     result.get("tailored_text", resume_text),
        "tailored_summary":  result.get("tailored_summary", ""),
        "tailored_bullets":  result.get("tailored_bullets", []),
        "ats_score":         result.get("ats_score", 70),
        "improvements":      result.get("improvements", []),
        "added_keywords":    _extract_jd_keywords(jd_text)[:8],
        "missing_skills":    result.get("missing_skills", []),
    }


# ──────────────────────────────────────────────────────────────────────────
# Text → PDF using reportlab
# ──────────────────────────────────────────────────────────────────────────
def text_to_pdf(text: str, output_path: str | None = None) -> str:
    """
    Convert plain text to a clean, ATS-friendly PDF.
    Returns the path to the generated PDF.
    Requires:  pip install reportlab
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="tailored_resume_")
        os.close(fd)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_LEFT

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )

        styles = getSampleStyleSheet()
        normal_style = ParagraphStyle(
            "ResumeNormal",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1a1a1a"),
        )
        heading_style = ParagraphStyle(
            "ResumeHeading",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            spaceBefore=8,
            spaceAfter=2,
            textColor=colors.HexColor("#0a0e1a"),
            fontName="Helvetica-Bold",
        )
        name_style = ParagraphStyle(
            "ResumeName",
            parent=styles["Title"],
            fontSize=16,
            leading=20,
            spaceBefore=0,
            spaceAfter=4,
            textColor=colors.HexColor("#0a0e1a"),
            fontName="Helvetica-Bold",
        )
        bullet_style = ParagraphStyle(
            "ResumeBullet",
            parent=normal_style,
            leftIndent=12,
            firstLineIndent=-12,
            bulletIndent=0,
            spaceAfter=2,
        )

        _SECTION_HEADERS = {
            "experience", "work experience", "professional experience",
            "education", "skills", "technical skills", "projects",
            "certifications", "summary", "professional summary",
            "objective", "achievements", "publications", "awards",
        }

        story = []
        lines = text.split("\n")
        first_line = True

        for line in lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 3))
                continue

            line_lower = stripped.lower().rstrip(":").strip()

            if first_line:
                # First non-empty line = candidate name
                story.append(Paragraph(stripped.replace("&", "&amp;"), name_style))
                first_line = False
            elif line_lower in _SECTION_HEADERS or (
                len(stripped) < 50
                and stripped.isupper()
                and not stripped.startswith("•")
            ):
                story.append(Paragraph(stripped.replace("&", "&amp;"), heading_style))
            elif stripped.startswith(("•", "-", "–", "*", "▪")):
                bullet_text = re.sub(r"^[•\-–*▪]\s*", "", stripped)
                story.append(
                    Paragraph(
                        f"• {bullet_text.replace('&', '&amp;')}",
                        bullet_style,
                    )
                )
            else:
                story.append(Paragraph(stripped.replace("&", "&amp;"), normal_style))

        doc.build(story)
        return output_path

    except ImportError:
        # Fallback: write raw text file if reportlab not installed
        txt_path = output_path.replace(".pdf", ".txt")
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(
            "  [TAILOR] reportlab not installed — saved as .txt\n"
            "  Run:  pip install reportlab"
        )
        return txt_path


# ──────────────────────────────────────────────────────────────────────────
# Main public function
# ──────────────────────────────────────────────────────────────────────────
def tailor_resume_for_job(
    resume_source: str,          # path to PDF/DOCX/TXT  OR  raw text string
    jd_text: str,
    custom_prompt: str = "",
    company: str = "",
    role: str = "",
    save_pdf: bool = True,
) -> TailorResult:
    """
    Full tailor pipeline:
      1. Extract text from resume (if path given) or use directly
      2. Score BEFORE
      3. Tailor with Claude Sonnet (or mock if no API key)
      4. Score AFTER
      5. Generate tailored PDF
      6. Return TailorResult

    Args:
        resume_source: file path to PDF/DOCX/TXT OR raw resume text string
        jd_text:       full job description text
        custom_prompt: optional extra instruction for Claude
        company:       company name (used for version_name)
        role:          job title (used for version_name)
        save_pdf:      if True, generate a tailored PDF in temp dir

    Returns:
        TailorResult dataclass
    """
    # ── 1. Get original text ──────────────────────────────────
    if os.path.isfile(resume_source):
        original_text = file_to_text(resume_source)
        print(f"  [TAILOR] Extracted {len(original_text)} chars from {resume_source}")
    else:
        original_text = resume_source  # already plain text

    if not original_text.strip():
        raise ValueError("Resume is empty — cannot tailor")

    # ── 2. Score before ───────────────────────────────────────
    score_before = calculate_match(original_text, jd_text)
    print(f"  [TAILOR] Match BEFORE: {score_before:.0f}%")

    # ── 3. Tailor ─────────────────────────────────────────────
    has_api_key = bool(_get_api_key())
    if has_api_key:
        print("  [TAILOR] Using Claude Sonnet (claude-sonnet-4-5) ...")
        ai_result = _tailor_with_claude(original_text, jd_text, custom_prompt)
    else:
        print("  [TAILOR] No ANTHROPIC_API_KEY found — using mock tailor")
        ai_result = _tailor_mock(original_text, jd_text)

    tailored_text = ai_result.get("tailored_text", original_text)

    # ── 4. Score after ────────────────────────────────────────
    score_after = calculate_match(tailored_text, jd_text)
    print(f"  [TAILOR] Match AFTER:  {score_after:.0f}%  (ATS: {ai_result.get('ats_score', 0)})")

    # ── 5. Generate PDF ───────────────────────────────────────
    pdf_path = ""
    if save_pdf:
        pdf_path = text_to_pdf(tailored_text)
        print(f"  [TAILOR] PDF saved: {pdf_path}")

    # ── 6. Build version name ─────────────────────────────────
    from datetime import datetime
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M")
    company_slug = re.sub(r"[^a-zA-Z0-9]", "_", company or "Company")[:20]
    role_slug    = re.sub(r"[^a-zA-Z0-9]", "_", role    or "Role")[:20]
    version_name = f"{company_slug}_{role_slug}_{timestamp}"

    return TailorResult(
        original_text    = original_text,
        tailored_text    = tailored_text,
        tailored_bullets = ai_result.get("tailored_bullets", []),
        tailored_summary = ai_result.get("tailored_summary", ""),
        improvements     = ai_result.get("improvements", []),
        missing_skills   = ai_result.get("missing_skills", []),
        added_keywords   = ai_result.get("added_keywords", []),
        score_before     = score_before,
        score_after      = score_after,
        ats_score        = int(ai_result.get("ats_score", score_after)),
        tailored_pdf_path= pdf_path,
        version_name     = version_name,
    )
