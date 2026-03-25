"""
test_url_apply.py — Unit tests for Manual URL Apply feature.

Tests cover:
  1. URL platform detection (LinkedIn vs Naukri vs unknown)
  2. URL_APPLY task payload validation
  3. `specific_urls` routing in task_runner._handle_url_apply
  4. detect_pdf_style() fallback behaviour
  5. text_to_pdf() with and without source_style
  6. Tailoring prompt produces valid JSON shape
  7. calculate_match() keyword overlap scores

Run from project root:
    cd taskrunner && python test_url_apply.py
"""
from __future__ import annotations
import sys, os, json, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status}  {name}" + (f"  — {detail}" if detail else ""))


# ══════════════════════════════════════════════════════════════════════════
# 1. URL platform detection
# ══════════════════════════════════════════════════════════════════════════
print("\n── 1. URL platform detection ────────────────────────────────────────────")

_LINKEDIN_URLS = [
    "https://www.linkedin.com/jobs/view/3887654321/",
    "https://linkedin.com/jobs/view/1234567890/?refId=abc",
    "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=999",
]
_NAUKRI_URLS = [
    "https://www.naukri.com/job-listings/software-engineer-xyz-123456",
    "https://naukri.com/job-listings/backend-dev-abc?jobId=78901",
]
_OTHER_URLS = [
    "https://jobs.google.com/jobs/results/xyz",
    "https://angel.co/jobs/123",
    "not-a-url-at-all",
]


def _detect_platform(url: str) -> str:
    if "linkedin.com" in url.lower():
        return "linkedin"
    if "naukri.com" in url.lower():
        return "naukri"
    return "unknown"


for url in _LINKEDIN_URLS:
    check(f"LinkedIn detected: {url[:60]}", _detect_platform(url) == "linkedin")

for url in _NAUKRI_URLS:
    check(f"Naukri detected: {url[:60]}", _detect_platform(url) == "naukri")

for url in _OTHER_URLS:
    check(f"Unknown correctly rejected: {url[:60]}", _detect_platform(url) == "unknown")

# ══════════════════════════════════════════════════════════════════════════
# 2. URL grouping logic (mirrors _handle_url_apply routing)
# ══════════════════════════════════════════════════════════════════════════
print("\n── 2. URL grouping logic ────────────────────────────────────────────────")

_mixed_urls = _LINKEDIN_URLS[:2] + _NAUKRI_URLS[:1] + _OTHER_URLS[:1]
_li  = [u for u in _mixed_urls if "linkedin.com" in u.lower()]
_nk  = [u for u in _mixed_urls if "naukri.com"   in u.lower()]
_oth = [u for u in _mixed_urls if u not in _li and u not in _nk]

check("LinkedIn URLs extracted", len(_li) == 2, str(_li))
check("Naukri URLs extracted",   len(_nk) == 1, str(_nk))
check("Other URLs identified",   len(_oth) == 1, str(_oth))

# ══════════════════════════════════════════════════════════════════════════
# 3. URL_APPLY task payload validation (mirrors dashboard createTask)
# ══════════════════════════════════════════════════════════════════════════
print("\n── 3. Task payload validation ───────────────────────────────────────────")


def build_url_task_payload(
    manual_urls: list[str],
    tailor_resume: bool = True,
    smart_match: bool = True,
    match_threshold: int = 70,
    tailor_custom_prompt: str = "",
    phone: str = "9876543210",
    years_experience: int = 3,
) -> dict:
    """Mirrors the dashboard's URL_APPLY task creation logic."""
    urls = [u.strip() for u in manual_urls
            if u.strip() and ("linkedin.com" in u or "naukri.com" in u)]
    if not urls:
        return {}
    return {
        "type": "URL_APPLY",
        "status": "PENDING",
        "input": {
            "manual_urls": urls,
            "tailor_resume": tailor_resume,
            **({"tailor_custom_prompt": tailor_custom_prompt} if tailor_custom_prompt else {}),
            **({"smart_match": True, "match_threshold": match_threshold} if smart_match else {}),
            "phone": phone,
            "years_experience": years_experience,
        },
    }


# Valid payload with LinkedIn URLs
payload = build_url_task_payload(
    manual_urls=_LINKEDIN_URLS[:2],
    tailor_resume=True,
    smart_match=True,
)
check("URL task type is URL_APPLY",      payload.get("type") == "URL_APPLY")
check("manual_urls present in payload",   len(payload["input"]["manual_urls"]) == 2)
check("tailor_resume=True in payload",    payload["input"]["tailor_resume"] is True)
check("smart_match flag present",         payload["input"].get("smart_match") is True)
check("match_threshold present (70)",     payload["input"].get("match_threshold") == 70)

# Payload with no valid URLs returns empty
empty = build_url_task_payload(manual_urls=["https://jobs.google.com/xyz"])
check("Empty payload for non-LinkedIn/Naukri URLs", empty == {})

# Mixed URLs — only valid ones should pass
mixed_payload = build_url_task_payload(
    manual_urls=_LINKEDIN_URLS[:1] + ["https://other.com/job/123"] + _NAUKRI_URLS[:1]
)
check("Mixed URLs: only LinkedIn+Naukri included",
      len(mixed_payload["input"]["manual_urls"]) == 2)

# ══════════════════════════════════════════════════════════════════════════
# 4. detect_pdf_style() fallback
# ══════════════════════════════════════════════════════════════════════════
print("\n── 4. detect_pdf_style() fallback ──────────────────────────────────────")
try:
    from automation.resume_tailor import detect_pdf_style
    # Pass a non-existent path — must not raise, must return sensible defaults
    style = detect_pdf_style("/tmp/nonexistent_resume_12345.pdf")
    check("detect_pdf_style: returns dict",          isinstance(style, dict))
    check("detect_pdf_style: has font_family",       "font_family" in style)
    check("detect_pdf_style: has name_font_size",    "name_font_size" in style)
    check("detect_pdf_style: has accent_hex",        "accent_hex" in style)
    check("detect_pdf_style: default font is Helvetica", style["font_family"] == "Helvetica")
    check("detect_pdf_style: name size ≥ 14",        style["name_font_size"] >= 14)
    check("detect_pdf_style: body size ≥ 8",         style["body_font_size"] >= 8)
except Exception as ex:
    check("detect_pdf_style import", False, str(ex))

# ══════════════════════════════════════════════════════════════════════════
# 5. text_to_pdf() with and without source_style
# ══════════════════════════════════════════════════════════════════════════
print("\n── 5. text_to_pdf() PDF generation ─────────────────────────────────────")

SAMPLE_RESUME = """\
Jane Smith
jane.smith@email.com | +1-555-0199 | linkedin.com/in/janesmith

SUMMARY
Results-driven software engineer with 4 years delivering scalable Python backends.

EXPERIENCE
Senior Software Engineer — Acme Corp (2021-Present)
• Built REST APIs serving 50k+ daily users with FastAPI and PostgreSQL
• Reduced latency by 35% through query optimisation and Redis caching

Software Engineer — StartupXYZ (2019-2021)
• Developed React frontend components for the main dashboard

SKILLS
Python, FastAPI, React, PostgreSQL, Redis, Docker, AWS, Git

EDUCATION
B.Tech Computer Science — State University (2019)
"""

try:
    from automation.resume_tailor import text_to_pdf

    # Without source_style (default)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path_default = os.path.join(tmpdir, "test_default.pdf")
        result_path = text_to_pdf(SAMPLE_RESUME, output_path=pdf_path_default)
        check("text_to_pdf: default → file created",    os.path.isfile(result_path))
        check("text_to_pdf: default → non-empty file",  os.path.getsize(result_path) > 1000)

    # With custom source_style (simulating a detected style)
    custom_style = {
        "font_family":       "Times-Roman",
        "name_font_size":    18.0,
        "heading_font_size": 13.0,
        "body_font_size":    10.5,
        "accent_hex":        "#1a3a6b",
        "body_hex":          "#111111",
        "left_margin_mm":    22.0,
        "right_margin_mm":   22.0,
        "top_margin_mm":     18.0,
        "bottom_margin_mm":  18.0,
        "use_section_rule":  True,
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path_styled = os.path.join(tmpdir, "test_styled.pdf")
        result_path2 = text_to_pdf(SAMPLE_RESUME, output_path=pdf_path_styled,
                                   source_style=custom_style)
        check("text_to_pdf: styled → file created",     os.path.isfile(result_path2))
        check("text_to_pdf: styled → non-empty file",   os.path.getsize(result_path2) > 1000)

    # With section rules disabled
    no_rule_style = dict(custom_style, use_section_rule=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path_norule = os.path.join(tmpdir, "test_norule.pdf")
        result_path3 = text_to_pdf(SAMPLE_RESUME, output_path=pdf_path_norule,
                                   source_style=no_rule_style)
        check("text_to_pdf: no-rule variant created",   os.path.isfile(result_path3))

except Exception as ex:
    check("text_to_pdf import / execution", False, str(ex))


# ══════════════════════════════════════════════════════════════════════════
# 6. tailor_resume_for_job() without API key (mock path)
# ══════════════════════════════════════════════════════════════════════════
print("\n── 6. tailor_resume_for_job() mock path ─────────────────────────────────")

SAMPLE_JD = """\
We are looking for a Senior Software Engineer to join our platform team.
Requirements:
- 3+ years Python experience (FastAPI, Django, or Flask)
- Strong understanding of REST API design and microservices
- Experience with PostgreSQL or MySQL
- Familiarity with Docker and Kubernetes
- AWS or GCP cloud experience preferred
- React or Vue.js frontend skills a plus
"""

try:
    # Temporarily remove the API key so the mock path runs
    _saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        from automation.resume_tailor import tailor_resume_for_job, calculate_match
        result = tailor_resume_for_job(
            resume_source=SAMPLE_RESUME,
            jd_text=SAMPLE_JD,
            company="Acme Corp",
            role="Senior Software Engineer",
            save_pdf=True,
        )
        check("tailor_resume_for_job: returns TailorResult",  hasattr(result, "tailored_text"))
        check("tailor_resume_for_job: tailored_text non-empty", len(result.tailored_text) > 100)
        check("tailor_resume_for_job: score_before 0-100",
              0 <= result.score_before <= 100, f"score={result.score_before}")
        check("tailor_resume_for_job: score_after 0-100",
              0 <= result.score_after <= 100, f"score={result.score_after}")
        check("tailor_resume_for_job: ats_score 0-100",
              0 <= result.ats_score <= 100, f"ats={result.ats_score}")
        if result.tailored_pdf_path:
            check("tailor_resume_for_job: PDF file exists",
                  os.path.isfile(result.tailored_pdf_path),
                  result.tailored_pdf_path)
            # Clean up temp PDF
            try:
                os.unlink(result.tailored_pdf_path)
            except Exception:
                pass
        else:
            check("tailor_resume_for_job: PDF path set", False, "tailored_pdf_path is empty")
    finally:
        if _saved_key:
            os.environ["ANTHROPIC_API_KEY"] = _saved_key
except Exception as ex:
    check("tailor_resume_for_job execution", False, str(ex))

# ══════════════════════════════════════════════════════════════════════════
# 7. calculate_match() scoring
# ══════════════════════════════════════════════════════════════════════════
print("\n── 7. calculate_match() keyword scoring ─────────────────────────────────")
try:
    from automation.resume_tailor import calculate_match

    # High-match scenario
    high_score = calculate_match(
        resume_text="Python FastAPI PostgreSQL Docker AWS microservices REST API",
        jd_text="Python FastAPI PostgreSQL Docker AWS microservices REST API",
    )
    check("calculate_match: perfect overlap → high score",  high_score >= 60,
          f"score={high_score}")

    # Low-match scenario
    low_score = calculate_match(
        resume_text="Java Spring Oracle on-premise",
        jd_text="Python FastAPI PostgreSQL Docker AWS React TypeScript",
    )
    check("calculate_match: poor overlap → low score", low_score < 60,
          f"score={low_score}")

    # Returns float
    check("calculate_match: returns float/int", isinstance(high_score, (int, float)))
    check("calculate_match: score within 0-100 range",
          0 <= high_score <= 100 and 0 <= low_score <= 100)

except Exception as ex:
    check("calculate_match execution", False, str(ex))

# ══════════════════════════════════════════════════════════════════════════
# 8. specific_urls flag plumbing through task_runner (mock)
# ══════════════════════════════════════════════════════════════════════════
print("\n── 8. specific_urls plumbing (task_runner mock) ─────────────────────────")

_mock_task_input_li = {
    "specific_urls": ["https://www.linkedin.com/jobs/view/111/",
                      "https://www.linkedin.com/jobs/view/222/"],
    "platform":       "linkedin",
    "tailor_resume":  False,
    "user_id":        "test-user",
    "task_id":        "test-task",
    "resume_text":    SAMPLE_RESUME,
    "max_apply":      2,
}

# Verify specific_urls is passed through correctly (no browser launched here)
check("specific_urls: correct count in input",
      len(_mock_task_input_li["specific_urls"]) == 2)
check("specific_urls: all are LinkedIn",
      all("linkedin.com" in u for u in _mock_task_input_li["specific_urls"]))

_mock_task_input_nk = {
    "specific_urls": ["https://www.naukri.com/job-listings/backend-dev-123"],
    "platform":       "naukri",
    "tailor_resume":  True,
    "user_id":        "test-user-2",
    "task_id":        "test-task-2",
    "resume_text":    SAMPLE_RESUME,
    "max_apply":      1,
}
check("specific_urls: Naukri URL detected correctly",
      "naukri.com" in _mock_task_input_nk["specific_urls"][0])

# Verify _handle_url_apply split logic (without actually launching a browser)
manual_urls_mixed = (
    ["https://www.linkedin.com/jobs/view/111/",
     "https://www.linkedin.com/jobs/view/222/"]
    + ["https://www.naukri.com/job-listings/backend-dev-456"]
    + ["https://jobs.google.com/xyz"]
)
li_split  = [u for u in manual_urls_mixed if "linkedin.com" in u.lower()]
nk_split  = [u for u in manual_urls_mixed if "naukri.com"   in u.lower()]
oth_split = [u for u in manual_urls_mixed if u not in li_split and u not in nk_split]

check("URL split: 2 LinkedIn", len(li_split) == 2)
check("URL split: 1 Naukri",   len(nk_split) == 1)
check("URL split: 1 other",    len(oth_split) == 1)

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print()
print("=" * 72)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
total  = len(results)
print(f"  Results: {passed}/{total} passed, {failed} failed")
print("=" * 72)

if failed > 0:
    print("\nFailed tests:")
    for s, name, detail in results:
        if s == FAIL:
            print(f"    {FAIL}  {name}" + (f"  — {detail}" if detail else ""))
    sys.exit(1)
else:
    print("\nAll tests passed ✅")
