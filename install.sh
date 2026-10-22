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

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
dest_dir="$data_home/fingerprint-manager"
apps_dir="$data_home/applications"
desktop_file="$apps_dir/fingerprint-manager.desktop"
package_dir="$dest_dir/cinnamon_fingerprint_manager"

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

install -d "$dest_dir"
rm -rf "$package_dir"
cp -r "$script_dir/src/cinnamon_fingerprint_manager" "$package_dir"
find "$dest_dir" -type d -name __pycache__ -prune -exec rm -rf {} +
rm -f "$dest_dir/fingerprint_manager.py"  # 旧バージョンの単一ファイル版

PYTHONPATH="$dest_dir" python3 -c 'import cinnamon_fingerprint_manager' 2>/dev/null || {
    echo "エラー: インストールしたパッケージを読み込めません。" >&2
    exit 1
}

mkdir -p "$apps_dir"
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
Exec=env PYTHONPATH=$dest_dir python3 -m cinnamon_fingerprint_manager
Icon=dialog-password
Terminal=false
Categories=Settings;
Keywords=fingerprint;fprint;biometric;指紋;生体認証;
StartupNotify=true
EOF
chmod 644 "$desktop_file"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
fi

echo "インストールしました:"
echo "  本体     : $package_dir"
echo "  メニュー : $desktop_file"

if [[ ${1:-} == "--desktop" ]]; then
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
