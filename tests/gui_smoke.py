#!/usr/bin/env python3
"""GUI を実際に組み立てて描画するスモークテスト。

PyGObject とディスプレイが必要なため pytest の通常テストには含めず、
CI では ``xvfb-run`` 経由で実行する。fprintd の実機に依存しないよう、
一時的な偽の ``fprintd-list`` を PATH の先頭に置いてから画面を作る。

    xvfb-run -a env PYTHONPATH=src python3 tests/gui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from cinnamon_fingerprint_manager.gui import APP_TITLE, FingerprintManager  # noqa: E402

FAKE_LIST = """\
found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user alice on Sensor A (swipe):
 - #0: left-index-finger
 - #1: right-thumb
"""


def pump_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if predicate():
            return True
        time.sleep(0.01)
    return False


def install_fake_list(bin_dir: Path) -> None:
    path = bin_dir / "fprintd-list"
    path.write_text(
        "#!/bin/sh\ncat <<'OUT'\n" + FAKE_LIST + "OUT\nexit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fingerprint-manager-smoke-") as tmp:
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        install_fake_list(bin_dir)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

        win = FingerprintManager()
        win.show_all()
        win.cancel_button.hide()

        if not pump_until(lambda: win.last_list is not None and not win.refreshing):
            print("GUI smoke failed: timed out waiting for the device list", file=sys.stderr)
            win.destroy()
            return 1

        assert win.get_title() == APP_TITLE, win.get_title()
        assert win.get_visible(), "window is not visible"
        assert win.add_button.get_visible(), "add button is not visible"
        assert win.add_button.get_sensitive(), "add button is not sensitive"
        assert win.refresh_button.get_visible(), "refresh button is not visible"
        assert not win.cancel_button.get_visible(), "cancel button should be hidden"
        assert len(win.listbox.get_children()) == 2, "unexpected list rows"
        assert win.device_label.get_text() == "Sensor A（スワイプ式）", win.device_label.get_text()

        print("GUI smoke OK:", win.get_title())
        print("  device label:", win.device_label.get_text())
        print("  rows:", len(win.listbox.get_children()))

        win.destroy()
        return 0


if __name__ == "__main__":
    sys.exit(main())
