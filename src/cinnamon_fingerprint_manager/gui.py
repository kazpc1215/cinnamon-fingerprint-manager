"""GTK3 front-end for fprintd."""

from __future__ import annotations

import contextlib
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .core import (  # noqa: E402
    available_fingers,
    build_delete_command,
    build_enroll_command,
    build_list_command,
    build_verify_command,
    classify_result,
    current_user,
    device_title,
    finger_label,
    parse_list_output,
)

APP_TITLE = "指紋マネージャー"

USER = current_user()


class FingerprintManager(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_TITLE)
        self.set_default_size(560, 560)
        self.proc = None
        self.last_lines: list[str] = []
        self.current_action: str | None = None
        self.cancelled = False

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
        out_frame.set_no_show_all(True)
        out_frame.hide()
        self.out_frame = out_frame
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
                build_list_command(USER),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._set_device_error(str(exc))
            return

        parsed = parse_list_output(result.stdout + result.stderr)

        for row in self.listbox.get_children():
            self.listbox.remove(row)

        if not parsed.found:
            self._set_device_error("指紋センサーが見つかりません")
            return

        self.device_label.set_text(device_title(parsed.device, parsed.scan_type))
        self.count_label.set_text(f"登録済み: {len(parsed.fingers)} 本")

        if not parsed.fingers:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label="まだ指紋が登録されていません。「指を追加」から登録できます。")
            label.set_margin_top(16)
            label.set_margin_bottom(16)
            label.get_style_context().add_class("dim-label")
            row.add(label)
            self.listbox.add(row)

        for name in parsed.fingers:
            self.listbox.add(self._make_row(name))

        self.listbox.show_all()
        self.cancel_button.hide()

    def _set_device_error(self, message):
        self.device_label.set_text(message)
        self.count_label.set_text("")
        for row in self.listbox.get_children():
            self.listbox.remove(row)
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=message)
        label.set_margin_top(16)
        label.set_margin_bottom(16)
        row.add(label)
        self.listbox.add(row)
        self.listbox.show_all()

    def _make_row(self, finger):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_border_width(8)

        icon = Gtk.Image.new_from_icon_name("dialog-password", Gtk.IconSize.BUTTON)
        box.pack_start(icon, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label(label=finger_label(finger), xalign=0)
        subtitle = Gtk.Label(label=finger, xalign=0)
        subtitle.get_style_context().add_class("dim-label")
        text.pack_start(title, False, False, 0)
        text.pack_start(subtitle, False, False, 0)
        box.pack_start(text, True, True, 0)

        verify = Gtk.Button(label="テスト")
        verify.connect(
            "clicked",
            lambda *_: self.run_command(build_verify_command(finger), "照合テスト", "verify"),
        )
        delete = Gtk.Button(label="削除")
        delete.get_style_context().add_class("destructive-action")
        delete.connect("clicked", lambda *_: self.on_delete_clicked(finger, title.get_text()))
        box.pack_end(delete, False, False, 0)
        box.pack_end(verify, False, False, 0)

        row.add(box)
        return row

    # ---------- 操作 ----------
    def on_add_clicked(self, _button):
        parsed = parse_list_output(self._get_list_text())
        candidates = available_fingers(parsed.fingers)
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
                build_enroll_command(finger),
                f"「{finger_label(finger)}」を登録",
                "enroll",
            )

    def on_delete_clicked(self, finger, label):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
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
                build_delete_command(finger, USER),
                f"「{label}」を削除",
                "delete",
            )

    def on_cancel_clicked(self, _button):
        if self.proc and self.proc.poll() is None:
            self.cancelled = True
            self.status_label.set_text("中止しています…")
            proc = self.proc
            try:
                proc.terminate()
            except ProcessLookupError:
                return
            # fprintd が SIGTERM を無視した場合に備えて、少し待ってから強制終了する
            GLib.timeout_add(2000, self._kill_if_running, proc)

    @staticmethod
    def _kill_if_running(proc):
        if proc.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        return False

    def on_destroy(self, _widget):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        if Gtk.main_level() > 0:
            Gtk.main_quit()

    # ---------- コマンド実行 ----------
    @staticmethod
    def _get_list_text():
        try:
            result = subprocess.run(
                build_list_command(USER), capture_output=True, text=True, timeout=15
            )
            return result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def run_command(self, args, description, action=None):
        if self.proc and self.proc.poll() is None:
            return
        self.last_lines = []
        self.current_action = action
        self.cancelled = False
        self._clear_output()
        self.out_frame.set_no_show_all(False)
        self.out_frame.show_all()
        self.status_label.set_text(f"{description} を開始しました…")
        self.add_button.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.cancel_button.show()
        self.cancel_button.set_sensitive(True)
        for row in self.listbox.get_children():
            row.set_sensitive(False)

        try:
            self.proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._finish(-1, str(exc))
            return

        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            GLib.idle_add(self._append_line, line.rstrip("\n"))
        returncode = proc.wait()
        GLib.idle_add(self._finish, returncode, None)

    def _append_line(self, line):
        self.last_lines.append(line)
        buffer = self.output.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + "\n")
        self.output.scroll_to_iter(buffer.get_end_iter(), 0.0, False, 0.0, 0.0)
        return False

    def _finish(self, returncode, error):
        self.proc = None
        self.cancel_button.hide()
        self.add_button.set_sensitive(True)
        self.refresh_button.set_sensitive(True)
        self.refresh()

        if error:
            self.status_label.set_text(f"起動に失敗しました: {error}")
            return

        if self.cancelled:
            self.cancelled = False
            self.status_label.set_text("中止しました。")
            return

        result = classify_result(self.last_lines, returncode, self.current_action)
        self.status_label.set_text(result.message)

    def _clear_output(self):
        self.output.get_buffer().set_text("")

    def _message(self, text, kind):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=kind,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )
        dialog.run()
        dialog.destroy()


def main():
    win = FingerprintManager()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    win.cancel_button.hide()
    Gtk.main()
