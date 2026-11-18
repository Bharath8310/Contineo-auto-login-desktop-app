"""
Milestone 4 terminal front-end (temporary, until the UI exists).

    python tools/cli.py add            # prompts; DOB + digits are typed hidden
    python tools/cli.py list
    python tools/cli.py login <id>
    python tools/cli.py delete <id>
"""
import logging
import sys
from datetime import date
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C
import portal
import storage


def cmd_add() -> None:
    name = input("Display name: ")
    usn = input("USN: ")
    try:
        dob = date.fromisoformat(getpass("DOB (YYYY-MM-DD, hidden): ").strip())
    except ValueError:
        sys.exit("DOB must be a real date in YYYY-MM-DD format.")
    for k, v in C.VERIFICATION_TYPES.items():
        print(f"  {k} = {v}")
    vtype = input("Verification type: ").strip()
    last4 = getpass("Last 4 digits (hidden): ")
    try:
        u = storage.add_user(name, usn, dob, vtype, last4)
    except ValueError as e:
        sys.exit(f"Not saved: {e}")
    print(f"Saved {u.display_name} with id {u.id}")


def cmd_list() -> None:
    users = storage.list_users()
    if not users:
        print("No users yet. Run: python tools/cli.py add")
    for u in users:
        has = "ok" if storage.get_secrets(u.id) else "MISSING secrets"
        print(f"{u.id}  {u.display_name:<20} {u.usn:<12} type={u.verification_type}  [{has}]")


def cmd_login(user_id: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(C.LOG_FILE, encoding="utf-8")],
    )
    print("Close the Chrome window to finish.")
    r = portal.login_user(user_id)
    print("Final:", r.outcome.name, r.detail)


def cmd_delete(user_id: str) -> None:
    u = storage.get_user(user_id)
    if u is None:
        sys.exit("No such user.")
    if input(f"Delete {u.display_name} ({u.usn})? [y/N] ").lower() == "y":
        storage.delete_user(user_id)
        print("Deleted.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["add"]:
        cmd_add()
    elif args == ["list"]:
        cmd_list()
    elif len(args) == 2 and args[0] == "login":
        cmd_login(args[1])
    elif len(args) == 2 and args[0] == "delete":
        cmd_delete(args[1])
    else:
        print(__doc__)
