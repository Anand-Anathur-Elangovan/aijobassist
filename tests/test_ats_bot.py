"""
Unit tests for the ATS form-fill bot modules.

Covers:
  - ats_fingerprint   (2 tests)
  - field_normalizer  (3 tests)
  - enriched FIELD_JS (2 tests — via mocked page.evaluate)
  - claude_filler     (3 tests)
  - fill_validator    (3 tests)
  - field_cache       (3 tests)

Run with:
  pip install pytest pytest-asyncio aiosqlite
  pytest tests/test_ats_bot.py -v
"""

import json
import os
import sys
import asyncio
import tempfile

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

# ---------------------------------------------------------------------------
# Make automation/ importable when running from the project root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from ats_fingerprint  import detect_ats, ATS_FILL_QUIRKS
from field_normalizer import normalize_field, is_eeo_field, EEO_FIELDS
import field_cache as fc


# ===========================================================================
# Module 1 — ats_fingerprint
# ===========================================================================

class TestAtsFingerprintModule:
    def test_url_detection_greenhouse(self):
        """Greenhouse boards URL should be detected via URL pattern."""
        result = detect_ats("https://boards.greenhouse.io/company/jobs/123456")
        assert result == "greenhouse"

    def test_url_detection_workday(self):
        """Workday URL should be detected correctly."""
        result = detect_ats("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/123")
        assert result == "workday"

    def test_html_fallback_lever(self):
        """Lever should be detected via HTML signals when URL is generic."""
        html = '<div class="lever-application"><form class="lever-jobs"></form></div>'
        result = detect_ats("https://jobs.example.com/apply", html)
        assert result == "lever"

    def test_html_fallback_oracle_cx(self):
        """Oracle CX should be detected via cx-select-pills class in HTML."""
        html = '<ul class="cx-select-pills-container"><li>...</li></ul>'
        result = detect_ats("https://careers.example.com/apply", html)
        assert result == "oracle_cx"

    def test_unknown_returns_unknown(self):
        """A URL with no matching patterns should return 'unknown'."""
        result = detect_ats("https://somerandomblog.com/careers")
        assert result == "unknown"

    def test_fill_quirks_keys_match_patterns(self):
        """Every ATS_FILL_QUIRKS key that isn't 'unknown' must appear in ATS_PATTERNS."""
        for key in ATS_FILL_QUIRKS:
            if key != "unknown":
                assert key in ATS_FILL_QUIRKS, f"{key} missing from ATS_FILL_QUIRKS"


# ===========================================================================
# Module 2 — field_normalizer
# ===========================================================================

class TestFieldNormalizerModule:
    def test_exact_canonical_match_first_name(self):
        assert normalize_field("First Name") == "first_name"

    def test_partial_label_match_email(self):
        """Label with surrounding text should still map to 'email'."""
        assert normalize_field("Your Email Address *") == "email"

    def test_name_attr_assists_matching(self):
        """Ambiguous visible label resolved by name attribute."""
        result = normalize_field("Primary Contact", "linkedin_url")
        assert result == "linkedin_url"

    def test_unknown_field_returns_unknown_prefix(self):
        result = normalize_field("Favourite Colour")
        assert result.startswith("unknown__")
        assert "favourite" in result or "colour" in result

    def test_eeo_fields_identified(self):
        for key in EEO_FIELDS:
            assert is_eeo_field(key) is True

    def test_non_eeo_field_returns_false(self):
        assert is_eeo_field("first_name") is False
        assert is_eeo_field("email") is False

    def test_normalize_eeo_gender(self):
        assert normalize_field("Gender Identity") == "gender"

    def test_normalize_veteran_status(self):
        assert normalize_field("Are you a Protected Veteran?") == "veteran_status"


# ===========================================================================
# Module 3 — enriched FIELD_JS (via mocked page.evaluate)
# ===========================================================================

class TestEnrichedFieldJs:
    @pytest.mark.asyncio
    async def test_section_heading_included_in_descriptor(self):
        """page.evaluate(FIELD_JS) result should include section_heading key."""
        from run_form_fill import ENRICHED_FIELD_JS

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "id": "first_name", "name": "first_name",
                "label": "First Name", "type": "text",
                "options": [], "required": True, "placeholder": "",
                "section_heading": "Personal Information",
                "sibling_context": "Last Name | Email",
            }
        ])
        result = await mock_page.evaluate(ENRICHED_FIELD_JS)
        assert len(result) == 1
        assert "section_heading" in result[0]
        assert result[0]["section_heading"] == "Personal Information"

    @pytest.mark.asyncio
    async def test_sibling_context_included_in_descriptor(self):
        """page.evaluate(FIELD_JS) result should include sibling_context key."""
        from run_form_fill import ENRICHED_FIELD_JS

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "id": "email", "name": "email",
                "label": "Email Address", "type": "email",
                "options": [], "required": True, "placeholder": "",
                "section_heading": "Contact Details",
                "sibling_context": "First Name | Last Name | Phone",
            }
        ])
        result = await mock_page.evaluate(ENRICHED_FIELD_JS)
        assert result[0]["sibling_context"] == "First Name | Last Name | Phone"

    @pytest.mark.asyncio
    async def test_field_js_is_valid_js_string(self):
        """ENRICHED_FIELD_JS must be a non-empty string starting with the IIFE pattern."""
        from run_form_fill import ENRICHED_FIELD_JS
        assert isinstance(ENRICHED_FIELD_JS, str)
        assert "() => {" in ENRICHED_FIELD_JS
        assert "return fields;" in ENRICHED_FIELD_JS


# ===========================================================================
# Module 4 — claude_filler
# ===========================================================================

class TestClaudeFillerModule:
    _fields = [
        {
            "id": "first_name", "name": "first_name",
            "label": "First Name", "type": "text",
            "options": [], "required": True, "placeholder": "",
            "canonical_key": "first_name", "is_eeo": False,
            "section_heading": "", "sibling_context": "",
        }
    ]
    _profile = {"first_name": "Anand", "last_name": "Kumar",
                "email": "anand@example.com"}

    @pytest.mark.asyncio
    async def test_successful_json_response_parsed(self):
        """A well-formed Claude response is correctly parsed to a dict."""
        from claude_filler import get_fill_answers

        payload = json.dumps({
            "first_name": {"answer": "Anand", "conf": 0.97, "reason": "from profile"}
        })
        mock_client = MagicMock()
        mock_msg    = MagicMock()
        mock_msg.content = [MagicMock(text=payload)]
        mock_client.messages.create.return_value = mock_msg

        result = await get_fill_answers(
            self._fields, self._profile, "greenhouse", "Apply", mock_client
        )
        assert result["first_name"]["answer"] == "Anand"
        assert result["first_name"]["conf"]   == 0.97

    @pytest.mark.asyncio
    async def test_bad_json_retries_and_returns_empty_on_second_failure(self):
        """Two consecutive bad JSON responses should yield an empty dict."""
        from claude_filler import get_fill_answers

        mock_client = MagicMock()
        mock_msg    = MagicMock()
        mock_msg.content = [MagicMock(text="not valid json {{{{")]
        mock_client.messages.create.return_value = mock_msg

        result = await get_fill_answers(
            self._fields, self._profile, "greenhouse", "Apply", mock_client
        )
        assert result == {}
        assert mock_client.messages.create.call_count == 2  # initial + retry

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped_before_parse(self):
        """Claude response wrapped in ```json ... ``` should still parse."""
        from claude_filler import get_fill_answers

        payload = (
            "```json\n"
            + json.dumps({"first_name": {"answer": "Anand", "conf": 0.95, "reason": "profile"}})
            + "\n```"
        )
        mock_client = MagicMock()
        mock_msg    = MagicMock()
        mock_msg.content = [MagicMock(text=payload)]
        mock_client.messages.create.return_value = mock_msg

        result = await get_fill_answers(
            self._fields, self._profile, "lever", "Apply", mock_client
        )
        assert result["first_name"]["answer"] == "Anand"

    @pytest.mark.asyncio
    async def test_empty_fields_returns_empty_dict(self):
        """No fields → no API call, returns {}."""
        from claude_filler import get_fill_answers

        mock_client = MagicMock()
        result = await get_fill_answers([], self._profile, "unknown", "", mock_client)
        assert result == {}
        mock_client.messages.create.assert_not_called()


# ===========================================================================
# Module 5 — fill_validator
# ===========================================================================

class TestFillValidatorModule:
    @pytest.mark.asyncio
    async def test_text_field_settles_correctly(self):
        """fill_and_verify returns settled=True when actual matches intended."""
        from fill_validator import fill_and_verify

        mock_page = AsyncMock()
        # _read_actual returns the answer we set
        mock_page.evaluate = AsyncMock(side_effect=[
            "Anand",   # _read_actual result
            None,      # _get_error_message result
        ])
        mock_page.wait_for_timeout = AsyncMock()

        async def mock_fill(page, field, answer):
            pass

        field  = {"id": "fn", "name": "fn", "type": "text", "options": []}
        result = await fill_and_verify(mock_page, field, "Anand", mock_fill)

        assert result["settled"]  is True
        assert result["intended"] == "Anand"
        assert result["actual"]   == "Anand"

    @pytest.mark.asyncio
    async def test_unsettled_triggers_retry_with_transformed_answer(self):
        """If the value does not settle, fill_and_verify retries with stripped answer."""
        from fill_validator import fill_and_verify

        fill_calls = []

        async def mock_fill(page, field, answer):
            fill_calls.append(answer)

        # First read returns wrong value (spaces), second read returns correct
        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=[
            "",          # actual after first fill → not settled
            None,        # error_msg after first fill
            "42",        # actual after retry → settled
        ])

        field  = {"id": "yrs", "name": "yrs", "type": "number", "options": []}
        result = await fill_and_verify(mock_page, field, " 42 ", mock_fill)

        assert result["settled"] is True
        assert "42" in fill_calls  # retry was called with stripped numeric

    @pytest.mark.asyncio
    async def test_fill_fn_exception_captured_in_error_msg(self):
        """An exception in fill_fn should be caught and reported in error_msg."""
        from fill_validator import fill_and_verify

        async def bad_fill(page, field, answer):
            raise RuntimeError("DOM error")

        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        field  = {"id": "x", "name": "x", "type": "text", "options": []}
        result = await fill_and_verify(mock_page, field, "hello", bad_fill)

        assert result["settled"]  is False
        assert "DOM error" in result["error_msg"]


# ===========================================================================
# Module 6 — field_cache
# ===========================================================================

@pytest.fixture
def tmp_db(tmp_path):
    """Provide a fresh temp SQLite path and reset in-memory counters."""
    db_file = str(tmp_path / "test_cache.db")
    fc.set_db_path(db_file)
    fc._lookup_counts.clear()
    fc._hit_counts.clear()
    yield db_file
    fc._lookup_counts.clear()
    fc._hit_counts.clear()


class TestFieldCacheModule:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, tmp_db):
        """A fresh cache should return None for any key."""
        result = await fc.get_cached_answer("greenhouse", "first_name")
        assert result is None

    @pytest.mark.asyncio
    async def test_record_success_and_cache_hit_after_threshold(self, tmp_db):
        """After _TRUST_THRESHOLD successful records, cached answer is returned."""
        for _ in range(fc._TRUST_THRESHOLD):
            await fc.record_success(
                "greenhouse", "first_name", "First Name", "text", "Anand"
            )
        result = await fc.get_cached_answer("greenhouse", "first_name")
        assert result == "Anand"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self, tmp_db):
        """Fewer than _TRUST_THRESHOLD records should not yield a cache hit."""
        for _ in range(fc._TRUST_THRESHOLD - 1):
            await fc.record_success(
                "lever", "email", "Email", "email", "a@b.com"
            )
        result = await fc.get_cached_answer("lever", "email")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_resets_to_miss(self, tmp_db):
        """Invalidating a trusted entry should make it return None again."""
        for _ in range(fc._TRUST_THRESHOLD):
            await fc.record_success(
                "workday", "phone", "Phone Number", "tel", "9876543210"
            )
        assert await fc.get_cached_answer("workday", "phone") == "9876543210"

        await fc.invalidate("workday", "phone")
        # success_count reset to 0 → below threshold
        assert await fc.get_cached_answer("workday", "phone") is None

    @pytest.mark.asyncio
    async def test_cache_hit_rate_calculation(self, tmp_db):
        """Hit rate should equal hits / total lookups."""
        # 3 lookups: 1 miss, then fill to threshold, 2 hits
        await fc.get_cached_answer("greenhouse", "city")  # miss
        for _ in range(fc._TRUST_THRESHOLD):
            await fc.record_success("greenhouse", "city", "City", "text", "Chennai")
        await fc.get_cached_answer("greenhouse", "city")  # hit
        await fc.get_cached_answer("greenhouse", "city")  # hit

        rate = await fc.cache_hit_rate("greenhouse")
        # 3 lookups total (1 miss before fill + 2 hits); 2 hits
        assert rate == pytest.approx(2 / 3, rel=1e-3)
