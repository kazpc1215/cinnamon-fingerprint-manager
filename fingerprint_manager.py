#!/usr/bin/env python3
"""指紋マネージャー — fprintd の登録・削除・テストを GUI で行う小さなフロントエンド。

依存: python3-gi / GTK3 / fprintd (いずれも Linux Mint に標準で入っているもの)
"""

import os
import re
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

APP_TITLE = "指紋マネージャー"
USER = os.environ.get("USER") or os.environ.get("LOGNAME") or ""

FINGERS = [
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
]
FINGER_LABEL = dict(FINGERS)


class FingerprintManager(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_TITLE)
        self.set_default_size(560, 560)
        self.set_border_width(0)
        self.proc = None
        self.last_lines = []

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title(APP_TITLE)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        # --- デバイス情報 ---
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_border_width(16)
        self.device_label = Gtk.Label(label="確認中…", xalign=0)
        self.device_label.set_ellipsize(Pango.EllipsizeMode.END)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
        self.device_label.set_attributes(attrs)
        self.count_label = Gtk.Label(label="", xalign=0)
        self.count_label.get_style_context().add_class("dim-label")
        info_box.pack_start(self.device_label, False, False, 0)
        info_box.pack_start(self.count_label, False, False, 0)
        outer.pack_start(info_box, False, False, 0)

        # --- 登録済み一覧 ---
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_header_func(self._row_header)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_size_request(-1, 200)
        scroll.add(self.listbox)
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.set_border_width(12)
        frame.add(scroll)
        outer.pack_start(frame, True, True, 0)

        # --- ヒント ---
        hint = Gtk.Label(xalign=0)
        hint.set_markup(
            "<small>追加・削除のときは、本人確認のためパスワードのダイアログが出ます。\n"
            "このセンサーはスワイプ式です。指を端から端へ、一定方向にゆっくり動かしてください。</small>"
        )
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("dim-label")
        hint.set_margin_start(12)
        hint.set_margin_end(12)
        hint.set_margin_top(4)
        hint.set_margin_bottom(4)
        outer.pack_start(hint, False, False, 0)

        # --- ボタン ---
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_border_width(12)
        self.add_button = Gtk.Button(label="指を追加")
        self.add_button.get_style_context().add_class("suggested-action")
        self.add_button.connect("clicked", self.on_add_clicked)
        self.refresh_button = Gtk.Button(label="更新")
        self.refresh_button.connect("clicked", lambda *_: self.refresh())
        self.cancel_button = Gtk.Button(label="中止")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.cancel_button.set_no_show_all(True)
        buttons.pack_start(self.add_button, False, False, 0)
        buttons.pack_start(self.refresh_button, False, False, 0)
        buttons.pack_end(self.cancel_button, False, False, 0)
        outer.pack_start(buttons, False, False, 0)

        # --- 進捗・出力 ---
        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_end(12)
        self.status_label.set_margin_bottom(8)
        self.status_label.set_line_wrap(True)
        outer.pack_start(self.status_label, False, False, 0)

        out_scroll = Gtk.ScrolledWindow()
        out_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        out_scroll.set_shadow_type(Gtk.ShadowType.IN)
        out_scroll.set_size_request(-1, 120)
        self.output = Gtk.TextView()
        self.output.set_editable(False)
        self.output.set_cursor_visible(False)
        self.output.set_monospace(True)
        self.output.set_left_margin(6)
        self.output.set_right_margin(6)
        out_scroll.add(self.output)
        out_frame = Gtk.Frame()
        out_frame.set_border_width(12)
        out_frame.add(out_scroll)
        outer.pack_start(out_frame, False, False, 0)

        self.connect("destroy", self.on_destroy)
        self.refresh()

    # ---------- 一覧 ----------
    @staticmethod
    def _row_header(row, before):
        if before is not None:
            row.set_header(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    def refresh(self):
        try:
            result = subprocess.run(
                ["fprintd-list", USER],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._set_device_error(str(exc))
            return

        text = result.stdout + result.stderr
        device = None
        scan_type = None
        m = re.search(r"on (.+?)(?: \((.+?)\))?:\s*$", text, re.MULTILINE)
        if m:
            device = m.group(1)
            scan_type = m.group(2)

        fingers = re.findall(r"^\s*-\s*#\d+:\s*(\S+)\s*$", text, re.MULTILINE)

        for row in self.listbox.get_children():
            self.listbox.remove(row)

        if device:
            label = device + (f"（{scan_type} 式）" if scan_type else "")
            self.device_label.set_text(label)
            self.count_label.set_text(f"登録済み: {len(fingers)} 本")
        else:
            self._set_device_error("指紋センサーが見つかりません")
            return

        if not fingers:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label="まだ指紋が登録されていません。「指を追加」から登録できます。")
            lbl.set_margin_top(16)
            lbl.set_margin_bottom(16)
            lbl.get_style_context().add_class("dim-label")
            row.add(lbl)
            self.listbox.add(row)

        for name in fingers:
            self.listbox.add(self._make_row(name))

        self.listbox.show_all()
        self.cancel_button.hide()

    def _set_device_error(self, message):
        self.device_label.set_text(message)
        self.count_label.set_text("")
        for row in self.listbox.get_children():
            self.listbox.remove(row)
        row = Gtk.ListBoxRow()
        lbl = Gtk.Label(label=message)
        lbl.set_margin_top(16)
        lbl.set_margin_bottom(16)
        row.add(lbl)
        self.listbox.add(row)
        self.listbox.show_all()

    def _make_row(self, finger):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_border_width(8)

        icon = Gtk.Image.new_from_icon_name("dialog-password", Gtk.IconSize.BUTTON)
        box.pack_start(icon, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label(label=FINGER_LABEL.get(finger, finger), xalign=0)
        sub = Gtk.Label(label=finger, xalign=0)
        sub.get_style_context().add_class("dim-label")
        text.pack_start(title, False, False, 0)
        text.pack_start(sub, False, False, 0)
        box.pack_start(text, True, True, 0)

        verify = Gtk.Button(label="テスト")
        verify.connect("clicked", lambda *_: self.run_command(
            ["fprintd-verify", "-f", finger], "照合テスト"))
        delete = Gtk.Button(label="削除")
        delete.get_style_context().add_class("destructive-action")
        delete.connect("clicked", lambda *_: self.on_delete_clicked(finger, title.get_text()))
        box.pack_end(delete, False, False, 0)
        box.pack_end(verify, False, False, 0)

        row.add(box)
        return row

    # ---------- 操作 ----------
    def on_add_clicked(self, _button):
        enrolled = {
            m for m in re.findall(
                r"^\s*-\s*#\d+:\s*(\S+)\s*$", self._get_list_text(), re.MULTILINE)
        }
        candidates = [(f, l) for f, l in FINGERS if f not in enrolled]
        if not candidates:
            self._message("すべての指が登録済みです。", Gtk.MessageType.INFO)
            return

        dialog = Gtk.Dialog(title="登録する指を選択", transient_for=self, modal=True)
        dialog.add_button("キャンセル", Gtk.ResponseType.CANCEL)
        dialog.add_button("登録する", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        box.add(Gtk.Label(label="登録する指を選んでください:", xalign=0))
        combo = Gtk.ComboBoxText()
        for finger, label in candidates:
            combo.append(finger, label)
        combo.set_active(0)
        box.pack_start(combo, False, False, 0)
        box.show_all()
        response = dialog.run()
        finger = combo.get_active_id()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and finger:
            self.run_command(
                ["fprintd-enroll", "-f", finger],
                f"「{FINGER_LABEL.get(finger, finger)}」を登録")

    def on_delete_clicked(self, finger, label):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"「{label}」の指紋を削除しますか？",
        )
        dialog.format_secondary_text("削除後は、その指では認証できなくなります。")
        dialog.add_button("キャンセル", Gtk.ResponseType.CANCEL)
        delete = dialog.add_button("削除する", Gtk.ResponseType.OK)
        delete.get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.run_command(
                ["fprintd-delete", USER, "-f", finger],
                f"「{label}」を削除")

    def on_cancel_clicked(self, _button):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status_label.set_text("中止しました。")

    def on_destroy(self, _widget):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        Gtk.main_quit()

    # ---------- コマンド実行 ----------
    def _get_list_text(self):
        try:
            result = subprocess.run(
                ["fprintd-list", USER], capture_output=True, text=True, timeout=15)
            return result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def run_command(self, args, description):
        if self.proc and self.proc.poll() is None:
            return
        self.last_lines = []
        self._clear_output()
        self.status_label.set_text(f"{description} を開始しました…")
        self.add_button.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.cancel_button.show()
        self.cancel_button.set_sensitive(True)
        for row in self.listbox.get_children():
            row.set_sensitive(False)

        try:
            self.proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as exc:
            self._finish(-1, str(exc))
            return

        threading.Thread(
            target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            line = line.rstrip("\n")
            GLib.idle_add(self._append_line, line)
        rc = proc.wait()
        GLib.idle_add(self._finish, rc, None)

    def _append_line(self, line):
        self.last_lines.append(line)
        buf = self.output.get_buffer()
        buf.insert(buf.get_end_iter(), line + "\n")
        self.output.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 0.0)
        return False

    def _finish(self, rc, error):
        self.proc = None
        self.cancel_button.hide()
        self.add_button.set_sensitive(True)
        self.refresh_button.set_sensitive(True)
        self.refresh()

        joined = "\n".join(self.last_lines)
        if error:
            self.status_label.set_text(f"起動に失敗しました: {error}")
            return
        if "Authorization denied" in joined or "Not Authorized" in joined:
            self.status_label.set_text(
                "認証が承認されなかったため操作を中止しました。"
                "パスワードのダイアログで「認証」を選んでください。")
        elif "enroll-completed" in joined:
            self.status_label.set_text("登録が完了しました。")
        elif "verify-match" in joined:
            self.status_label.set_text("照合に成功しました。")
        elif "verify-no-match" in joined:
            self.status_label.set_text("照合に失敗しました（指紋が一致しません）。")
        elif "verify-retry-scan" in joined or "enroll-retry-scan" in joined:
            self.status_label.set_text("読み取りが不十分でした。もう一度スワイプしてください。")
        elif "delete" in " ".join(self.last_lines).lower() and rc == 0:
            self.status_label.set_text("削除しました。")
        elif rc == 0:
            self.status_label.set_text("完了しました。")
        else:
            self.status_label.set_text(f"コマンドが終了コード {rc} で失敗しました。下の出力を確認してください。")

    def _clear_output(self):
        self.output.get_buffer().set_text("")

    def _message(self, text, kind):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=kind,
            buttons=Gtk.ButtonsType.OK, text=text)
        dialog.run()
        dialog.destroy()


if __name__ == "__main__":
    win = FingerprintManager()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    win.cancel_button.hide()
    Gtk.main()
