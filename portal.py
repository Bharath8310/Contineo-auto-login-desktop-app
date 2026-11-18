"""
Playwright automation for the Contineo parent portal login.

Flow:
    open portal (per-user Chrome profile)
      -> already logged in?              -> done (ALREADY_LOGGED_IN)
      -> login screen    -> USN + DOB    -> LOGIN
      -> verification    -> type + 4 digits -> SUBMIT
      -> dashboard?                      -> done (LOGGED_IN)
    Anything unexpected (captcha challenge, no progress within STEP_TIMEOUT)
    -> stop automating, leave the window open (MANUAL_NEEDED).

We never interact with reCAPTCHA; we only notice when a challenge is visible.

Terminal test (values come from env vars, never from code):
    $env:CONTINEO_USN   = "1BG22CS000"
    $env:CONTINEO_DOB   = "2004-07-15"      # YYYY-MM-DD
    $env:CONTINEO_VTYPE = "1"               # 1=Father 2=Mother 3=ABC ID
    $env:CONTINEO_LAST4 = "1234"
    python portal.py
"""
from __future__ import annotations

import logging
import os
import random
import threading
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import Page, sync_playwright

import config as C

log = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────
@dataclass
class Credentials:
    usn: str
    dob: date
    verification_type: str   # "1" | "2" | "3" (see config.VERIFICATION_TYPES)
    last4: str               # exactly 4 digits

    def __repr__(self) -> str:  # never leak secrets into logs/tracebacks
        return f"Credentials(usn={self.usn!r}, dob=***, verification_type={self.verification_type!r}, last4=***)"


class Outcome(Enum):
    LOGGED_IN = "Logged in ✓"
    ALREADY_LOGGED_IN = "Already logged in ✓"
    MANUAL_NEEDED = "Please finish login manually"
    FAILED = "Login failed – check details"
    CANCELLED = "Login cancelled"


@dataclass
class Result:
    outcome: Outcome
    detail: str = ""

    @property
    def message(self) -> str:
        """Text for the status label, e.g. 'Please finish login manually (captcha challenge shown)'."""
        return self.outcome.value + (f" ({self.detail})" if self.detail else "")


StatusCallback = Callable[[str], None]


# ── Small helpers ─────────────────────────────────────────────────────────
def _pause(page: Page) -> None:
    """Short random human-like pause. page.wait_for_timeout keeps Playwright's
    event loop running, unlike time.sleep."""
    page.wait_for_timeout(random.randint(C.DELAY_MIN_MS, C.DELAY_MAX_MS))


def _visible(page: Page, selector: str) -> bool:
    try:
        return page.locator(selector).first.is_visible()
    except PlaywrightError:
        return False  # page mid-navigation; treat as "not yet"


def _wait_for_any(page: Page, targets: dict[str, str], timeout_ms: int) -> Optional[str]:
    """Poll until one of the named selectors is visible. Returns its name, or
    None on timeout. Order matters: earlier entries win if several match.
    We poll (instead of one wait_for) because we need to know WHICH screen
    appeared, and a captcha challenge must be noticed as soon as it shows."""
    waited = 0
    step = 250
    while waited <= timeout_ms:
        for name, sel in targets.items():
            if _visible(page, sel):
                return name
        page.wait_for_timeout(step)
        waited += step
    return None


SCREENS = {
    "captcha": C.SEL_CAPTCHA_CHALLENGE,
    "dashboard": C.SEL_LOGGED_IN,
    "verify": C.SEL_VERIFY_TYPE,
    "login": C.SEL_USERNAME,
}


# ── The two form screens ──────────────────────────────────────────────────
def _fill_login_screen(page: Page, creds: Credentials) -> None:
    usn = page.locator(C.SEL_USERNAME)
    usn.click()
    usn.fill("")
    usn.press_sequentially(creds.usn, delay=C.TYPE_DELAY_MS)
    _pause(page)

    # select_option auto-waits for the <select> and the option to exist.
    # Values must match the portal's zero-padded option values.
    page.locator(C.SEL_DOB_DAY).select_option(f"{creds.dob.day:02d}")
    _pause(page)
    page.locator(C.SEL_DOB_MONTH).select_option(f"{creds.dob.month:02d}")
    _pause(page)
    page.locator(C.SEL_DOB_YEAR).select_option(str(creds.dob.year))
    _pause(page)

    page.locator(C.SEL_LOGIN_BTN).click()


def _fill_verify_screen(page: Page, creds: Credentials) -> None:
    page.locator(C.SEL_VERIFY_TYPE).select_option(creds.verification_type)
    _pause(page)

    boxes = page.locator(C.SEL_DIGIT_BOXES)
    boxes.first.wait_for()
    count = boxes.count()
    if count != 4:
        raise RuntimeError(f"expected 4 digit boxes, found {count}")

    # Fill one box at a time with real keystrokes so the page's own JS
    # (auto-advance focus, building the hidden 'enteredid') runs normally.
    # Clicking each box first makes us independent of auto-advance.
    for i, digit in enumerate(creds.last4):
        box = boxes.nth(i)
        box.click()
        box.fill("")
        box.press_sequentially(digit, delay=C.TYPE_DELAY_MS)
        page.wait_for_timeout(random.randint(80, 200))

    typed = "".join(boxes.nth(i).input_value() for i in range(4))
    if typed != creds.last4:
        raise RuntimeError("digit boxes did not keep the typed values")
    _pause(page)
    page.locator(C.SEL_SUBMIT_BTN).click()


# ── Main state machine ────────────────────────────────────────────────────
def _run_login(page: Page, creds: Credentials, status: StatusCallback) -> Result:
    status("Opening portal…")
    page.goto(C.PORTAL_URL, timeout=C.NAV_TIMEOUT_MS, wait_until="domcontentloaded")

    screen = _wait_for_any(page, SCREENS, C.STEP_TIMEOUT_MS)
    log.info("first screen: %s", screen)

    if screen == "dashboard":
        return Result(Outcome.ALREADY_LOGGED_IN, "existing session reused")

    if screen == "login":
        status("Logging in… (USN + DOB)")
        _fill_login_screen(page, creds)
        # After LOGIN, the login screen must disappear. Leave "login" out of
        # the targets: it is still visible for a moment while the page posts.
        screen = _wait_for_any(
            page, {k: v for k, v in SCREENS.items() if k != "login"}, C.STEP_TIMEOUT_MS
        )
        log.info("after LOGIN: %s", screen)
        if screen is None:
            if _visible(page, C.SEL_USERNAME):
                return Result(Outcome.FAILED, "still on login screen – USN/DOB may be wrong")
            return Result(Outcome.MANUAL_NEEDED, "page did not advance after LOGIN")

    if screen == "verify":
        status("Logging in… (verification)")
        _fill_verify_screen(page, creds)
        screen = _wait_for_any(
            page, {k: v for k, v in SCREENS.items() if k != "verify"}, C.STEP_TIMEOUT_MS
        )
        log.info("after SUBMIT: %s", screen)
        if screen == "dashboard":
            return Result(Outcome.LOGGED_IN)
        if screen == "login":
            return Result(Outcome.FAILED, "sent back to login – verification digits may be wrong")
        if screen is None and _visible(page, C.SEL_VERIFY_TYPE):
            return Result(Outcome.FAILED, "still on verification screen – digits/type may be wrong")

    if screen == "captcha":
        return Result(Outcome.MANUAL_NEEDED, "captcha challenge shown")
    if screen == "dashboard":
        return Result(Outcome.LOGGED_IN)
    return Result(Outcome.MANUAL_NEEDED, f"unexpected state ({screen or 'timeout'})")


def login(
    creds: Credentials,
    profile_dir: Path,
    status: StatusCallback = print,
    wait_until_closed: bool = True,
) -> Result:
    """Open Chrome with this user's own profile and log in.

    Blocks until the user closes the browser window (when wait_until_closed),
    because Playwright's sync API keeps Chrome alive only while this function's
    `with` block is running. The UI will call this from a background thread.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=False,
                no_viewport=True,          # use the real window size
                args=["--start-maximized"],
            )
        except PlaywrightError as e:
            result = _launch_error(e)
            log.warning("launch failed: %s", _first_line(e))
            status(result.message)
            return result

        # Remember if the user closes Chrome, so we never wait for a
        # 'close' event that already happened (that would hang forever).
        closed = threading.Event()
        context.on("close", lambda _ctx: closed.set())
        context.set_default_timeout(C.ACTION_TIMEOUT_MS)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            result = _run_login(page, creds, status)
        except PlaywrightError as e:
            log.warning("playwright error: %s", _first_line(e))
            result = _runtime_error(e, closed.is_set())
        except RuntimeError as e:
            log.warning("login error: %s", e)
            result = Result(Outcome.MANUAL_NEEDED, str(e))

        log.info("result: %s %s", result.outcome.name, result.detail)
        status(result.message)

        if closed.is_set():
            return result
        if wait_until_closed:
            result = _stay_open(context, page, result, status, closed)
        else:
            context.close()
    return result


def _first_line(e: Exception) -> str:
    return (getattr(e, "message", None) or str(e)).strip().splitlines()[0]


def _launch_error(e: PlaywrightError) -> Result:
    msg = str(e)
    if "is not found" in msg or "executable doesn't exist" in msg.lower():
        return Result(Outcome.FAILED, "Google Chrome is not installed")
    return Result(Outcome.FAILED, "couldn't start Chrome – is this user's browser already open?")


def _runtime_error(e: PlaywrightError, browser_closed: bool) -> Result:
    msg = str(e)
    if browser_closed or "has been closed" in msg:
        return Result(Outcome.CANCELLED, "browser was closed")
    if "net::ERR_" in msg:
        return Result(Outcome.FAILED, "can't reach the portal – check your internet")
    if isinstance(e, PlaywrightTimeout):
        return Result(Outcome.MANUAL_NEEDED, "page is too slow to respond")
    return Result(Outcome.MANUAL_NEEDED, "automation interrupted")


def _stay_open(context, page: Page, result: Result, status: StatusCallback,
               closed: threading.Event) -> Result:
    """Keep the browser open for the user until they close it.
    If we handed over (MANUAL_NEEDED), also watch for the dashboard so the
    UI can show success once the user finishes the login by hand."""
    if result.outcome is Outcome.MANUAL_NEEDED:
        try:
            page.locator(C.SEL_LOGGED_IN).first.wait_for(state="visible", timeout=0)
            result = Result(Outcome.LOGGED_IN, "finished manually")
            log.info("user finished login manually")
            status(result.message)
        except PlaywrightError:
            pass  # tab or browser closed before reaching the dashboard
    if not closed.is_set():
        try:
            # timeout=0 -> wait forever, until the user closes Chrome.
            context.wait_for_event("close", timeout=0)
        except PlaywrightError:
            pass
    return result


# ── Storage-backed entry point (Milestone 4) ──────────────────────────────
def login_user(user_id: str, status: StatusCallback = print,
               wait_until_closed: bool = True) -> Result:
    """Log in a saved user: details from users.json + Credential Manager,
    browser profile at browser_profiles/<user_id>/."""
    import storage  # local import: portal.py still works standalone for M2 tests

    user = storage.get_user(user_id)
    if user is None:
        return Result(Outcome.FAILED, "user not found")
    secrets = storage.get_secrets(user_id)
    if secrets is None:
        # e.g. Credential Manager entry removed by hand
        return Result(Outcome.FAILED, "saved DOB/digits missing – edit this user and re-enter them")

    log.info("login requested for user %s (%s)", user.id, user.display_name)
    creds = Credentials(
        usn=user.usn,
        dob=secrets.dob,
        verification_type=user.verification_type,
        last4=secrets.last4,
    )
    return login(creds, storage.PROFILES_DIR / user.id, status, wait_until_closed)


# ── Terminal test (Milestone 2) ───────────────────────────────────────────
def _creds_from_env() -> Credentials:
    missing = [k for k in ("CONTINEO_USN", "CONTINEO_DOB", "CONTINEO_VTYPE", "CONTINEO_LAST4")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Set these environment variables first: {', '.join(missing)}")
    return Credentials(
        usn=os.environ["CONTINEO_USN"].strip().upper(),
        dob=date.fromisoformat(os.environ["CONTINEO_DOB"].strip()),
        verification_type=os.environ["CONTINEO_VTYPE"].strip(),
        last4=os.environ["CONTINEO_LAST4"].strip(),
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(C.LOG_FILE, encoding="utf-8")],
    )
    creds = _creds_from_env()
    print("Close the Chrome window to end the test.")
    r = login(creds, C.PROFILES_DIR / "test")
    print("Final:", r.outcome.name, r.detail)
