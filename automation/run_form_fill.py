"""
Main orchestration module for ATS form auto-fill.

Wires together:
  ATS detection → enriched FIELD_JS extraction → field normalisation →
  SQLite cache lookup → Claude inference → fill + validation →
  cache recording → summary report.
"""

from typing import Callable, Optional

import anthropic
from playwright.async_api import Page
from loguru import logger

from ats_fingerprint  import detect_ats
from field_normalizer import normalize_field, is_eeo_field
from claude_filler    import get_fill_answers
from fill_validator   import fill_and_verify
from field_cache      import get_cached_answer, record_success, invalidate

# ---------------------------------------------------------------------------
# Enriched FIELD_JS
#
# Adds two new properties to every field descriptor returned by the original
# FIELD_JS:
#
#   section_heading (str) — innerText of the nearest section/fieldset heading
#                           (h1–h4, legend, or [class*="heading/title"]).
#
#   sibling_context (str) — labels 2 before and 2 after this field's label
#                           in DOM order, joined with " | ".
#
# All existing properties are preserved:
#   id, name, label, type, options, required, placeholder
# ---------------------------------------------------------------------------
ENRICHED_FIELD_JS: str = """() => {
    const fields = [], seen = new Set();

    const isVisible = (el) => {
        if (!el || el.offsetParent === null) return false;
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const getLabel = (el) => {
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
        if (el.id) {
            const l = document.querySelector('label[for="' + el.id + '"]');
            if (l) return l.innerText.replace(/\\s+/g, ' ').trim();
        }
        const lid = el.getAttribute('aria-labelledby');
        if (lid) {
            const l = document.getElementById(lid);
            if (l) return l.innerText.replace(/\\s+/g, ' ').trim();
        }
        if (el.placeholder) return el.placeholder.trim();
        const p = el.parentElement;
        if (p) { const t = (p.innerText||'').replace(/\\s+/g,' ').trim(); if (t && t.length < 100) return t; }
        return '';
    };

    // Walk up the DOM. At the first section/fieldset/data-automation-id boundary,
    // look for the nearest h1–h4, legend, or heading-classed element within it.
    const getSectionHeading = (el) => {
        let ancestor = el.parentElement;
        while (ancestor && ancestor !== document.body) {
            const tag = ancestor.tagName.toLowerCase();
            const cls = (ancestor.className || '').toString().toLowerCase();
            const isSection =
                tag === 'section' || tag === 'fieldset' || tag === 'article'
                || ancestor.hasAttribute('data-automation-id')
                || /application-section|form-section|form-group|form-block/.test(cls);
            if (isSection) {
                for (const sel of ['h1','h2','h3','h4','legend']) {
                    const h = ancestor.querySelector(sel);
                    if (h) { const t = (h.innerText||'').trim(); if (t) return t.substring(0,80); }
                }
                for (const hEl of ancestor.querySelectorAll(
                        '[class*="heading"],[class*="title"],[class*="section-label"]')) {
                    const t = (hEl.innerText||'').trim();
                    if (t) return t.substring(0,80);
                }
                break;  // stop at first section boundary even if no heading found
            }
            ancestor = ancestor.parentElement;
        }
        return '';
    };

    // Return up to 2 labels before and 2 after this field's label in the
    // same form (or document if not in a <form>), joined with " | ".
    const getSiblingContext = (el) => {
        let fieldLabel = null;
        if (el.id) fieldLabel = document.querySelector('label[for="' + el.id + '"]');
        if (!fieldLabel) fieldLabel = el.closest('label');
        if (!fieldLabel && el.parentElement) fieldLabel = el.parentElement.querySelector('label');
        const container = el.closest('form') || document;
        const allLabels = Array.from(container.querySelectorAll('label'));
        if (!fieldLabel || allLabels.length === 0) return '';
        const idx = allLabels.indexOf(fieldLabel);
        if (idx === -1) return '';
        const neighbors = [];
        for (let i = Math.max(0, idx - 2); i < Math.min(allLabels.length, idx + 3); i++) {
            if (i !== idx) { const t = (allLabels[i].innerText||'').trim(); if (t) neighbors.push(t); }
        }
        return neighbors.join(' | ');
    };

    // ── Standard inputs / textarea / select ──────────────────────────────
    for (const el of document.querySelectorAll(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"])' +
        ':not([type="reset"]):not([type="image"]), textarea, select'
    )) {
        if (!isVisible(el)) continue;
        const key = el.id || el.name || (el.type + '_' + fields.length);
        if (seen.has(key)) continue; seen.add(key);
        const tag  = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const type = tag === 'select' ? 'select'
                   : tag === 'textarea' ? 'textarea'
                   : (role === 'combobox' ? 'combobox' : (el.type || 'text'));
        const opts = type === 'select'
            ? Array.from(el.options).filter(o => o.value !== '').map(o => o.text.trim())
            : [];
        fields.push({
            id: key, name: el.name||'', label: getLabel(el), type, options: opts,
            required: el.required || el.getAttribute('aria-required') === 'true',
            placeholder: el.placeholder||'',
            section_heading: getSectionHeading(el),
            sibling_context: getSiblingContext(el),
        });
    }

    // ── Radio / Checkbox groups ───────────────────────────────────────────
    const groups = {};
    for (const el of document.querySelectorAll('input[type="radio"], input[type="checkbox"]')) {
        if (!isVisible(el)) continue;
        const g = el.name || ('grp_' + el.id);
        if (!g) continue;
        if (!groups[g]) {
            groups[g] = {
                id: g, name: g, label: getLabel(el), type: el.type,
                options: [], required: el.required,
                section_heading: getSectionHeading(el),
                sibling_context: getSiblingContext(el),
            };
        }
        const optLbl = el.labels && el.labels[0]
            ? el.labels[0].innerText.trim()
            : (el.nextSibling && el.nextSibling.textContent
                ? el.nextSibling.textContent.trim() : el.value);
        groups[g].options.push(optLbl || el.value);
    }
    for (const g of Object.values(groups)) {
        if (!seen.has(g.id)) { seen.add(g.id); fields.push(g); }
    }

    // ── Oracle cx-select-pills ────────────────────────────────────────────
    for (const ul of document.querySelectorAll('ul.cx-select-pills-container')) {
        if (!isVisible(ul)) continue;
        const label = (ul.getAttribute('aria-label') || '').trim();
        if (!label) continue;
        const options = Array.from(ul.querySelectorAll('button .cx-select-pill-name'))
                            .map(s => s.textContent.trim()).filter(Boolean);
        const key = 'cxpill_' + label.replace(/\\W+/g, '_').substring(0, 40);
        if (!seen.has(key)) {
            seen.add(key);
            fields.push({
                id: key, name: key, label, type: 'cx_pills', options,
                required: true, placeholder: '',
                section_heading: getSectionHeading(ul),
                sibling_context: getSiblingContext(ul),
            });
        }
    }

    // ── Oracle hidden T&C / legal-disclaimer checkboxes ──────────────────
    for (const inp of document.querySelectorAll(
            'input[type="checkbox"].input-row__hidden-control')) {
        if (inp.checked) continue;
        const lbl = inp.id
            ? document.querySelector('label[for="' + inp.id + '"]')
            : inp.closest('label');
        const text = lbl
            ? (lbl.innerText||'').replace(/\\s+/g, ' ').trim().substring(0, 80)
            : (inp.id || 'legal_checkbox');
        const key = 'legalchk_' + (inp.id || inp.name || 'chk');
        if (!seen.has(key)) {
            seen.add(key);
            fields.push({
                id: inp.id||inp.name, name: inp.name||inp.id, label: text,
                type: 'legal_checkbox', options: [], required: true, placeholder: '',
                section_heading: getSectionHeading(inp), sibling_context: '',
            });
        }
    }

    // ── intl-tel-input phone country selector (Greenhouse, Lever, etc.) ──
    for (const btn of document.querySelectorAll('button.iti__selected-country')) {
        if (!isVisible(btn)) continue;
        const container = btn.closest('.iti');
        const phoneInp  = container
            ? container.querySelector(
                'input[type="tel"],input[name*="phone"],input[id*="phone"]')
            : null;
        const key = 'iti_phone_' + (phoneInp
            ? (phoneInp.id || phoneInp.name || 'phone') : 'phone');
        if (!seen.has(key)) {
            seen.add(key);
            fields.push({
                id: key, name: key, label: 'Phone Country Code',
                type: 'iti_phone', options: [], required: false, placeholder: '',
                section_heading: getSectionHeading(btn), sibling_context: '',
            });
        }
    }

    return fields;
}"""


# ---------------------------------------------------------------------------
# Default async fill function (minimal mirror of linkedin.py fill logic)
# ---------------------------------------------------------------------------
async def _default_fill_fn(page: Page, field: dict, answer: str) -> None:
    """Built-in fill implementation used when no custom ``fill_fn`` is supplied."""
    fid   = field.get("id",   "")
    fname = field.get("name", "")
    ftype = field.get("type", "text")

    if ftype in ("text", "textarea", "email", "tel", "number", "url", "search"):
        try:
            el = page.locator(f'[id="{fid}"]').first
            if await el.count() > 0:
                await el.fill(answer)
                return
        except Exception:
            pass
        await page.evaluate(
            """([id, name, val]) => {
                const el = document.getElementById(id)
                         || document.querySelector('[name="'+name+'"]');
                if (el) {
                    el.value = val;
                    el.dispatchEvent(new Event('input',  {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                }
            }""",
            [fid, fname, answer],
        )
    elif ftype == "select":
        try:
            await page.locator(f'[id="{fid}"]').select_option(label=answer)
        except Exception:
            try:
                await page.locator(f'[id="{fid}"]').select_option(value=answer)
            except Exception:
                pass
    elif ftype in ("radio", "checkbox"):
        await page.evaluate(
            """([name, val]) => {
                for (const inp of document.querySelectorAll('input[name="'+name+'"]')) {
                    const lbl = inp.labels?.[0]?.innerText?.trim() || inp.value;
                    if (inp.value === val || lbl === val) { inp.click(); break; }
                }
            }""",
            [fname, answer],
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
async def run_form_fill(
    page: Page,
    profile: dict,
    client: anthropic.Anthropic,
    fill_fn: Optional[Callable] = None,
    ats_platform_hint: Optional[str] = None,
) -> dict:
    """Orchestrate a complete ATS form auto-fill cycle.

    Flow:
      1. Detect ATS platform (URL + HTML signals).
      2. Run enriched FIELD_JS → raw field descriptors.
      3. Normalise each field to a canonical key; flag EEO fields.
      4. Check SQLite cache for trusted answers.
      5. Send uncached fields to Claude API.
      6. Merge cached + Claude answers.
      7. Fill each answer via ``fill_fn``; verify DOM settlement.
      8. Record successes in cache; invalidate stale cache hits on failure.
      9. Return a summary dict.

    Args:
        page:               Playwright Page already positioned on the form.
        profile:            Candidate profile dict (from task_input).
        client:             Anthropic API client.
        fill_fn:            Optional async callable ``fill_fn(page, field, answer)``.
        ats_platform_hint:  Override ATS detection when already known.

    Returns:
        ``{"ats_platform", "total_fields", "cache_hits", "claude_filled",
           "settled", "failed", "flagged_low_conf"}``
    """
    _fill = fill_fn or _default_fill_fn

    # ── 1. Detect ATS ──────────────────────────────────────────────────────
    html_snippet = ""
    try:
        html_snippet = await page.evaluate(
            "() => document.body?.innerHTML?.substring(0, 8000) || ''"
        )
    except Exception:
        pass

    ats = ats_platform_hint or detect_ats(page.url, html_snippet)
    logger.debug(f"run_form_fill: ATS = {ats!r}")

    page_title = ""
    try:
        page_title = await page.title()
    except Exception:
        pass

    # ── 2. Extract enriched fields ─────────────────────────────────────────
    try:
        raw_fields: list[dict] = await page.evaluate(ENRICHED_FIELD_JS)
    except Exception as exc:
        logger.error(f"run_form_fill: FIELD_JS eval failed: {exc}")
        return {"error": str(exc), "ats_platform": ats}

    # ── 3. Normalise fields ────────────────────────────────────────────────
    for f in raw_fields:
        if f.get("type") in ("legal_checkbox", "iti_phone"):
            f["canonical_key"] = f["type"]
            f["is_eeo"]        = False
        else:
            ck                 = normalize_field(f.get("label", ""), f.get("name", ""))
            f["canonical_key"] = ck
            f["is_eeo"]        = is_eeo_field(ck)

    # ── 4. Cache lookup ────────────────────────────────────────────────────
    cached_answers:  dict[str, str] = {}
    uncached_fields: list[dict]     = []
    cache_hits = 0

    for f in raw_fields:
        fid = f.get("id", "")
        ck  = f.get("canonical_key", "")
        if f.get("type") in ("legal_checkbox", "iti_phone"):
            uncached_fields.append(f)
            continue
        cached = await get_cached_answer(ats, ck)
        if cached is not None:
            cached_answers[fid] = cached
            cache_hits += 1
        else:
            uncached_fields.append(f)

    logger.debug(
        f"run_form_fill: {cache_hits} cache hits, "
        f"{len(uncached_fields)} sent to Claude"
    )

    # ── 5. Claude for uncached fields ──────────────────────────────────────
    claude_raw: dict[str, dict] = {}
    if uncached_fields:
        claude_raw = await get_fill_answers(
            fields=uncached_fields,
            profile=profile,
            ats_platform=ats,
            page_title=page_title,
            client=client,
        )

    # ── 6. Merge answers ───────────────────────────────────────────────────
    all_answers:      dict[str, str] = dict(cached_answers)
    flagged_low_conf: list[dict]     = []

    for fid, resp in claude_raw.items():
        answer = resp.get("answer")
        conf   = float(resp.get("conf", 0.0))
        if answer is None or conf < 0.60:
            continue
        all_answers[fid] = str(answer)
        if conf < 0.85:
            ck = next(
                (f.get("canonical_key", "") for f in raw_fields if f.get("id") == fid),
                fid,
            )
            flagged_low_conf.append(
                {"field_id": fid, "canonical_key": ck, "conf": conf}
            )

    # ── 7. Fill + verify ───────────────────────────────────────────────────
    settled_count = 0
    failed:       list[dict] = []
    field_by_id   = {f["id"]: f for f in raw_fields}

    for fid, answer in all_answers.items():
        field = field_by_id.get(fid)
        if not field:
            continue
        result = await fill_and_verify(page, field, answer, _fill)
        ck     = field.get("canonical_key", fid)

        if result["settled"]:
            settled_count += 1
            if field.get("type") not in ("legal_checkbox", "iti_phone"):
                await record_success(
                    ats_platform=ats,
                    canonical_key=ck,
                    raw_label=field.get("label", ""),
                    fill_strategy=field.get("type", "text"),
                    answer=answer,
                )
        else:
            failed.append(
                {
                    "field_id":      fid,
                    "canonical_key": ck,
                    "error_msg":     result.get("error_msg"),
                }
            )
            if fid in cached_answers:          # stale cache → invalidate
                await invalidate(ats, ck)

    return {
        "ats_platform":     ats,
        "total_fields":     len(raw_fields),
        "cache_hits":       cache_hits,
        "claude_filled":    len(claude_raw),
        "settled":          settled_count,
        "failed":           failed,
        "flagged_low_conf": flagged_low_conf,
    }
