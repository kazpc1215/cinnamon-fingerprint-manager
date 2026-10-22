"""GUI モジュールの import スモークテスト。

CI で GTK/PyGObject をインストールすると時間がかかるため、``gi`` を軽量な
スタブに差し替えて import 時のエラー（構文・相対 import・名前の誤り）だけを
高速に検出する。実際の GTK 描画はテストしない。
"""

import importlib
import sys
import types


def _fake_repository():
    repository = types.ModuleType("gi.repository")

    class _Window:
        pass

    repository.GLib = types.ModuleType("gi.repository.GLib")
    repository.Gtk = types.SimpleNamespace(Window=_Window)
    repository.Pango = types.ModuleType("gi.repository.Pango")
    return repository


def test_gui_module_imports_without_gtk(monkeypatch):
    repository = _fake_repository()
    fake_gi = types.ModuleType("gi")
    fake_gi.require_version = lambda *_args, **_kwargs: None
    fake_gi.repository = repository

    monkeypatch.setitem(sys.modules, "gi", fake_gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    monkeypatch.delitem(sys.modules, "cinnamon_fingerprint_manager.gui", raising=False)

    module = importlib.import_module("cinnamon_fingerprint_manager.gui")

    assert module.APP_TITLE == "指紋マネージャー"
    assert hasattr(module, "FingerprintManager")
    assert callable(module.main)
