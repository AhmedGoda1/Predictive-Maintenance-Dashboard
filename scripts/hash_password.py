"""Prints a password hash for the dashboard's [users] secrets (see docs/LOGIN.md).

    python scripts/hash_password.py              # asks for the password without showing it
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

from auth import hash_password  # noqa: E402

if __name__ == "__main__":
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Again: "):
        sys.exit("The passwords differ.")
    print(hash_password(password))
