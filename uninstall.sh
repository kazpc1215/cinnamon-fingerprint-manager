#!/usr/bin/env bash
#
# 指紋マネージャーを削除します。登録済みの指紋データには触れません。
#
set -euo pipefail

data_home=${XDG_DATA_HOME:-$HOME/.local/share}
dest_dir="$data_home/fingerprint-manager"
apps_dir="$data_home/applications"

rm -f "$apps_dir/fingerprint-manager.desktop"
rm -rf "$dest_dir"

desk_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
if [[ -n $desk_dir ]]; then
    rm -f "$desk_dir/指紋マネージャー.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
fi

echo "アンインストールしました。"
echo "登録済みの指紋は削除していません。削除する場合: fprintd-delete \"\$USER\""
