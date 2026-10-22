# Contributing

コントリビュートを歓迎します。バグ報告・機能提案は
[Issues](https://github.com/kazpc1215/cinnamon-fingerprint-manager/issues) へお願いします。

## 開発環境

Linux Mint / Ubuntu では、システム側に次が必要です。

```bash
sudo apt install fprintd libpam-fprintd python3-gi gir1.2-gtk-3.0
```

Python の開発環境は [uv](https://docs.astral.sh/uv/) で管理しています。

```bash
uv sync
```

## チェック

コミット前に以下を実行してください。

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

`pytest` は venv に `gi` がない場合、GUI テストを自動的にスキップします。
GUI テストまで実行する場合は、システムの PyGObject を使える Python で実行します。

```bash
# Xvfb を使う場合
xvfb-run -a env PYTHONPATH=src python3 -m pytest -q tests/

# 実際の画面を使う場合
DISPLAY=:0 env PYTHONPATH=src python3 -m pytest -q tests/
```

GUI テストは一時的な fake `fprintd-list` / `fprintd-enroll` / `fprintd-verify` を
PATH の先頭に置くため、実機のセンサーには依存しません。

インストーラを変更した場合は、ShellCheck と desktop entry の検証も行ってください。

```bash
shellcheck install.sh uninstall.sh
XDG_DATA_HOME=/tmp/fingerprint-manager-test ./install.sh
desktop-file-validate /tmp/fingerprint-manager-test/applications/fingerprint-manager.desktop
XDG_DATA_HOME=/tmp/fingerprint-manager-test ./uninstall.sh
```

## コード構成

- `src/cinnamon_fingerprint_manager/core.py` — GTK に依存しない解析・コマンド組み立て・結果判定
- `src/cinnamon_fingerprint_manager/gui.py` — GTK3 の画面と非同期実行
- `tests/test_core.py` — core の単体テスト
- `tests/test_gui.py` — fake fprintd を使った GUI テスト
- `tests/gui_smoke.py` — Xvfb 上で画面を組み立てるスモークテスト

## 方針

- UI の文言は日本語を基本とします。翻訳を追加する場合は、文字列を一箇所に集約する
  リファクタリングと合わせて提案してください。
- ボタンや入力欄を追加するときは、ラベルに加えてツールチップやアクセシブル名も
  設定してください。
- fprintd の出力に依存する処理は、実機の出力例をテストに追加してください。
- 既存のコードスタイル（Ruff、100 文字、型ヒント）に合わせてください。

## コミット

1 つの変更を 1 つのコミットにまとめ、何を・なぜ変更したかが分かるメッセージを
書いてください。日本語の UI 文言とコメントはそのまま維持します。
