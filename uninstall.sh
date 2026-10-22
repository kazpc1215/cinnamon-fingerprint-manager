#!/usr/bin/env bash
#
# 指紋マネージャーを削除します。登録済みの指紋データには触れません。
#
set -euo pipefail

data_home=${XDG_DATA_HOME:-$HOME/.local/share}
dest_dir="$data_home/fingerprint-manager"
apps_dir="$data_home/applications"
icon_file="$data_home/icons/hicolor/scalable/apps/fingerprint-manager.svg"

rm -f "$apps_dir/fingerprint-manager.desktop"
rm -f "$icon_file"
rm -rf "$dest_dir"

desk_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
[[ -n $desk_dir ]] || desk_dir="$HOME/Desktop"
rm -f "$desk_dir/指紋マネージャー.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$data_home/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "アンインストールしました。"
echo "登録済みの指紋は削除していません。削除する場合: fprintd-delete \"\$USER\""
