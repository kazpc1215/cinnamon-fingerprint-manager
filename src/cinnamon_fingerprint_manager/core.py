"""Pure helpers for the fingerprint manager.

This module deliberately has no GTK imports so it can be unit tested without a
display or PyGObject. It parses ``fprintd`` output and builds the command lines
used by the GUI.
"""

from __future__ import annotations

import getpass
import os
import pwd
import re
from typing import NamedTuple

FINGERS: tuple[tuple[str, str], ...] = (
    ("right-thumb", "右手の親指"),
    ("right-index-finger", "右手の人差し指"),
    ("right-middle-finger", "右手中指"),
    ("right-ring-finger", "右手薬指"),
    ("right-little-finger", "右手小指"),
    ("left-thumb", "左手の親指"),
    ("left-index-finger", "左手の人差し指"),
    ("left-middle-finger", "左手中指"),
    ("left-ring-finger", "左手薬指"),
    ("left-little-finger", "左手小指"),
)

FINGER_LABEL: dict[str, str] = dict(FINGERS)

SCAN_TYPE_LABEL: dict[str, str] = {
    "swipe": "スワイプ式",
    "press": "押し当て式",
}

_FINGER_LINE = re.compile(r"^\s*-\s*#\d+:\s*(\S+)\s*$", re.MULTILINE)
_DEVICE_LINE = re.compile(r"\bon (.+?)(?: \((.+?)\))?:\s*$", re.MULTILINE)
_NO_FINGERS_LINE = re.compile(
    r"^\s*User\s+.+?\s+has no fingers enrolled(?: for (.+?))?\.\s*$",
    re.MULTILINE,
)


class ListResult(NamedTuple):
    """Parsed result of ``fprintd-list``."""

    device: str | None
    scan_type: str | None
    fingers: list[str]

    @property
    def found(self) -> bool:
        return self.device is not None


class Result(NamedTuple):
    """Classified outcome of an fprintd command."""

    kind: str
    message: str


def parse_list_output(text: str) -> ListResult:
    """Extract the device name, scan type and enrolled fingers."""
    match = _DEVICE_LINE.search(text)
    if match:
        device = match.group(1).strip()
        scan_type = match.group(2).strip() if match.group(2) else None
        fingers = _FINGER_LINE.findall(text)
        return ListResult(device, scan_type, fingers)

    # fprintd prints a different line when the device exists but the user has
    # not enrolled any finger yet:
    #   User nobody has no fingers enrolled for AuthenTec AES2660.
    no_fingers = _NO_FINGERS_LINE.search(text)
    if no_fingers:
        device = (no_fingers.group(1) or "").strip() or None
        return ListResult(device, None, [])

    return ListResult(None, None, [])


def device_title(device: str, scan_type: str | None = None) -> str:
    """Human readable device heading."""
    if scan_type:
        return f"{device}（{SCAN_TYPE_LABEL.get(scan_type, scan_type)}）"
    return device


def finger_label(finger: str) -> str:
    """Japanese label for a fprintd finger name (falls back to the raw name)."""
    return FINGER_LABEL.get(finger, finger)


def summarize_output(text: str) -> str:
    """Return the last non-empty line of command output."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def available_fingers(enrolled: list[str]) -> list[tuple[str, str]]:
    """Fingers that are not enrolled yet, in display order."""
    taken = set(enrolled)
    return [(finger, label) for finger, label in FINGERS if finger not in taken]


def current_user() -> str:
    """Current login name, with a fallback for minimal environments."""
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        return os.environ.get("USER") or os.environ.get("LOGNAME") or getpass.getuser()


def build_list_command(user: str | None = None) -> list[str]:
    return ["fprintd-list", user or current_user()]


def build_enroll_command(finger: str, user: str | None = None) -> list[str]:
    return ["fprintd-enroll", "-f", finger, user or current_user()]


def build_verify_command(finger: str, user: str | None = None) -> list[str]:
    return ["fprintd-verify", "-f", finger, user or current_user()]


def build_delete_command(finger: str, user: str | None = None) -> list[str]:
    return ["fprintd-delete", user or current_user(), "-f", finger]


def classify_result(lines: list[str], returncode: int, action: str | None = None) -> Result:
    """Turn fprintd output into a status kind and a user facing message."""
    joined = "\n".join(lines)
    if "Authorization denied" in joined or "Not Authorized" in joined:
        return Result(
            "denied",
            "認証が承認されなかったため操作を中止しました。"
            "パスワードのダイアログで「認証」を選んでください。",
        )
    if "enroll-completed" in joined:
        return Result("enrolled", "登録が完了しました。")
    if "verify-no-match" in joined:
        return Result("no-match", "照合に失敗しました（指紋が一致しません）。")
    if "verify-match" in joined:
        return Result("verified", "照合に成功しました。")
    if "verify-retry-scan" in joined or "enroll-retry-scan" in joined:
        return Result("retry", "読み取りが不十分でした。もう一度スワイプしてください。")
    if returncode != 0:
        return Result(
            "error",
            f"コマンドが終了コード {returncode} で失敗しました。下の出力を確認してください。",
        )
    if action == "delete":
        return Result("deleted", "削除しました。")
    return Result("ok", "完了しました。")
