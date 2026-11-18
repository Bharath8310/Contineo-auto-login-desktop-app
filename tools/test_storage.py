"""
Milestone 3 test: exercise storage.py CRUD with fake data.

Uses a temporary users.json and a separate keyring service name, so your
real users and credentials are never touched. Cleans up after itself.

    python tools/test_storage.py
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyring

import storage

tmp = Path(tempfile.mkdtemp())
storage.USERS_FILE = tmp / "users.json"
storage.PROFILES_DIR = tmp / "profiles"
storage.SERVICE = "contineo-autologin-TEST"

failures = 0


def check(label: str, cond: bool) -> None:
    global failures
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    failures += not cond


print("Add:")
u = storage.add_user("  Test Kid ", "1bg22cs001", date(2004, 7, 15), "1", "1234")
check("normalized name/USN", u.display_name == "Test Kid" and u.usn == "1BG22CS001")
check("listed", [x.id for x in storage.list_users()] == [u.id])
raw = storage.USERS_FILE.read_text()
check("users.json has no DOB/digits", "2004" not in raw and "1234" not in raw)
s = storage.get_secrets(u.id)
check("secrets in keyring", s is not None and s.dob == date(2004, 7, 15) and s.last4 == "1234")
check("secrets hidden in repr", "1234" not in repr(s))

print("Validation:")
for label, args in [
    ("bad USN", ("X", "ABC", date(2004, 1, 1), "1", "1234")),
    ("3 digits", ("X", "1BG22CS002", date(2004, 1, 1), "1", "123")),
    ("letters in digits", ("X", "1BG22CS002", date(2004, 1, 1), "1", "12a4")),
    ("bad verification type", ("X", "1BG22CS002", date(2004, 1, 1), "9", "1234")),
    ("year out of range", ("X", "1BG22CS002", date(1900, 1, 1), "1", "1234")),
    ("duplicate USN", ("X", "1BG22CS001", date(2004, 1, 1), "1", "1234")),
]:
    try:
        storage.add_user(*args)
        check(f"rejects {label}", False)
    except ValueError as e:
        check(f"rejects {label}: {e}", True)
check("nothing extra saved", len(storage.list_users()) == 1)

print("Update:")
storage.update_user(u.id, "Renamed", "1BG22CS001", date(2004, 8, 1), "2", "9876")
u2 = storage.get_user(u.id)
s2 = storage.get_secrets(u.id)
check("json updated", u2.display_name == "Renamed" and u2.verification_type == "2")
check("keyring updated", s2.dob == date(2004, 8, 1) and s2.last4 == "9876")

print("Delete:")
(storage.PROFILES_DIR / u.id).mkdir(parents=True)
storage.delete_user(u.id)
check("removed from json", storage.list_users() == [])
check("removed from keyring", keyring.get_password(storage.SERVICE, u.id) is None)
check("profile folder removed", not (storage.PROFILES_DIR / u.id).exists())

print("\nALL PASSED" if failures == 0 else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
