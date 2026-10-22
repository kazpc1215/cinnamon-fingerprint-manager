# トラブルシューティング

## 指紋センサーが見つからない

まず fprintd がセンサーを認識しているか確認します。

```bash
fprintd-list "$USER"
```

`No devices available` と出る場合は、fprintd / libfprint とセンサーの対応状況を
確認してください。

```bash
sudo apt install fprintd libpam-fprintd
systemctl status fprintd
```

USB センサーの場合は、接続し直すか、次のコマンドで認識を確認できます。

```bash
lsusb
```

## 「指紋センサーは他のアプリで使用中です」と表示される

fprintd は 1 つのデバイスを排他的に使用します。他の指紋アプリ、設定画面、
ログイン画面の指紋認証などがセンサーを掴んでいる可能性があります。それらを
閉じてから「更新」を押してください。

## パスワードのダイアログが出ない

登録・削除には polkit エージェントが必要です。Cinnamon では通常
`cinnamon-polkit-agent` が動作しています。次のコマンドで確認できます。

```bash
ps aux | grep -i polkit
```

リモートログインや最小構成のデスクトップでは、polkit エージェントが起動して
いないことがあります。

## GTK3 / PyGObject を読み込めない

仮想環境（venv / pipx / uv tool）から起動すると、システムの `gi` を参照できず
次のようなメッセージが出ることがあります。

```
エラー: GTK3 / PyGObject (gi) を読み込めませんでした。
```

システムパッケージを導入し、システムの Python で実行してください。

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
./install.sh
```

pip で入れる場合は `python3 -m venv --system-site-packages` を使うか、システム
Python の環境にインストールしてください。

## 画面が固まった / 処理を中止したい

登録・照合・削除の実行中は「中止」ボタンが表示されます。中止後も fprintd が
応答しない場合は、数秒後に強制終了されます。ウィンドウを閉じる場合も、実行中
なら確認ダイアログが表示されます。

## ログを確認する

`CFM_DEBUG=1` を設定すると、fprintd の実行や失敗の詳細を標準エラーに出力します。

```bash
CFM_DEBUG=1 gtk-launch fingerprint-manager
```

メニューから起動した場合は標準エラーが見えないため、ターミナルから直接実行すると
確認しやすいです。

```bash
CFM_DEBUG=1 PYTHONPATH="$HOME/.local/share/fingerprint-manager" \
  python3 -m cinnamon_fingerprint_manager
```

## 登録した指紋をすべて削除したい

アプリの「削除」を使うか、ターミナルから削除できます。

```bash
fprintd-delete "$USER"
```

## 指紋認証を PAM から無効にしたい

```bash
sudo pam-auth-update --disable fprintd
```

## インストールをやり直したい

```bash
./uninstall.sh
./install.sh
```

`uninstall.sh` は登録済みの指紋データを削除しません。
