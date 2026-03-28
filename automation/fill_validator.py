"""
Post-fill validation module.

After a field is filled, reads back the actual DOM value and checks for
visible validation error messages near the field.  Retries once with a
lightly-transformed answer if the value did not settle.
"""

import re
from typing import Callable, Optional

from playwright.async_api import Page
from loguru import logger


async def fill_and_verify(
    page: Page,
    field: dict,
    answer: str,
    fill_fn: Callable,
) -> dict:
    """Fill a form field and verify the value settled in the DOM.

    Args:
        page:     Playwright :class:`~playwright.async_api.Page`.
        field:    Field descriptor dict with at least ``id``, ``name``,
                  ``type``, and ``options`` keys.
        answer:   The intended answer string.
        fill_fn:  Async callable ``fill_fn(page, field, answer)`` that
                  performs the actual DOM interaction.

    Returns:
        ``{"field_id", "intended", "actual", "settled", "error_msg"}``
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
        await fill_fn(page, field, answer)
    except Exception as exc:
        result["error_msg"] = f"fill_fn error: {exc}"
        logger.warning(f"fill_and_verify: fill_fn failed for {fid!r}: {exc}")
        return result

    # ── 2. Wait for React/Vue state to settle ──────────────────────────────
    await page.wait_for_timeout(400)

    # ── 3. Read back actual DOM value ──────────────────────────────────────
    actual = await _read_actual(page, fid, fname, ftype)
    result["actual"] = actual

    # ── 4. Check for visible validation error near the field ───────────────
    error_msg = await _get_error_message(page, fid, fname)
    result["error_msg"] = error_msg

    # ── 5. Determine whether the value settled ─────────────────────────────
    settled = _is_settled(ftype, answer, actual, field.get("options", []))
    result["settled"] = settled

    # ── 6. Retry once with a transformed answer if not settled ─────────────
    if not settled and not error_msg:
        transformed = _transform_answer(answer, ftype)
        if transformed != answer:
            try:
                await fill_fn(page, field, transformed)
                await page.wait_for_timeout(400)
                actual2  = await _read_actual(page, fid, fname, ftype)
                settled2 = _is_settled(
                    ftype, transformed, actual2, field.get("options", [])
                )
                if settled2:
                    result["actual"]  = actual2
                    result["settled"] = True
                    logger.debug(
                        f"fill_and_verify: settled after retry for "
                        f"{fid!r} with {transformed!r}"
                    )
                    return result
            except Exception as exc:
                logger.warning(
                    f"fill_and_verify: retry fill_fn failed for "
                    f"{fid!r}: {exc}"
                )

    if not result["settled"]:
        logger.warning(
            f"fill_and_verify: NOT settled — id={fid!r} type={ftype!r} "
            f"intended={answer!r} actual={actual!r} error={error_msg!r}"
        )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _read_actual(
    page: Page,
    fid: str,
    fname: str,
    ftype: str,
) -> str:
    """Read the current DOM value of a field via ``page.evaluate()``."""
    try:
        if ftype in ("radio", "checkbox"):
            return await page.evaluate(
                """([id, name]) => {
                    const inp = document.getElementById(id)
                              || document.querySelector(
                                     'input[name="' + name + '"]');
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
            return await page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id)
                             || document.querySelector(
                                    'select[name="' + name + '"]');
                    if (!el) return '';
                    const opt = el.options[el.selectedIndex];
                    return opt ? opt.text.trim() : '';
                }""",
                [fid, fname],
            )
        else:
            return await page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id)
                             || document.querySelector(
                                    '[name="' + name + '"]');
                    return el ? (el.value || '') : '';
                }""",
                [fid, fname],
            )
    except Exception as exc:
        logger.debug(f"_read_actual error for {fid!r}: {exc}")
        return ""


async def _get_error_message(
    page: Page,
    fid: str,
    fname: str,
) -> Optional[str]:
    """Find a visible validation error message near the field element."""
    try:
        msg: Optional[str] = await page.evaluate(
            """([id, name]) => {
                const el = document.getElementById(id)
                         || document.querySelector('[name="' + name + '"]');
                if (!el) return null;
                let wrapper = el.parentElement;
                for (let i = 0; i < 5 && wrapper; i++) {
                    const cls = (wrapper.className || '').toLowerCase();
                    if (/field|form-group|row|input-wrapper|control/.test(cls))
                        break;
                    wrapper = wrapper.parentElement;
                }
                if (!wrapper) return null;
                const errEl = wrapper.querySelector(
                    '[class*="error"],[class*="invalid"],' +
                    '[class*="helper"],[aria-live]'
                );
                if (!errEl) return null;
                const t = (errEl.innerText || '').trim();
                return t || null;
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
    options: list[str],
) -> bool:
    """Return ``True`` if the actual DOM value reflects the intended answer."""
    if not actual:
        return False
    i_lo = intended.strip().lower()
    a_lo = actual.strip().lower()
    if ftype in ("radio", "checkbox"):
        return a_lo in (i_lo, "checked")
    elif ftype == "select":
        return i_lo in a_lo or a_lo in i_lo
    else:
        return i_lo in a_lo


def _transform_answer(answer: str, ftype: str) -> str:
    """Light transformation for retry: strip spaces + numeric coercion."""
    transformed = answer.strip()
    if ftype in ("text", "number"):
        try:
            f_val = float(transformed.replace(",", ""))
            return str(int(f_val)) if f_val == int(f_val) else str(f_val)
        except ValueError:
            pass
    return transformed
