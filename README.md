# Contineo Auto-Login

A Windows desktop app that logs into the BNMIT Contineo parent portal in a real
Chrome window, for one or more saved users.

- One click per user: fills USN + date of birth, then verification type + last 4 digits.
- Skips the forms when that user's session is still valid.
- Each user gets their own Chrome profile, so sessions never mix.
- DOB and the 4 digits are stored in **Windows Credential Manager**, not in files.
- reCAPTCHA is never touched. If a challenge appears or a page doesn't advance
  within 15 s, the app stops and leaves the window for you to finish.

## Requirements
- Windows 10/11
- **Google Chrome** installed (the app drives your installed Chrome)
- Python 3.11+ (only to run from source or build)

## Run from source
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```
No `playwright install` is needed: the app uses `channel="chrome"`.

## Use
1. **+ Add User** → display name, USN, DOB, verification type, last 4 digits.
2. **Login** → Chrome opens and logs in. Close Chrome when you're done.
3. **Edit** / **Delete** (delete also removes the saved secrets and browser session).

Status meanings:

| Status | Meaning |
|---|---|
| Logging in… | automation running |
| Logged in ✓ / Already logged in ✓ | done, browser is yours |
| Please finish login manually | captcha challenge or slow page – finish in the open window; status updates when you reach the dashboard |
| Login failed – check details | portal rejected the details, no internet, or Chrome missing (reason shown) |
| Login cancelled | you closed Chrome before it finished |

## Build the .exe
```powershell
.\.venv\Scripts\Activate.ps1
.\build.ps1                                  # -> dist\ContineoAutoLogin.exe
dist\ContineoAutoLogin.exe --selftest        # checks keyring, driver, Chrome -> app.log
```

## Where data lives
| | From source | Packaged .exe |
|---|---|---|
| users.json, app.log, browser_profiles\ | project folder | `%LOCALAPPDATA%\ContineoAutoLogin\` |
| DOB + last 4 digits | Credential Manager (`contineo-autologin`) | same |

To move your users from source to the exe, copy `users.json` into
`%LOCALAPPDATA%\ContineoAutoLogin\` (secrets are already shared through Credential Manager).

## Project layout
```
main.py      entry point, logging, --selftest
ui.py        main window + Add/Edit dialog
storage.py   user CRUD (users.json + keyring) and validation
portal.py    Playwright login automation
config.py    URL, selectors, timeouts, paths
build.ps1    PyInstaller build
tools/       dump_selectors.py, check_selectors.py, test_storage.py, cli.py
```

## If the portal changes
Run `python tools\check_selectors.py`. Any `FAIL` line names the selector to
update in `config.py`; `tools\dump_selectors.py` shows the new page structure.
