"""
External form fill orchestration module.

Improves external ATS form filling by:
1. Using Claude to get field answers
2. Validating each fill settles in the DOM
3. Retrying failed fills with transformed answers
4. Logging all actions for debugging
"""

import time as _time
from typing import Callable, Optional


class ExternalFormFiller:
    """Orchestrates filling and validating forms on external ATS portals."""

    def __init__(self, page, log_fn: Callable = None):
        self.page = page
        self.log = log_fn or (lambda msg, level: print(f"[{level}] {msg}"))
        self.fill_stats = {
            "total": 0,
            "settled": 0,
            "failed": 0,
            "retried": 0,
        }

    def fill_fields(self, fields: list, answers_dict: dict) -> dict:
        """Fill multiple fields and track success/failure.

        Args:
            fields: List of field descriptors {id, name, type, label, ...}
            answers_dict: Mapping of field id/name → answer value

        Returns:
            {
                "settled": count of fields that settled successfully,
                "failed": count of fields that failed,
               "errors": list of error dicts,
            }
        """
        if not fields:
            return {"settled": 0, "failed": 0, "errors": []}

        errors = []

        for field in fields:
            fid = field.get("id", "")
            fname = field.get("name", "") or fid
            flabel = field.get("label", "?")[:50]

            # Get answer for this field (try both id and name)
            answer = str(answers_dict.get(fid) or answers_dict.get(fname) or "").strip()
            if not answer:
                continue

            self.fill_stats["total"] += 1

            # Attempt to fill with validation
            result = self._fill_one(field, answer)

            if result["settled"]:
                self.fill_stats["settled"] += 1
                self.log(
                    f"✓ Field '{flabel}' filled successfully with '{answer[:40]}'",
                    "info"
                )
            else:
                self.fill_stats["failed"] += 1
                err_msg = result.get("error_msg", "Unknown error")
                self.log(
                    f"✗ Field '{flabel}' failed to settle: {err_msg}",
                    "warning"
                )
                errors.append({
                    "field_id": fid,
                    "field_label": flabel,
                    "intended": answer,
                    "actual": result.get("actual", ""),
                    "error": err_msg,
                })

        return {
            "settled": self.fill_stats["settled"],
            "failed": self.fill_stats["failed"],
            "total": self.fill_stats["total"],
            "errors": errors,
        }

    def _fill_one(self, field: dict, answer: str) -> dict:
        """Fill one field with validation and retry logic.

        Returns a result dict with keys: settled, actual, error_msg
        """
        fid = field.get("id", "")
        fname = field.get("name", "") or fid
        ftype = field.get("type", "text")

        result = {
            "field_id": fid,
            "intended": answer,
            "actual": "",
            "settled": False,
            "error_msg": None,
        }

        # ── 1. Scroll field into view if possible ──────────────────────────
        try:
            self.page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id) ||
                               document.querySelector('[name="' + name + '"]');
                    if (el && el.scrollIntoView) {
                        el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    }
                }""",
                [fid, fname]
            )
            _time.sleep(0.3)
        except Exception:
            pass

        # ── 2. Perform the fill ────────────────────────────────────────────
        try:
            self._perform_fill(field, answer)
        except Exception as e:
            result["error_msg"] = f"Fill failed: {e}"
            return result

        # ── 3. Wait for DOM to settle ──────────────────────────────────────
        self.page.wait_for_timeout(500)

        # ── 4. Read back the value ─────────────────────────────────────────
        actual = self._read_actual(fid, fname, ftype)
        result["actual"] = actual

        # ── 5. Check for validation errors ─────────────────────────────────
        error_msg = self._get_error_message(fid, fname)
        result["error_msg"] = error_msg

        # ── 6. Determine if settled ────────────────────────────────────────
        settled = self._is_settled(ftype, answer, actual, field.get("options", []))
        result["settled"] = settled

        # ── 7. Retry with transformed answer if not settled ─────────────────
        if not settled and not error_msg:
            transformed = self._transform_answer(answer, ftype)
            if transformed != answer:
                self.fill_stats["retried"] += 1
                try:
                    self._perform_fill(field, transformed)
                    self.page.wait_for_timeout(500)
                    actual2 = self._read_actual(fid, fname, ftype)
                    settled2 = self._is_settled(ftype, transformed, actual2, field.get("options", []))
                    if settled2:
                        result["actual"] = actual2
                        result["settled"] = True
                        return result
                except Exception:
                    pass

        return result

    def _perform_fill(self, field: dict, answer: str) -> None:
        """Actually fill the field in the DOM."""
        fid = field.get("id", "")
        fname = field.get("name", "") or fid
        ftype = field.get("type", "text")

        def _has_css_special(s: str) -> bool:
            return any(c in s for c in ("[", "]", ".", "#", ":", "(", ")", "!", "/"))

        if ftype == "select":
            # Try by label first, then by value
            for try_method in ("label", "value"):
                try:
                    if fid and not _has_css_special(fid):
                        self.page.locator(f'[id="{fid}"]').select_option(
                            label=answer if try_method == "label" else None,
                            value=answer if try_method == "value" else None,
                        )
                        return
                    elif fname:
                        self.page.locator(f'[name="{fname}"]').select_option(
                            label=answer if try_method == "label" else None,
                            value=answer if try_method == "value" else None,
                        )
                        return
                except Exception:
                    continue

            # JS fallback
            self.page.evaluate(
                """([id, name, val]) => {
                    const sel = document.getElementById(id) ||
                                document.querySelector('select[name="' + name + '"]');
                    if (!sel) return;
                    for (const opt of sel.options) {
                        if (opt.text.trim() === val || opt.value === val) {
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                }""",
                [fid, fname, answer]
            )

        elif ftype in ("radio", "checkbox"):
            self.page.evaluate(
                """([name, val]) => {
                    for (const inp of document.querySelectorAll('input[name="' + name + '"]')) {
                        if (!inp.offsetParent) continue;  // skip hidden
                        const lbl = inp.labels?.[0]?.innerText?.trim() || inp.value;
                        if (inp.value === val || lbl === val) {
                            inp.click();
                            break;
                        }
                    }
                }""",
                [fname, answer]
            )

        elif ftype in ("text", "textarea", "email", "tel", "number", "url", "search"):
            # Try Playwright locator first for clean IDs
            if fid and not fid.startswith("grp_") and not _has_css_special(fid):
                el = self.page.locator(f'[id="{fid}"]').first
                if el.count() > 0:
                    el.fill(answer)
                    return

            # JS fill for problematic IDs
            self.page.evaluate(
                """([id, name, val]) => {
                    const el = document.getElementById(id) ||
                               document.querySelector('[name="' + name + '"]');
                    if (el) {
                        el.focus();
                        el.value = val;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
                [fid, fname, answer]
            )

    def _read_actual(self, fid: str, fname: str, ftype: str) -> str:
        """Read the current DOM value."""
        try:
            if ftype in ("radio", "checkbox"):
                return self.page.evaluate(
                    """([id, name]) => {
                        const inp = document.getElementById(id) ||
                                    document.querySelector('input[name="' + name + '"]');
                        if (!inp) return '';
                        if (inp.type === 'radio') {
                            const ch = document.querySelector('input[name="' + name + '"]:checked');
                            return ch ? (ch.labels?.[0]?.innerText?.trim() || ch.value) : '';
                        }
                        return inp.checked ? 'checked' : '';
                    }""",
                    [fid, fname],
                )
            elif ftype == "select":
                return self.page.evaluate(
                    """([id, name]) => {
                        const sel = document.getElementById(id) ||
                                   document.querySelector('select[name="' + name + '"]');
                        if (!sel) return '';
                        const opt = sel.options[sel.selectedIndex];
                        return opt ? opt.text.trim() : '';
                    }""",
                    [fid, fname],
                )
            else:
                return self.page.evaluate(
                    """([id, name]) => {
                        const el = document.getElementById(id) ||
                                   document.querySelector('[name="' + name + '"]');
                        return el ? (el.value || '') : '';
                    }""",
                    [fid, fname],
                )
        except Exception:
            return ""

    def _get_error_message(self, fid: str, fname: str) -> Optional[str]:
        """Find validation error message near the field."""
        try:
            msg = self.page.evaluate(
                """([id, name]) => {
                    const el = document.getElementById(id) ||
                               document.querySelector('[name="' + name + '"]');
                    if (!el) return null;
                    let wrapper = el.parentElement;
                    for (let i = 0; i < 5 && wrapper; i++) {
                        const cls = (wrapper.className || '').toLowerCase();
                        if (/field|form-group|row|wrapper|container|control/.test(cls)) break;
                        wrapper = wrapper.parentElement;
                    }
                    if (!wrapper) return null;
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

    @staticmethod
    def _is_settled(ftype: str, intended: str, actual: str, options: list = None) -> bool:
        """Check if value settled as expected."""
        if not actual:
            return False

        options = options or []
        i_lo = intended.strip().lower()
        a_lo = actual.strip().lower()

        if ftype in ("radio", "checkbox"):
            return a_lo in (i_lo, "checked")
        elif ftype == "select":
            return i_lo in a_lo or a_lo in i_lo or any(
                o.lower().strip() == i_lo for o in options
            )
        else:
            return i_lo in a_lo or a_lo in i_lo

    @staticmethod
    def _transform_answer(answer: str, ftype: str) -> str:
        """Light transformation for retry."""
        transformed = answer.strip()
        if ftype in ("text", "number"):
            try:
                f_val = float(transformed.replace(",", ""))
                return str(int(f_val)) if f_val == int(f_val) else str(f_val)
            except ValueError:
                pass
        return transformed
