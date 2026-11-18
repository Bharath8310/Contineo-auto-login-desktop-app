"""
Central configuration: portal URL, selectors, timeouts.
If the portal's HTML changes, this should be the ONLY file you need to edit.
Selectors were collected with tools/dump_selectors.py.
"""
import os
import sys
from pathlib import Path

# ── Portal ────────────────────────────────────────────────────────────────
PORTAL_URL = "https://bnmit-students.contineo.in/parents/index.php"

# ── Paths ─────────────────────────────────────────────────────────────────
# A PyInstaller --onefile exe unpacks to a temp folder (sys._MEIPASS) that is
# deleted on exit, so __file__ is NOT a safe place for user data there.
# Frozen exe -> %LOCALAPPDATA%\ContineoAutoLogin ; running from source -> project folder.
if getattr(sys, "frozen", False):
    APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ContineoAutoLogin"
else:
    APP_DIR = Path(__file__).resolve().parent
APP_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR = APP_DIR / "browser_profiles"   # one sub-folder per user id
USERS_FILE = APP_DIR / "users.json"
LOG_FILE = APP_DIR / "app.log"

# Windows Credential Manager entries appear as "<service>/<user_id>"-style
# generic credentials. One entry per user holds DOB + last 4 digits.
KEYRING_SERVICE = "contineo-autologin"

# ── Screen 1: Login (USN + DOB) ───────────────────────────────────────────
SEL_USERNAME = "#username"
SEL_DOB_DAY = "#dd"       # option values "01".."31"
SEL_DOB_MONTH = "#mm"     # option values "01".."12" (text Jan..Dec)
SEL_DOB_YEAR = "#yyyy"    # option values "1955".."2026"
SEL_LOGIN_BTN = 'input[type="submit"][value="Login"]'

DOB_YEAR_MIN = 1955       # range offered by the Year dropdown
DOB_YEAR_MAX = 2026

# ── Screen 2: Verification ────────────────────────────────────────────────
SEL_VERIFY_TYPE = "#id-type-select"
SEL_DIGIT_BOXES = "input.digit-input"         # 4 boxes, maxlength=1, no ids
SEL_SUBMIT_BTN = 'input[type="submit"][value="Submit"]'

# value -> label, exactly as in the portal's <select id="id-type-select">
VERIFICATION_TYPES = {
    "1": "Father Mobile Last 4 Digits",
    "2": "Mother Mobile Last 4 Digits",
    "3": "ABC ID Last 4 Digits",
}

# ── Screen 3: Logged in ───────────────────────────────────────────────────
# The URL stays index.php after login, so we can't detect success by URL.
# Rule used: "logged in" = neither the login form nor the verification
# form is on the page, AND this marker is visible.
# TODO(verify): run tools/check_selectors.py to the dashboard and confirm.
SEL_LOGGED_IN = 'a[href*="logout" i], a:has-text("Logout"), a:has-text("Log out")'

# ── Captcha (detect only, never interact) ─────────────────────────────────
# The page uses invisible reCAPTCHA v3 (api.js?render=..., size=invisible).
# A visible *challenge* would appear as a bframe iframe.
SEL_CAPTCHA_CHALLENGE = 'iframe[src*="recaptcha/api2/bframe"]'

# ── Timeouts (milliseconds) ───────────────────────────────────────────────
NAV_TIMEOUT_MS = 30_000        # initial page load
STEP_TIMEOUT_MS = 15_000       # max wait for the next screen to appear
ACTION_TIMEOUT_MS = 10_000     # default for click/fill/select auto-waiting

# ── Human-like pacing (milliseconds) ──────────────────────────────────────
DELAY_MIN_MS = 150
DELAY_MAX_MS = 450
TYPE_DELAY_MS = 60             # per keystroke when typing the USN
