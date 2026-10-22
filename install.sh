#!/usr/bin/env bash
#
# 指紋マネージャーをユーザー領域にインストールします。
#   ./install.sh            アプリメニューに登録
#   ./install.sh --desktop  さらにデスクトップにもアイコンを作成
#
# 実行時はシステムの Python 3 + PyGObject (python3-gi) を使います。
# uv / venv は開発・テスト用で、実行には必要ありません。
#
set -euo pipefail

usage() {
    cat <<'EOF'
使い方: ./install.sh [--desktop]

  --desktop   デスクトップにもアイコンを作成します
  -h, --help  このヘルプを表示します
EOF
}

desktop_icon=false
case ${1:-} in
    "") ;;
    --desktop) desktop_icon=true ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        echo "エラー: 不明な引数です: $1" >&2
        usage >&2
        exit 2
        ;;
esac

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
dest_dir="$data_home/fingerprint-manager"
apps_dir="$data_home/applications"
desktop_file="$apps_dir/fingerprint-manager.desktop"
package_dir="$dest_dir/cinnamon_fingerprint_manager"
icon_dir="$data_home/icons/hicolor/scalable/apps"
icon_file="$icon_dir/fingerprint-manager.svg"

if ! command -v python3 >/dev/null 2>&1; then
    echo "エラー: python3 が見つかりません。" >&2
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "エラー: Python 3.10 以上が必要です。" >&2
    exit 1
fi

if ! command -v fprintd-list >/dev/null 2>&1; then
    echo "エラー: fprintd が見つかりません。先に導入してください:" >&2
    echo "  sudo apt install fprintd libpam-fprintd" >&2
    exit 1
fi

if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null; then
    echo "エラー: GTK3 (python3-gi / gir1.2-gtk-3.0) が見つかりません。" >&2
    echo "  sudo apt install python3-gi gir1.2-gtk-3.0" >&2
    exit 1
fi

install -d "$dest_dir" "$apps_dir" "$icon_dir"

# 途中で失敗しても壊れたパッケージを残さないよう、一時領域に展開してから置き換える
tmp_dir=$(mktemp -d "$dest_dir/.install.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT
cp -r "$script_dir/src/cinnamon_fingerprint_manager" "$tmp_dir/"
find "$tmp_dir" -type d -name __pycache__ -prune -exec rm -rf {} +

rm -rf "$package_dir"
mv "$tmp_dir/cinnamon_fingerprint_manager" "$package_dir"
rm -f "$dest_dir/fingerprint_manager.py"  # 旧バージョンの単一ファイル版

PYTHONPATH="$dest_dir" python3 -c 'import cinnamon_fingerprint_manager' 2>/dev/null || {
    echo "エラー: インストールしたパッケージを読み込めません。" >&2
    exit 1
}

install -m 644 "$script_dir/data/fingerprint-manager.svg" "$icon_file"

# desktop entry の Exec 用に、空白・引用符・% などをエスケープする
quote_exec_arg() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\`/\\\`}
    value=${value//\$/\\\$}
    value=${value//%/%%}
    printf '"%s"' "$value"
}

exec_path=$(quote_exec_arg "$dest_dir")

cat > "$desktop_file" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Fingerprint Manager
Name[ja]=指紋マネージャー
GenericName=Fingerprint Management
GenericName[ja]=指紋の管理
Comment=Enroll, test and delete fingerprints
Comment[ja]=指紋の登録・照合テスト・削除を行います
Exec=env PYTHONPATH=$exec_path python3 -m cinnamon_fingerprint_manager
TryExec=python3
Icon=fingerprint-manager
Terminal=false
Categories=Settings;
Keywords=fingerprint;fprint;biometric;指紋;生体認証;
StartupNotify=true
EOF
chmod 644 "$desktop_file"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$data_home/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "インストールしました:"
echo "  本体     : $package_dir"
echo "  メニュー : $desktop_file"
echo "  アイコン : $icon_file"

if [[ $desktop_icon == true ]]; then
    desk_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
    [[ -n $desk_dir ]] || desk_dir="$HOME/Desktop"
    mkdir -p "$desk_dir"
    icon="$desk_dir/指紋マネージャー.desktop"
    cp "$desktop_file" "$icon"
    chmod +x "$icon"
    if command -v gio >/dev/null 2>&1; then
        gio set "$icon" metadata::trusted true >/dev/null 2>&1 || true
    fi
    echo "  デスクトップ: $icon"
fi

echo
echo "アプリメニューで「指紋」と検索するか、次のコマンドで起動できます:"
echo "  gtk-launch fingerprint-manager"
