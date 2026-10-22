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
_SECTION_LINE = re.compile(
    r"^\s*(?:"
    r"Fingerprints for user .+? on (?P<device>.+?)(?: \((?P<scan_type>.+?)\))?:"
    r"|User .+? has no fingers enrolled(?: for (?P<no_device>.+?))?\."
    r")\s*$",
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
    """Extract the first device and its enrolled fingers.

    ``fprintd-list`` may print one section per device.  The GUI only manages
    the default device, so ignore subsequent device sections instead of
    merging their fingerprints into the first one.
    """
    sections = list(_SECTION_LINE.finditer(text))
    if not sections:
        return ListResult(None, None, [])

    first = sections[0]
    device = (first.group("device") or first.group("no_device") or "").strip() or None
    scan_type = first.group("scan_type") or None

    if first.group("device"):
        end = sections[1].start() if len(sections) > 1 else len(text)
        fingers = _FINGER_LINE.findall(text[first.end() : end])
    else:
        # "User ... has no fingers enrolled for <device>." carries no scan type
        fingers = []

    return ListResult(device, scan_type, fingers)


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
        return Result("retry", "読み取りが不十分でした。もう一度指を置いてください。")
    if "enroll-data-full" in joined:
        return Result(
            "data-full",
            "登録できる指紋の上限に達しました。不要な指紋を削除してから登録してください。",
        )
    if "enroll-duplicate" in joined:
        return Result("duplicate", "この指紋は既に登録されています。")
    if "enroll-disconnected" in joined or "verify-disconnected" in joined:
        return Result(
            "disconnected",
            "指紋センサーとの接続が切れました。接続を確認してから再試行してください。",
        )
    if "AlreadyInUse" in joined or "already claimed" in joined:
        return Result(
            "busy",
            "指紋センサーは他のアプリで使用中です。他のアプリを閉じてから再試行してください。",
        )
    if "enroll-failed" in joined:
        return Result("enroll-failed", "指紋の登録に失敗しました。もう一度お試しください。")
    if returncode != 0:
        return Result(
            "error",
            f"コマンドが終了コード {returncode} で失敗しました。下の出力を確認してください。",
        )
    if action == "delete":
        return Result("deleted", "削除しました。")
    return Result("ok", "完了しました。")
