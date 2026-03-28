"""
ATS platform detection module.

Identifies the ATS (Applicant Tracking System) platform from a page URL
and/or an HTML snippet.  Returns a normalised platform name used to look
up platform-specific fill quirks via ``ATS_FILL_QUIRKS``.
"""

import re

from loguru import logger

# ---------------------------------------------------------------------------
# URL-based patterns (checked first — most reliable)
# ---------------------------------------------------------------------------
ATS_PATTERNS: dict[str, list[str]] = {
    "greenhouse":      [r"boards\.greenhouse\.io", r"greenhouse\.io/embed",
                        r"grnh\.se"],
    "lever":           [r"jobs\.lever\.co", r"lever\.co/"],
    "workday":         [r"myworkdayjobs\.com", r"wd\d+\.myworkdayjobs\.com",
                        r"workday\.com.*recruiting"],
    "icims":           [r"\.icims\.com", r"careers\.icims\.com"],
    "taleo":           [r"taleo\.net", r"tbe\.taleo\.net",
                        r"oracle\.taleo\.net"],
    "oracle_cx":       [r"fa\.oraclecloud\.com",
                        r"oraclecloud\.com/hcmUI/CandidateExperience"],
    "smartrecruiters": [r"smartrecruiters\.com",
                        r"jobs\.smartrecruiters\.com"],
    "ashby":           [r"jobs\.ashbyhq\.com", r"ashbyhq\.com"],
    "rippling":        [r"app\.rippling\.com/hiring", r"ats\.rippling\.com"],
    "jobvite":         [r"jobs\.jobvite\.com", r"jobvite\.com"],
    "bamboohr":        [r"\.bamboohr\.com/careers", r"bamboohr\.com/jobs"],
}

# ---------------------------------------------------------------------------
# HTML class/attribute signals (fallback when URL does not match)
# Higher matched-signal count wins.
# ---------------------------------------------------------------------------
ATS_HTML_SIGNALS: dict[str, list[str]] = {
    "greenhouse":      ["data-greenhouse", "gh-btn", "application--form",
                        "greenhouse-form", "greenhouse_form"],
    "lever":           ["lever-", "lever-application", "lever-jobs",
                        "lever-job-posting"],
    "workday":         ["data-automation-id", "WDAY", "wd-popup", "gwt-",
                        "workday-"],
    "icims":           ["icims-", "iCIMS_", "icims_form", "icims_content"],
    "taleo":           ["input-row__hidden-control", "ftlApplicationForm",
                        "taleobuttonapply"],
    "oracle_cx":       ["cx-select-pills", "cx-select", "oracle-cx-",
                        "apply-flow", "oraclecloud"],
    "smartrecruiters": ["sr-apply", "SmartRecruiters", "smartrecruiters-",
                        "_srt_"],
    "ashby":           ["ashby-application", "_ashby_", "ashby-job",
                        "ashby-apply"],
    "rippling":        ["rippling-ats", "rippling-apply", "rippling-jobs"],
    "jobvite":         ["jvJobForm", "jobvite-", "jv-apply",
                        "JobviteWidget"],
    "bamboohr":        ["bamboohr-", "BambooHR", "bhr-apply",
                        "bamboohr_jobs"],
}

# ---------------------------------------------------------------------------
# Platform-specific fill quirks
# ---------------------------------------------------------------------------
ATS_FILL_QUIRKS: dict[str, dict] = {
    "greenhouse": {
        "phone_uses_iti":          True,
        "resume_field_id":         "resume",
        "cover_letter_field_id":   "cover_letter",
        "uses_react_inputs":       True,
    },
    "lever": {
        "phone_uses_iti":          False,
        "resume_field_name":       "resume",
        "uses_react_inputs":       True,
        "cover_letter_in_textarea": True,
    },
    "workday": {
        "uses_opaque_ids":             True,
        "combobox_needs_click_twice":  True,
        "date_format":                 "MM/DD/YYYY",
        "needs_slow_fill":             True,
        "uses_shadow_dom":             False,
    },
    "icims": {
        "uses_iframe":     True,
        "iframe_selector": "#icims_content_iframe",
        "phone_format":    "digits_only",
    },
    "taleo": {
        "hidden_legal_checkbox": True,
        "date_format":           "MM/DD/YYYY",
        "uses_oracle_select":    False,
    },
    "oracle_cx": {
        "uses_cx_select_pills":  True,
        "uses_combobox":         True,
        "hidden_legal_checkbox": True,
        "date_format":           "MM/DD/YYYY",
    },
    "smartrecruiters": {
        "phone_uses_iti":           True,
        "uses_react_inputs":        True,
        "custom_questions_section": True,
    },
    "ashby": {
        "phone_uses_iti":    False,
        "resume_required":   True,
        "uses_react_inputs": True,
    },
    "rippling": {
        "uses_react_inputs": True,
        "phone_uses_iti":    False,
    },
    "jobvite": {
        "uses_legacy_html_forms": True,
        "phone_format":           "formatted",
    },
    "bamboohr": {
        "phone_uses_iti":    False,
        "uses_react_inputs": True,
    },
    "unknown": {},
}


def detect_ats(page_url: str, page_html_snippet: str = "") -> str:
    """Detect the ATS platform from a page URL and optional HTML snippet.

    URL patterns are checked first (most reliable).  Falls back to counting
    HTML signal matches when no URL pattern fires.

    Args:
        page_url:          Full URL of the ATS application page.
        page_html_snippet: Optional beginning of the page's ``innerHTML``
                           (first ~8 KB is sufficient).

    Returns:
        Lowercase platform name, e.g. ``"greenhouse"``, or ``"unknown"``.
    """
    url_lower = page_url.lower()
    for platform, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower, re.IGNORECASE):
                logger.debug(f"ATS detected via URL: {platform} ({pattern!r})")
                return platform

    if page_html_snippet:
        scores: dict[str, int] = {}
        html_lower = page_html_snippet.lower()
        for platform, signals in ATS_HTML_SIGNALS.items():
            score = sum(1 for sig in signals if sig.lower() in html_lower)
            if score:
                scores[platform] = score
        if scores:
            best = max(scores, key=lambda k: scores[k])
            logger.debug(
                f"ATS detected via HTML signals: {best} "
                f"(score={scores[best]})"
            )
            return best

    logger.debug("ATS not detected, returning 'unknown'")
    return "unknown"
