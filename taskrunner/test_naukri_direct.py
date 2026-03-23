"""
Quick test: open one specific Naukri job URL with manual login and
attempt to apply using the existing _apply_to_job logic.

Run from the taskrunner/ folder:
    python test_naukri_direct.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright
from automation.naukri import _login, _apply_to_job

# ── The URL to test ───────────────────────────────────────────
TEST_URL = (
    "https://www.naukri.com/job-listings-civil-engineer-"
    "the-indian-hume-pipe-co-ihp-bengaluru-2-to-6-years-"
    "300725017920?src=jobsearchDesk&sid=17742926316886992"
    "&xp=2&px=1&nignbevent_src=jobsearchDeskGNB"
)

# ── Minimal task_input — no credentials → manual login ───────
TASK_INPUT = {
    # Leave naukri_email / linkedin_email blank → bot waits for manual login
    "semi_auto":          False,  # ← Full auto: bot fills AND submits
    # Change to True to stop before Submit and review manually
    "apply_types":        "both", # allow direct apply
    "years_experience":   3,
    "notice_period":      30,
    "phone":              "",     # fill in if the form asks for it
    "smart_match":        False,  # skip score gate for this test
}

def main():
    print("=" * 60)
    print("  Naukri Direct-Apply Test")
    print("  Job URL:", TEST_URL[:80] + "…")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context()
        page    = context.new_page()

        try:
            # Step 1 — login (manual: you log in in the browser window)
            print("\n[TEST] Step 1: Login")
            ok = _login(page, TASK_INPUT)
            if not ok:
                print("[TEST] ❌ Login failed or timed out — aborting.")
                return

            # Step 2 — try applying to the test URL
            print(f"\n[TEST] Step 2: Trying to apply → {TEST_URL[:80]}…")
            result = _apply_to_job(page, TEST_URL, TASK_INPUT)

            print("\n" + "=" * 60)
            if result:
                print("  [TEST] ✅  _apply_to_job returned True (hand-off successful)")
            else:
                print("  [TEST] ❌  _apply_to_job returned False")
                reason = TASK_INPUT.get("_last_skip_reason", "—")
                meta   = TASK_INPUT.get("_last_skip_metadata", {})
                print(f"  [TEST]    skip_reason   : {reason}")
                if meta:
                    print(f"  [TEST]    skip_metadata : {meta}")
            print("=" * 60)

            # Keep browser open so you can inspect
            input("\n  Press ENTER to close the browser…")

        except Exception as e:
            import traceback
            print(f"\n[TEST] EXCEPTION: {e}")
            traceback.print_exc()
            input("  Press ENTER to close…")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
