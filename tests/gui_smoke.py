#!/usr/bin/env python3
"""GUI を実際に組み立てて描画するスモークテスト。

PyGObject とディスプレイが必要なため pytest の通常テストには含めず、
CI では ``xvfb-run`` 経由で実行する。ローカルでは実際の画面でも実行できる。

    xvfb-run -a env PYTHONPATH=src python3 tests/gui_smoke.py
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from cinnamon_fingerprint_manager.gui import APP_TITLE, FingerprintManager  # noqa: E402


def pump_events(win: Gtk.Window, rounds: int = 50) -> None:
    """描画イベントを実際に処理させる。"""
    for _ in range(rounds):
        win.queue_draw()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def main() -> int:
    win = FingerprintManager()
    win.show_all()
    win.cancel_button.hide()
    pump_events(win)

    assert win.get_title() == APP_TITLE, win.get_title()
    assert win.get_visible(), "window is not visible"
    assert win.add_button.get_visible(), "add button is not visible"
    assert win.refresh_button.get_visible(), "refresh button is not visible"
    assert not win.cancel_button.get_visible(), "cancel button should be hidden"
    assert win.listbox.get_children(), "list is empty"

    # fprintd が無い CI 環境ではエラー行が 1 件表示される
    print("GUI smoke OK:", win.get_title())
    print("  device label:", win.device_label.get_text())
    print("  rows:", len(win.listbox.get_children()))

    win.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
