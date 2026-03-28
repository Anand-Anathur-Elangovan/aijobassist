"""
Claude-powered intelligent form field filler.

Sends enriched + normalised field descriptors to the Claude API and returns
structured JSON answers with per-field confidence scores.  EEO fields are
always answered with a "decline to self-identify" response unless the
module-level ``FILL_EEO`` flag is explicitly set to ``True``.
"""

import json
import re
from typing import Optional

import anthropic
from loguru import logger

# ---------------------------------------------------------------------------
# Global config flag — set to True to allow Claude to fill EEO fields
# from the candidate profile instead of always declining.
# ---------------------------------------------------------------------------
FILL_EEO: bool = False

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a precise form-filling assistant for job applications.

STRICT RULES — follow every rule without exception:
1. Return ONLY a raw JSON object. No markdown, no code fences, no explanation.
2. Top-level keys = the "id" values from the input fields list, exactly as given.
3. Each value is an object with exactly three keys:
   {"answer": <str|null>, "conf": <float 0.0–1.0>, "reason": <string ≤10 words>}
4. Confidence thresholds:
   - conf >= 0.85  → fill confidently
   - conf 0.60–0.84 → fill, but this answer will be flagged for human review
   - conf < 0.60   → set answer to null (skip this field entirely)
5. For select / radio / combobox fields: answer MUST exactly match one of the
   provided options[] strings. If no option fits with conf >= 0.60, answer null.
6. For EEO fields (gender, ethnicity, veteran_status, disability):
   ALWAYS answer with the decline option — the string closest to
   "Decline to self-identify", "I don't wish to answer", or "Prefer not to say"
   from options[]. Set conf=1.0. Ignore all profile data for these fields.
7. NEVER invent data not present in the candidate profile.
8. Use section_heading and sibling_context clues to resolve ambiguous fields.
9. For boolean yes/no eligibility fields (work_auth, visa_sponsor, relocate):
   interpret profile values carefully; return null if ambiguous.
"""


async def get_fill_answers(
    fields: list[dict],
    profile: dict,
    ats_platform: str,
    page_title: str,
    client: anthropic.Anthropic,
) -> dict[str, dict]:
    """Send enriched field descriptors to Claude and retrieve fill answers.

    Args:
        fields:        List of enriched + normalised field dicts from FIELD_JS.
        profile:       Candidate profile dict (from dashboard ``task_input``).
        ats_platform:  Platform string from ``detect_ats()``, e.g. ``"greenhouse"``.
        page_title:    Browser page ``<title>`` (extra context for Claude).
        client:        Anthropic client instance.

    Returns:
        Dict mapping ``field_id`` →
        ``{"answer": str | None, "conf": float, "reason": str}``.
        Returns an empty dict on unrecoverable failure.
    """
    if not fields:
        return {}

    # Strip sensitive / bulky keys before shipping to Claude
    _STRIP = {
        "linkedin_password", "gmail_app_password", "agent_key",
        "employments", "educations", "projects",
    }
    safe_profile = {
        k: v for k, v in profile.items()
        if k not in _STRIP and v not in (None, "", [], {})
    }

    user_payload = json.dumps(
        {
            "ats_platform": ats_platform,
            "page_title":   page_title,
            "fields":       fields,
            "profile":      safe_profile,
        },
        ensure_ascii=False,
    )

    system = _SYSTEM_PROMPT
    for attempt in range(2):
        if attempt == 1:
            system = (
                _SYSTEM_PROMPT
                + "\n\nSTRICT RETRY: Your previous response was not valid JSON. "
                  "Return ONLY the JSON object, absolutely nothing else."
            )
        try:
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": user_payload}],
            )
            raw: str = response.content[0].text.strip()
            # Strip accidental markdown fences
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$",        "", raw)

            parsed: dict = json.loads(raw)
            logger.debug(
                f"Claude filled {len(parsed)} fields for "
                f"{ats_platform!r} (attempt {attempt + 1})"
            )
            return parsed

        except json.JSONDecodeError as exc:
            if attempt == 0:
                logger.warning(
                    f"Claude response JSON parse failed ({exc}) — retrying "
                    "with stricter prompt"
                )
                continue
            logger.error(
                f"Claude response JSON parse failed after retry: {exc}"
            )
            return {}

        except Exception as exc:
            logger.error(f"Claude API call failed: {exc}")
            return {}

    return {}
