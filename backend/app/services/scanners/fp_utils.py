"""
fp_utils.py — Shared false-positive detection utilities for BreakMyApp scanners.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FIREBASE_SIBLING_KEYS = [
    "authDomain",
    "projectId",
    "storageBucket",
    "messagingSenderId",
    "appId",
]

_FIREBASE_NOTE = (
    "This is a Firebase Web SDK client key, which is safe to expose "
    "publicly. Firebase security relies on Firebase Security Rules and "
    "authorized domains, not on hiding this key. See: "
    "https://firebase.google.com/docs/projects/api-keys"
)


def is_firebase_client_config(file_path: str, line_number: int) -> tuple[bool, str]:
    """
    Checks whether a detected API-key-like string at the given file/line is
    actually a Firebase Web SDK client config key (safe to expose publicly),
    by checking for sibling Firebase config keys within +/-10 lines.

    Returns (is_firebase_config: bool, note: str).
    If the file can't be read, returns (False, "") — fail safe, do not
    suppress the finding if we can't verify it's safe.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_lines = f.readlines()

        match_line = (int(line_number) if line_number else 1) - 1  # 0-indexed
        window_start = max(0, match_line - 10)
        window_end = min(len(file_lines), match_line + 11)
        context = "".join(file_lines[window_start:window_end])

        siblings_found = sum(1 for k in _FIREBASE_SIBLING_KEYS if k in context)

        if siblings_found >= 2:
            return True, _FIREBASE_NOTE
        return False, ""
    except Exception:
        return False, ""
