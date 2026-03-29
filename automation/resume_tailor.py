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

    prompt = f"""You are helping a job applicant make targeted improvements to their resume so it better matches a specific job description.
Your goal is to produce changes that look like the applicant themselves spent 30-45 minutes carefully editing their own resume — NOT like AI rewrote it.

TASK: Make precise, minimal edits to the resume to improve its match with the job description.

RULES (read all carefully before writing anything):
1. NEVER invent facts. Keep ALL companies, job titles, project names, dates, and metrics EXACTLY as written.
2. ADD relevant keywords and phrases from the JD naturally into existing bullet points — weave them in, do not append lists.
3. Only REWRITE bullets that are genuinely weak (vague, passive, no impact). Leave strong bullets alone.
4. Strengthen improved bullets with a concrete action verb + quantified result WHERE the original already implies it.
5. Write a concise 2–3 sentence professional summary at the top of the resume, directly aligned with this JD.
6. Keep the SAME section order and section headings as the original resume. Do not add or remove sections.
7. Keep every date, company name, and job title 100% identical to the original.
8. Use the same bullet style as the original (•, -, ▪, etc.) — do not switch or mix.
9. Preserve the candidate's own writing voice and sentence rhythm. Avoid overly formal or corporate language that sounds robotic.
10. ATS-safe plain text only — no tables, columns, special characters, or markdown.
11. The final result must read as a polished, genuinely human-authored resume.
{extra}

JOB DESCRIPTION:
{jd_text}

CANDIDATE'S CURRENT RESUME:
{resume_text}

Return ONLY valid JSON (no markdown fences, no extra text) with these exact keys:
{{
  "tailored_text": "<full improved resume as plain text — preserve original structure>",
  "tailored_summary": "<2-3 sentence summary paragraph written for this specific JD>",
  "tailored_bullets": ["<only the bullets that were changed>"],
  "ats_score": <integer 0-100 estimated ATS match after tailoring>,
  "improvements": ["<brief description of each change made>"],
  "added_keywords": ["<each JD keyword that was injected>"],
  "missing_skills": ["<skills in the JD that are absent from the resume and could not be added honestly>"]
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
# PDF style detection — reads the source PDF to reproduce its visual look
# ──────────────────────────────────────────────────────────────────────────
def detect_pdf_style(pdf_path: str) -> dict:
    """
    Analyse an existing PDF resume and extract its visual style parameters.
    Returns a dict suitable for passing to text_to_pdf(source_style=...).
    Falls back to sensible defaults on any error.
    """
    style: dict = {
        "font_family":      "Helvetica",
        "name_font_size":   16.0,
        "heading_font_size": 12.0,
        "body_font_size":   10.0,
        "accent_hex":       "#0a0e1a",
        "body_hex":         "#1a1a1a",
        "left_margin_mm":   20.0,
        "right_margin_mm":  20.0,
        "top_margin_mm":    16.0,
        "bottom_margin_mm": 16.0,
        "use_section_rule": True,   # draw a light rule under section headers
    }
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return style
            page = pdf.pages[0]
            chars = page.chars
            if not chars:
                return style

            # ── Font sizes ───────────────────────────────────────────────
            size_counts: dict[float, int] = {}
            for ch in chars:
                sz = round(float(ch.get("size") or 10.0), 1)
                size_counts[sz] = size_counts.get(sz, 0) + 1

            all_sizes_desc = sorted(size_counts.keys(), reverse=True)
            body_sz = max(size_counts, key=size_counts.get)  # most-frequent = body text

            # Heading: next size tier above body
            heading_sz = next(
                (s for s in all_sizes_desc if s > body_sz + 0.5), body_sz + 2.0
            )
            # Name: next size tier above heading
            name_sz = next(
                (s for s in all_sizes_desc if s > heading_sz + 0.5), heading_sz + 4.0
            )

            style["body_font_size"]    = max(8.0, min(12.0, body_sz))
            style["heading_font_size"] = max(10.0, min(16.0, heading_sz))
            style["name_font_size"]    = max(14.0, min(26.0, name_sz))

            # ── Font family ──────────────────────────────────────────────
            font_names_raw: set[str] = {
                (ch.get("fontname") or "").lower() for ch in chars[:200]
            }
            font_str = " ".join(font_names_raw)
            if any(x in font_str for x in ("times", "georgia", "palatino", "garamond", "serif")):
                style["font_family"] = "Times-Roman"
            elif any(x in font_str for x in ("courier", "mono", "consolata", "inconsolata")):
                style["font_family"] = "Courier"
            else:
                style["font_family"] = "Helvetica"

            # ── Left margin ──────────────────────────────────────────────
            # 5th-percentile x0 of body-size characters is a reliable margin estimate
            body_xs = [
                float(ch["x0"])
                for ch in chars
                if ch.get("x0") is not None
                and round(float(ch.get("size") or 10.0), 1) <= body_sz + 1.0
            ]
            if body_xs:
                body_xs.sort()
                left_px = body_xs[max(0, int(len(body_xs) * 0.05))]
                detected_mm = round(left_px / 2.8346, 1)
                style["left_margin_mm"]  = max(10.0, min(30.0, detected_mm))
                style["right_margin_mm"] = style["left_margin_mm"]

            # ── Accent colour (dominant colour on large / bold text) ─────
            for ch in chars:
                sz = float(ch.get("size") or 0.0)
                if sz < style["heading_font_size"]:
                    continue
                color = ch.get("non_stroking_color") or ch.get("stroking_color")
                if color is None:
                    continue
                if isinstance(color, (list, tuple)) and len(color) == 3:
                    r, g, b = (float(c) for c in color)
                    # Skip near-black
                    if r + g + b < 0.1:
                        continue
                    style["accent_hex"] = (
                        f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
                    )
                    break
                elif isinstance(color, (int, float)):
                    gv = float(color)
                    if 0.05 < gv < 0.95:   # not pure black / pure white
                        gi = int(gv * 255)
                        style["accent_hex"] = f"#{gi:02x}{gi:02x}{gi:02x}"
                        break

            # ── Detect section rules (horizontal lines) ──────────────────
            # pdfplumber exposes page.lines; a full-width line = section divider
            try:
                page_w = page.width
                h_lines = [
                    ln for ln in (page.lines or [])
                    if abs(ln.get("y0", 0) - ln.get("y1", 0)) < 2
                    and (ln.get("x1", 0) - ln.get("x0", 0)) > page_w * 0.4
                ]
                style["use_section_rule"] = len(h_lines) > 0
            except Exception:
                style["use_section_rule"] = True   # default: include rules

    except Exception as e:
        print(f"  [TAILOR] PDF style detection skipped ({e}) — using defaults")

    return style


# ──────────────────────────────────────────────────────────────────────────
# Text → PDF using reportlab (style-aware)
# ──────────────────────────────────────────────────────────────────────────
def text_to_pdf(
    text: str,
    output_path: str | None = None,
    source_style: dict | None = None,
) -> str:
    """
    Convert plain text to a clean, ATS-friendly PDF.
    Pass source_style (from detect_pdf_style) to reproduce the look of the
    original resume — same fonts, sizes, colours, and margins.
    Returns the path to the generated PDF.
    Requires:  pip install reportlab
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="tailored_resume_")
        os.close(fd)

    # ── Resolve style params (source overrides defaults) ─────────────────
    st = source_style or {}
    _font_base   = st.get("font_family", "Helvetica")
    _name_sz     = float(st.get("name_font_size",    16))
    _head_sz     = float(st.get("heading_font_size", 12))
    _body_sz     = float(st.get("body_font_size",    10))
    _accent_hex  = str(st.get("accent_hex",  "#0a0e1a"))
    _body_hex    = str(st.get("body_hex",    "#1a1a1a"))
    _left_mm     = float(st.get("left_margin_mm",    20))
    _right_mm    = float(st.get("right_margin_mm",   20))
    _top_mm      = float(st.get("top_margin_mm",     16))
    _bot_mm      = float(st.get("bottom_margin_mm",  16))
    _use_rule    = bool(st.get("use_section_rule",   True))

    # Map to reportlab-registered font names
    _BOLD_MAP = {
        "Helvetica":  "Helvetica-Bold",
        "Times-Roman": "Times-Bold",
        "Courier":    "Courier-Bold",
    }
    _ITALIC_MAP = {
        "Helvetica":  "Helvetica-Oblique",
        "Times-Roman": "Times-Italic",
        "Courier":    "Courier-Oblique",
    }
    _font_bold   = _BOLD_MAP.get(_font_base, "Helvetica-Bold")
    _font_italic = _ITALIC_MAP.get(_font_base, "Helvetica-Oblique")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_LEFT

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=_left_mm * mm,
            rightMargin=_right_mm * mm,
            topMargin=_top_mm * mm,
            bottomMargin=_bot_mm * mm,
        )

        styles = getSampleStyleSheet()
        normal_style = ParagraphStyle(
            "ResumeNormal",
            parent=styles["Normal"],
            fontName=_font_base,
            fontSize=_body_sz,
            leading=_body_sz * 1.4,
            alignment=TA_LEFT,
            textColor=colors.HexColor(_body_hex),
        )
        heading_style = ParagraphStyle(
            "ResumeHeading",
            parent=styles["Heading2"],
            fontName=_font_bold,
            fontSize=_head_sz,
            leading=_head_sz * 1.35,
            spaceBefore=6,
            spaceAfter=1,
            textColor=colors.HexColor(_accent_hex),
        )
        name_style = ParagraphStyle(
            "ResumeName",
            parent=styles["Title"],
            fontName=_font_bold,
            fontSize=_name_sz,
            leading=_name_sz * 1.25,
            spaceBefore=0,
            spaceAfter=3,
            textColor=colors.HexColor(_accent_hex),
        )
        contact_style = ParagraphStyle(
            "ResumeContact",
            parent=normal_style,
            fontName=_font_italic,
            fontSize=max(8.0, _body_sz - 1.0),
            leading=(_body_sz - 1.0) * 1.4,
            spaceAfter=4,
            textColor=colors.HexColor(_body_hex),
        )
        bullet_style = ParagraphStyle(
            "ResumeBullet",
            parent=normal_style,
            leftIndent=14,
            firstLineIndent=-14,
            spaceAfter=1,
        )

        _SECTION_HEADERS = {
            "experience", "work experience", "professional experience",
            "education", "skills", "technical skills", "projects",
            "certifications", "summary", "professional summary",
            "objective", "achievements", "publications", "awards",
            "languages", "interests", "volunteer", "references",
        }

        def _is_section_header(s: str) -> bool:
            sl = s.lower().rstrip(":").strip()
            if sl in _SECTION_HEADERS:
                return True
            # Short all-caps line with no bullet = section header
            if len(s) < 50 and s.isupper() and not s.startswith(("•", "-", "–", "*")):
                return True
            return False

        story = []
        lines = text.split("\n")
        first_line = True
        second_line = True   # second non-empty line = contact info

        for line in lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 2))
                continue

            # Escape XML special chars
            safe = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            if first_line:
                # First non-empty line = candidate name
                story.append(Paragraph(safe, name_style))
                first_line = False
            elif second_line and not _is_section_header(stripped):
                # Second non-empty line = contact / location info
                story.append(Paragraph(safe, contact_style))
                second_line = False
            elif _is_section_header(stripped):
                second_line = False  # past the header area
                story.append(Spacer(1, 4))
                story.append(Paragraph(safe, heading_style))
                if _use_rule:
                    story.append(
                        HRFlowable(
                            width="100%",
                            thickness=0.5,
                            color=colors.HexColor(_accent_hex),
                            spaceAfter=2,
                        )
                    )
            elif stripped.startswith(("•", "-", "–", "*", "▪", "·")):
                second_line = False
                bullet_text = re.sub(r"^[•\-–*▪·]\s*", "", stripped)
                safe_bullet = (
                    bullet_text.replace("&", "&amp;")
                               .replace("<", "&lt;")
                               .replace(">", "&gt;")
                )
                story.append(Paragraph(f"• {safe_bullet}", bullet_style))
            else:
                second_line = False
                story.append(Paragraph(safe, normal_style))

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
    source_pdf_path = resume_source if os.path.isfile(resume_source) else ""
    if source_pdf_path:
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
        # Detect source style for faithful reproduction of the original layout
        source_style: dict | None = None
        if source_pdf_path and source_pdf_path.lower().endswith(".pdf"):
            try:
                source_style = detect_pdf_style(source_pdf_path)
                print(
                    f"  [TAILOR] Source style detected — "
                    f"font={source_style['font_family']}, "
                    f"sizes={source_style['name_font_size']:.0f}/"
                    f"{source_style['heading_font_size']:.0f}/"
                    f"{source_style['body_font_size']:.0f}, "
                    f"accent={source_style['accent_hex']}"
                )
            except Exception as _se:
                print(f"  [TAILOR] Style detection failed ({_se}) — using defaults")
        pdf_path = text_to_pdf(tailored_text, source_style=source_style)
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


def tailor_until_target(
    resume_source: str,
    jd_text: str,
    target_score: float = 90.0,
    custom_prompt: str = "",
    company: str = "",
    role: str = "",
    max_attempts: int = 3,
) -> "TailorResult":
    """
    Iteratively refine a resume until score_after >= target_score or max_attempts hit.
    Each round feeds the previous tailored text as input so quality improves progressively.
    PDF is generated only once for the final best result.
    Returns the TailorResult with the highest score_after.
    """
    max_attempts = max(1, max_attempts)
    best: TailorResult | None = None
    current_source = resume_source

    for attempt in range(max_attempts):
        result = tailor_resume_for_job(
            resume_source=current_source,
            jd_text=jd_text,
            custom_prompt=custom_prompt,
            company=company,
            role=role,
            save_pdf=False,   # no PDF during refinement — generate once at the end
        )
        print(f"  [TAILOR] Attempt {attempt + 1}/{max_attempts}: score {result.score_after:.0f}% (target {target_score:.0f}%)")
        if best is None or result.score_after > best.score_after:
            best = result

        if result.score_after >= target_score:
            break

        if attempt < max_attempts - 1:
            current_source = result.tailored_text   # refine from the latest output

    # Generate PDF for the winning result
    if best and not best.tailored_pdf_path:
        try:
            best.tailored_pdf_path = text_to_pdf(best.tailored_text)
        except Exception as _pe:
            print(f"  [TAILOR] PDF generation failed ({_pe})")

    return best  # type: ignore[return-value]
