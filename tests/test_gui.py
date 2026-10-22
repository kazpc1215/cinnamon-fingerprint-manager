"""GUI tests using fake fprintd commands.

These tests need PyGObject and a display.  They are skipped automatically when
the development virtualenv has no system ``gi`` module or when no display is
available.  CI runs them under Xvfb with the system Python.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from cinnamon_fingerprint_manager import gui  # noqa: E402


def _display_available() -> bool:
    try:
        result = Gtk.init_check(None)
    except Exception:
        return False
    if isinstance(result, tuple):
        return bool(result[0])
    return bool(result)


if not _display_available():
    pytest.skip("GTK display is not available", allow_module_level=True)


SAMPLE_LIST = """\
found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user alice on Sensor A (swipe):
 - #0: left-index-finger
 - #1: right-thumb
"""

SAMPLE_NO_FINGERS = """\
found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
User alice has no fingers enrolled for Sensor A.
"""


def write_script(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def write_list_script(bin_dir: Path, output: str, returncode: int = 0) -> None:
    body = f"cat <<'OUT'\n{output}OUT\nexit {returncode}\n"
    write_script(bin_dir, "fprintd-list", body)


def pump_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        value = predicate()
        if value:
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(gui, "USER", "alice")
    return bin_dir


@pytest.fixture
def window_factory(fake_bin):
    windows = []

    def make():
        win = gui.FingerprintManager()
        win.show_all()
        win.cancel_button.hide()
        windows.append(win)
        return win

    yield make

    # Keep windows alive until the process exits.  Destroying several GTK
    # windows while worker threads are winding down can crash PyGObject.
    for win in windows:
        win.hide()


def test_list_shows_first_device_and_fingers(fake_bin, window_factory):
    write_list_script(fake_bin, SAMPLE_LIST)
    win = window_factory()

    assert pump_until(lambda: win.last_list is not None and not win.refreshing)
    assert win.device_label.get_text() == "Sensor A（スワイプ式）"
    assert win.count_label.get_text() == "登録済み: 2 本"
    assert len(win.listbox.get_children()) == 2
    assert win.add_button.get_sensitive()
    assert "スワイプ式" in win.hint.get_text()
    assert not win.cancel_button.get_visible()


def test_list_shows_device_when_no_fingers_are_enrolled(fake_bin, window_factory):
    write_list_script(fake_bin, SAMPLE_NO_FINGERS)
    win = window_factory()

    assert pump_until(lambda: win.last_list is not None and not win.refreshing)
    assert win.last_list.found
    assert win.device_label.get_text() == "Sensor A"
    assert win.count_label.get_text() == "登録済み: 0 本"
    assert len(win.listbox.get_children()) == 1
    assert win.add_button.get_sensitive()
    assert "読み取り方法" in win.hint.get_text()


def test_list_failure_is_not_reported_as_a_missing_sensor(fake_bin, window_factory):
    write_list_script(fake_bin, "Failed to connect to fprintd\n", returncode=1)
    win = window_factory()

    assert pump_until(lambda: not win.refreshing and win.last_list is None)
    assert "fprintd から一覧を取得できませんでした" in win.device_label.get_text()
    assert "Failed to connect to fprintd" in win.device_label.get_text()
    assert not win.add_button.get_sensitive()


def test_verify_success_updates_status(fake_bin, window_factory):
    write_list_script(fake_bin, SAMPLE_LIST)
    write_script(fake_bin, "fprintd-verify", "printf '%s\\n' 'Verify result: verify-match'\n")
    win = window_factory()
    assert pump_until(lambda: win.last_list is not None and not win.refreshing)

    win.run_command(["fprintd-verify", "-f", "left-thumb", "alice"], "照合テスト", "verify")

    assert pump_until(
        lambda: (
            win.proc is None
            and not win.refreshing
            and win.status_label.get_text() == "照合に成功しました。"
        )
    )
    assert "Verify result: verify-match" in win.last_lines
    assert not win.cancel_button.get_visible()


def test_cancel_reports_cancelled_and_kills_the_process(fake_bin, window_factory):
    write_list_script(fake_bin, SAMPLE_LIST)
    write_script(
        fake_bin,
        "fprintd-enroll",
        "trap '' TERM\n"
        "printf '%s\\n' 'Enroll result: enroll-stage-passed'\n"
        "while :; do sleep 0.2; done\n",
    )
    win = window_factory()
    assert pump_until(lambda: win.last_list is not None and not win.refreshing)

    win.run_command(["fprintd-enroll", "-f", "left-thumb", "alice"], "登録", "enroll")
    assert pump_until(
        lambda: (
            win.proc is not None and any("enroll-stage-passed" in item for item in win.last_lines)
        )
    ), (win.proc, win.status_label.get_text(), win.last_lines)

    win.on_cancel_clicked(None)
    assert win.cancelled
    assert "中止しています" in win.status_label.get_text()

    assert pump_until(
        lambda: (
            win.proc is None
            and not win.refreshing
            and win.status_label.get_text() == "中止しました。"
        ),
        timeout=5.0,
    )
