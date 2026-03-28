"""
Synchronous field fill validation for LinkedIn external apply flow.

Validates that filled fields settle correctly in the DOM, with retry logic
for fields that don't settle on first attempt.
"""

import re
from typing import Callable, Optional


def fill_and_verify(
    page,
    field: dict,
    answer: str,
    fill_fn: Callable,
    retry: bool = True,
) -> dict:
    """Fill a form field synchronously and verify the value settled in the DOM.

    Args:
        page:     Playwright Page object (sync API).
        field:    Field descriptor dict with at least id, name, type, options.
        answer:   The intended answer string.
        fill_fn:  Callable that fills the field: fill_fn(page, field, answer)
        retry:    Whether to retry once with transformed answer if not settled.

    Returns:
        {"field_id", "intended", "actual", "settled", "error_msg"}
    """
    fid   = field.get("id",   "")
    fname = field.get("name", "")
    ftype = field.get("type", "text")

    result: dict = {
        "field_id":  fid,
        "intended":  answer,
        "actual":    "",
        "settled":   False,
        "error_msg": None,
    }

    # ── 1. Fill ────────────────────────────────────────────────────────────
    try:
        fill_fn(page, field, answer)
    except Exception as exc:
        result["error_msg"] = f"fill_fn error: {exc}"
        return result

    # ── 2. Wait for state to settle ────────────────────────────────────────
    page.wait_for_timeout(400)

    # ── 3. Read back actual DOM value ──────────────────────────────────────
    actual = _read_actual(page, fid, fname, ftype)
    result["actual"] = actual

    # ── 4. Check for visible validation error ──────────────────────────────
    error_msg = _get_error_message(page, fid, fname)
    result["error_msg"] = error_msg

    # ── 5. Determine whether value settled ─────────────────────────────────
    settled = _is_settled(ftype, answer, actual, field.get("options", []))
    result["settled"] = settled

    # ── 6. Retry once with transformed answer if needed ────────────────────
    if retry and not settled and not error_msg:
        transformed = _transform_answer(answer, ftype)
        if transformed != answer:
            try:
                fill_fn(page, field, transformed)
                page.wait_for_timeout(400)
                actual2  = _read_actual(page, fid, fname, ftype)
                settled2 = _is_settled(
                    ftype, transformed, actual2, field.get("options", [])
                )
                if settled2:
                    result["actual"]  = actual2
                    result["settled"] = True
                    return result
            except Exception:
                pass

    return result


def _read_actual(page, fid: str, fname: str, ftype: str) -> str:
    """Read the current DOM value of a field."""
    try:
        if ftype in ("radio", "checkbox"):
            return page.evaluate(
                """([id, name]) => {
                    const inp = document.getElementById(id)
                              || document.querySelector('input[name="' + name + '"]');
                    if (!inp) return '';
                    if (inp.type === 'radio') {
                        const ch = document.querySelector(
                            'input[name="' + name + '"]:checked');
                        return ch
                            ? (ch.labels?.[0]?.innerText?.trim() || ch.value)
                            : '';
                    }
                    return inp.checked ? 'checked' : '';
                }""",
                [fid, fname],
            )
        elif ftype == "select":
            return page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id)
                             || document.querySelector('select[name="' + name + '"]');
                    if (!el) return '';
                    const opt = el.options[el.selectedIndex];
                    return opt ? opt.text.trim() : '';
                }""",
                [fid, fname],
            )
        else:
            return page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id)
                             || document.querySelector('[name="' + name + '"]');
                    return el ? (el.value || '') : '';
                }""",
                [fid, fname],
            )
    except Exception:
        return ""


def _get_error_message(page, fid: str, fname: str) -> Optional[str]:
    """Find a visible validation error message near the field."""
    try:
        msg: Optional[str] = page.evaluate(
            """([id, name]) => {
                const el = document.getElementById(id)
                         || document.querySelector('[name="' + name + '"]');
                if (!el) return null;
                // Look in nearby parent containers
                let wrapper = el.parentElement;
                for (let i = 0; i < 5 && wrapper; i++) {
                    const cls = (wrapper.className || '').toLowerCase();
                    if (/field|form-group|row|input-wrapper|control|container/.test(cls))
                        break;
                    wrapper = wrapper.parentElement;
                }
                if (!wrapper) return null;
                // Find error/validation message
                const errEl = wrapper.querySelector(
                    '[class*="error"],[class*="invalid"],[class*="alert"],' +
                    '[class*="helper"],[aria-live],[role="alert"]'
                );
                if (!errEl) return null;
                const t = (errEl.innerText || errEl.textContent || '').trim();
                return (t && t.length > 0 && t.length < 200) ? t : null;
            }""",
            [fid, fname],
        )
        return msg
    except Exception:
        return None


def _is_settled(
    ftype: str,
    intended: str,
    actual: str,
    options: list = None,
) -> bool:
    """Return True if the actual DOM value reflects the intended answer."""
    if not actual:
        return False

    options = options or []
    i_lo = intended.strip().lower()
    a_lo = actual.strip().lower()

    if ftype in ("radio", "checkbox"):
        return a_lo in (i_lo, "checked")
    elif ftype == "select":
        # For select, check if both strings partially match
        return i_lo in a_lo or a_lo in i_lo or any(
            o.lower().strip() == i_lo for o in options
        )
    else:
        # For text/email/etc, check if intended substring is in actual
        return i_lo in a_lo or a_lo in i_lo


def _transform_answer(answer: str, ftype: str) -> str:
    """Light transformation for retry: strip spaces + numeric coercion."""
    transformed = answer.strip()

    if ftype in ("text", "number"):
        try:
            # Try numeric coercion
            f_val = float(transformed.replace(",", ""))
            return str(int(f_val)) if f_val == int(f_val) else str(f_val)
        except ValueError:
            pass

    return transformed
