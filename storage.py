"""
User storage.

Split by sensitivity:
  users.json                      -> id, display_name, usn, verification_type
  Windows Credential Manager      -> DOB + last 4 digits (via keyring),
  (service=KEYRING_SERVICE,          stored as one small JSON blob per user
   username=<user id>)

Public API:
  list_users() / get_user(id) / get_secrets(id)
  add_user(...) / update_user(id, ...) / delete_user(id)
  validate(...)  -> raises ValueError with a user-friendly message
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import keyring
from keyring.errors import PasswordDeleteError

import config as C

# keyring normally discovers its backend through package metadata, which a
# PyInstaller exe may not include ("No recommended backend was available").
# Choosing the Windows Credential Manager backend explicitly avoids that.
if sys.platform == "win32":
    from keyring.backends.Windows import WinVaultKeyring
    keyring.set_keyring(WinVaultKeyring())

# Module-level so the test script can point them at a temp file / test service.
USERS_FILE: Path = C.USERS_FILE
SERVICE: str = C.KEYRING_SERVICE
PROFILES_DIR: Path = C.PROFILES_DIR

# VTU-style USN, e.g. 1BG22CS001: region digit, college (2 letters),
# year (2 digits), branch (2-3 letters), roll (3 digits).
USN_RE = re.compile(r"^[1-4][A-Z]{2}\d{2}[A-Z]{2,3}\d{3}$")


@dataclass
class User:
    id: str
    display_name: str
    usn: str
    verification_type: str


@dataclass
class Secrets:
    dob: date
    last4: str

    def __repr__(self) -> str:
        return "Secrets(dob=***, last4=***)"


# ── Validation ────────────────────────────────────────────────────────────
def validate(display_name: str, usn: str, dob: date, verification_type: str, last4: str) -> None:
    if not display_name.strip():
        raise ValueError("Display name is required.")
    if not USN_RE.match(usn):
        raise ValueError("USN must look like 1BG22CS001.")
    if not isinstance(dob, date):
        raise ValueError("Date of birth is not a valid date.")
    if not (C.DOB_YEAR_MIN <= dob.year <= C.DOB_YEAR_MAX):
        raise ValueError(f"Birth year must be between {C.DOB_YEAR_MIN} and {C.DOB_YEAR_MAX}.")
    if verification_type not in C.VERIFICATION_TYPES:
        raise ValueError("Choose a verification type.")
    if not re.fullmatch(r"\d{4}", last4):
        raise ValueError("Last 4 digits must be exactly 4 numbers.")


def _normalize(display_name: str, usn: str, last4: str) -> tuple[str, str, str]:
    return display_name.strip(), usn.strip().upper(), last4.strip()


# ── JSON file (non-sensitive) ─────────────────────────────────────────────
def _load() -> list[User]:
    if not USERS_FILE.exists():
        return []
    data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return [User(**u) for u in data]


def _save(users: list[User]) -> None:
    # Write to a temp file, then atomically replace: a crash mid-write
    # can never leave a half-written users.json.
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(u) for u in users], indent=2), encoding="utf-8")
    os.replace(tmp, USERS_FILE)


# ── Keyring (sensitive) ───────────────────────────────────────────────────
def _set_secrets(user_id: str, dob: date, last4: str) -> None:
    blob = json.dumps({"dob": dob.isoformat(), "last4": last4})
    keyring.set_password(SERVICE, user_id, blob)


def get_secrets(user_id: str) -> Optional[Secrets]:
    blob = keyring.get_password(SERVICE, user_id)
    if blob is None:
        return None
    d = json.loads(blob)
    return Secrets(dob=date.fromisoformat(d["dob"]), last4=d["last4"])


def _delete_secrets(user_id: str) -> None:
    try:
        keyring.delete_password(SERVICE, user_id)
    except PasswordDeleteError:
        pass  # already gone


# ── CRUD ──────────────────────────────────────────────────────────────────
def list_users() -> list[User]:
    return _load()


def get_user(user_id: str) -> Optional[User]:
    return next((u for u in _load() if u.id == user_id), None)


def add_user(display_name: str, usn: str, dob: date, verification_type: str, last4: str) -> User:
    display_name, usn, last4 = _normalize(display_name, usn, last4)
    validate(display_name, usn, dob, verification_type, last4)
    users = _load()
    if any(u.usn == usn for u in users):
        raise ValueError(f"A user with USN {usn} already exists.")

    user = User(uuid.uuid4().hex[:12], display_name, usn, verification_type)
    # Secrets first: if saving them fails, nothing half-exists in users.json.
    _set_secrets(user.id, dob, last4)
    try:
        _save(users + [user])
    except Exception:
        _delete_secrets(user.id)  # roll back
        raise
    return user


def update_user(user_id: str, display_name: str, usn: str, dob: date,
                verification_type: str, last4: str) -> User:
    display_name, usn, last4 = _normalize(display_name, usn, last4)
    validate(display_name, usn, dob, verification_type, last4)
    users = _load()
    idx = next((i for i, u in enumerate(users) if u.id == user_id), None)
    if idx is None:
        raise KeyError(user_id)
    if any(u.usn == usn and u.id != user_id for u in users):
        raise ValueError(f"A user with USN {usn} already exists.")

    users[idx] = User(user_id, display_name, usn, verification_type)
    _set_secrets(user_id, dob, last4)
    _save(users)
    return users[idx]


def delete_user(user_id: str, remove_profile: bool = True) -> None:
    """Remove from users.json, Credential Manager, and (by default) delete
    the user's browser profile so no logged-in session is left behind."""
    users = _load()
    _save([u for u in users if u.id != user_id])
    _delete_secrets(user_id)
    if remove_profile:
        shutil.rmtree(PROFILES_DIR / user_id, ignore_errors=True)
