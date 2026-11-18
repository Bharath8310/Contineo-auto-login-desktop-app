"""
Milestone 1 test: confirm every selector in config.py matches on the live page.
Read-only. You log in manually; this only counts matching elements.

Usage (from project root):
    python tools/check_selectors.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import config from root

from playwright.sync_api import sync_playwright

import config as C

SCREEN1 = {
    "SEL_USERNAME": (C.SEL_USERNAME, 1),
    "SEL_DOB_DAY": (C.SEL_DOB_DAY, 1),
    "SEL_DOB_MONTH": (C.SEL_DOB_MONTH, 1),
    "SEL_DOB_YEAR": (C.SEL_DOB_YEAR, 1),
    "SEL_LOGIN_BTN": (C.SEL_LOGIN_BTN, 1),
}
SCREEN2 = {
    "SEL_VERIFY_TYPE": (C.SEL_VERIFY_TYPE, 1),
    "SEL_DIGIT_BOXES": (C.SEL_DIGIT_BOXES, 4),
    "SEL_SUBMIT_BTN": (C.SEL_SUBMIT_BTN, 1),
}


def check(page, checks: dict) -> None:
    for name, (sel, expected) in checks.items():
        n = page.locator(sel).count()
        mark = "OK  " if n == expected else "FAIL"
        print(f"  [{mark}] {name:<16} {sel!r}: found {n}, expected {expected}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()
        page.goto(C.PORTAL_URL, timeout=C.NAV_TIMEOUT_MS)

        print("\nScreen 1 (login):")
        check(page, SCREEN1)
        # Also verify the Verification dropdown values match what config expects.
        input("\n>>> Log in manually to the verification screen, then press Enter...")

        print("\nScreen 2 (verification):")
        check(page, SCREEN2)
        values = page.locator(f"{C.SEL_VERIFY_TYPE} option").evaluate_all(
            "opts => opts.map(o => o.value).filter(Boolean)")
        ok = sorted(values) == sorted(C.VERIFICATION_TYPES)
        print(f"  [{'OK  ' if ok else 'FAIL'}] VERIFICATION_TYPES values on page: {values}")

        input("\n>>> Finish verification manually. When the DASHBOARD is showing, press Enter...")

        print("\nScreen 3 (dashboard):")
        n = page.locator(C.SEL_LOGGED_IN).count()
        print(f"  [{'OK  ' if n else 'FAIL'}] SEL_LOGGED_IN matched {n} element(s)")
        print("  Login/verify forms still present?",
              page.locator(C.SEL_USERNAME).count(), page.locator(C.SEL_VERIFY_TYPE).count(),
              "(both should be 0)")
        # Help pick a reliable 'logged in' marker if the guess failed.
        links = page.locator("a").evaluate_all(
            "as => as.filter(a => a.offsetParent).map(a => [a.innerText.trim().slice(0,30), a.getAttribute('href')])"
            ".filter(([t,h]) => t || h).slice(0, 40)")
        print("  Visible links (first 40) - look for Logout/Sign out:")
        for text, href in links:
            print(f"    {text!r:<32} {href}")
        input("\n>>> Press Enter to close the browser...")
        browser.close()


if __name__ == "__main__":
    main()
