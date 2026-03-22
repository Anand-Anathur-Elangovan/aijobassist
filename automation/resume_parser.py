"""
automation/resume_parser.py — Resume text extraction

Supports: PDF, DOCX, TXT
Requires:  pdfplumber   (pip install pdfplumber)
           python-docx  (pip install python-docx)
           Both are optional — parser degrades gracefully if not installed.
"""

import os
import re


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────

def extract_text(file_path: str) -> str:
    """
    Dispatch to the correct parser based on file extension.
    Returns the extracted plain text (may be empty string on failure).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _parse_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _parse_docx(file_path)
    elif ext in (".txt", ".md", ".rtf"):
        return _parse_text(file_path)
    else:
        print(f"  [PARSER] Unsupported extension: {ext}")
        return ""


def extract_structure(file_path: str) -> dict:
    """
    Extract text AND attempt basic structure detection.
    Returns:
        {
          raw_text:   str,
          skills:     list[str],
          email:      str | None,
          phone:      str | None,
          word_count: int,
        }
    """
    text   = extract_text(file_path)
    return _structure_from_text(text)


def extract_structure_from_string(text: str) -> dict:
    """Same as extract_structure but accepts a pre-extracted string."""
    return _structure_from_text(text)


# ──────────────────────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────────────────────

def _parse_pdf(path: str) -> str:
    try:
        import pdfplumber
        text_parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts)
        print(f"  [PARSER] PDF parsed — {len(text)} chars, {len(text.split())} words")
        return text
    except ImportError:
        print("  [PARSER] pdfplumber not installed, trying PyPDF2…")
        return _parse_pdf_pypdf2(path)
    except Exception as e:
        print(f"  [PARSER] PDF parse error: {e}")
        return ""


def _parse_pdf_pypdf2(path: str) -> str:
    try:
        import PyPDF2
        text_parts: list[str] = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)
    except ImportError:
        print("  [PARSER] PyPDF2 not installed either. Install: pip install pdfplumber")
        return ""
    except Exception as e:
        print(f"  [PARSER] PyPDF2 parse error: {e}")
        return ""


def _parse_docx(path: str) -> str:
    try:
        from docx import Document
        doc   = Document(path)
        lines = [para.text for para in doc.paragraphs if para.text.strip()]
        text  = "\n".join(lines)
        print(f"  [PARSER] DOCX parsed — {len(text)} chars, {len(text.split())} words")
        return text
    except ImportError:
        print("  [PARSER] python-docx not installed. Install: pip install python-docx")
        return ""
    except Exception as e:
        print(f"  [PARSER] DOCX parse error: {e}")
        return ""


def _parse_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        print(f"  [PARSER] TXT parsed — {len(text)} chars")
        return text
    except Exception as e:
        print(f"  [PARSER] TXT parse error: {e}")
        return ""


# ──────────────────────────────────────────────────────────────────────────
# Structure extraction
# ──────────────────────────────────────────────────────────────────────────

_COMMON_SKILLS = [
    "python","javascript","typescript","java","c++","c#","golang","rust",
    "kotlin","swift","ruby","php","scala","r","bash","sql","html","css",
    "react","vue","angular","nextjs","svelte","tailwind","webpack","vite",
    "redux","graphql","rest","node","nodejs","express","fastapi","django",
    "flask","spring","rails","grpc","microservices","docker","kubernetes",
    "aws","gcp","azure","terraform","ansible","linux","nginx","git","github",
    "postgresql","mysql","mongodb","redis","elasticsearch","firebase",
    "machine learning","deep learning","tensorflow","pytorch","scikit-learn",
    "pandas","numpy","nlp","openai","langchain","react native","flutter",
    "jest","pytest","cypress","selenium","playwright","jira","agile","scrum",
    "figma","kafka","rabbitmq","celery","airflow",
]


def _structure_from_text(text: str) -> dict:
    lower  = text.lower()
    skills = [s for s in _COMMON_SKILLS if s in lower]

    email = None
    m = re.search(r"[\w.+\-]+@[\w\-]+\.\w{2,}", text)
    if m:
        email = m.group()

    phone = None
    m = re.search(r"(?:\+?\d{1,3}[\s\-]?)?\(?\d{3,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5}", text)
    if m:
        phone = m.group().strip()

    return {
        "raw_text":   text,
        "skills":     skills,
        "email":      email,
        "phone":      phone,
        "word_count": len(text.split()),
    }
