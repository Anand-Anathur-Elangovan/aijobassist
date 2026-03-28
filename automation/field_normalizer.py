"""
Canonical field taxonomy and normalization for ATS form fields.

Maps raw label / name-attribute strings to canonical field keys so the
rest of the pipeline can reason about fields in a platform-agnostic way.
Includes an EEO field set for special decline-to-answer handling.
"""

import re
from typing import Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Canonical key → list of label/name substrings (case-insensitive match).
# More-specific variants are listed first to avoid false positives.
# ---------------------------------------------------------------------------
CANONICAL_MAP: dict[str, list[str]] = {
    # ── Personal ─────────────────────────────────────────────────────────
    "first_name":      ["first name", "given name", "fname",
                        "first_name", "firstname"],
    "last_name":       ["last name", "surname", "family name",
                        "lname", "last_name", "lastname"],
    "full_name":       ["full name", "your name", "candidate name",
                        "applicant name", "legal name"],
    "email":           ["email address", "e-mail", "email"],
    "phone":           ["phone number", "contact number", "phone",
                        "mobile", "telephone", "cell"],
    "address":         ["street address", "mailing address",
                        "home address", "address line"],
    "city":            ["current city", "city", "town", "municipality"],
    "state":           ["state/province", "state", "province", "region"],
    "zip_code":        ["zip code", "postal code", "post code",
                        "postcode", "zip"],
    "country":         ["country of residence", "country of citizenship",
                        "country"],

    # ── Professional ─────────────────────────────────────────────────────
    "linkedin_url":    ["linkedin url", "linkedin profile", "linkedin"],
    "portfolio_url":   ["portfolio url", "personal website",
                        "personal site", "portfolio", "website"],
    "github_url":      ["github url", "github profile", "github"],
    "twitter_url":     ["twitter url", "twitter handle",
                        "x.com", "twitter"],

    # ── Application ──────────────────────────────────────────────────────
    "resume_upload":   ["upload resume", "attach resume", "upload cv",
                        "curriculum vitae", "resume", "cv"],
    "cover_letter":    ["cover letter", "covering letter",
                        "letter of interest"],
    "salary_expect":   ["desired salary", "expected salary",
                        "salary expectation", "compensation", "salary"],
    "start_date":      ["available start", "earliest start",
                        "when can you start", "availability date",
                        "start date"],
    "hear_about":      ["how did you hear", "how did you find",
                        "where did you hear", "referral source",
                        "source"],
    "location":        ["preferred location", "work location",
                        "desired location", "office location"],
    "years_experience": ["years of experience", "years experience",
                         "how many years", "years relevant"],

    # ── Eligibility ──────────────────────────────────────────────────────
    "work_auth":       ["authorized to work", "work authorization",
                        "eligible to work", "right to work",
                        "legally authorized", "work permit",
                        "legally eligible"],
    "visa_sponsor":    ["require sponsorship", "visa sponsorship",
                        "sponsorship required", "need sponsorship",
                        "require visa"],
    "relocate":        ["willing to relocate", "open to relocation",
                        "able to relocate", "relocation"],
    "remote_ok":       ["work remotely", "willing to work remote",
                        "open to remote", "remote work", "remote"],

    # ── EEO ──────────────────────────────────────────────────────────────
    "gender":          ["gender identity", "gender", "sex"],
    "ethnicity":       ["race/ethnicity", "ethnicity", "racial",
                        "ethnic", "race"],
    "veteran_status":  ["protected veteran", "military status",
                        "veteran status", "veteran", "military"],
    "disability":      ["disability status", "disability",
                        "disabled", "accommodation"],
}

EEO_FIELDS: set[str] = {"gender", "ethnicity", "veteran_status", "disability"}


def normalize_field(raw_label: str, field_name_attr: str = "") -> str:
    """Map a raw form label (and optional ``name`` attribute) to a canonical key.

    Matching is case-insensitive substring against the combined
    ``"<label> <name_attr>"`` string.

    Args:
        raw_label:        Visible label text of the form field.
        field_name_attr:  The HTML ``name`` attribute value (optional).

    Returns:
        Canonical key (e.g. ``"first_name"``) or
        ``"unknown__<sanitized_label>"`` when no variant matches.
    """
    combined = f"{raw_label} {field_name_attr}".lower().strip()
    for canonical_key, variants in CANONICAL_MAP.items():
        for variant in variants:
            if variant.lower() in combined:
                logger.debug(f"normalize_field: {raw_label!r} → {canonical_key}")
                return canonical_key

    sanitized = re.sub(r"[^a-z0-9]+", "_", raw_label.lower()).strip("_")[:50]
    result = f"unknown__{sanitized}" if sanitized else "unknown__field"
    logger.debug(f"normalize_field: {raw_label!r} → {result} (no match)")
    return result


def is_eeo_field(canonical_key: str) -> bool:
    """Return ``True`` if the canonical key belongs to the EEO/diversity set."""
    return canonical_key in EEO_FIELDS
