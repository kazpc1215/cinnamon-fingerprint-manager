import sys


def main() -> int:
    try:
        from .gui import main as gui_main
    except (ImportError, ValueError) as exc:
        if isinstance(exc, ModuleNotFoundError) and not (exc.name or "").startswith("gi"):
            raise
        print(
            "エラー: GTK3 / PyGObject (gi) を読み込めませんでした。\n"
            "  sudo apt install python3-gi gir1.2-gtk-3.0\n"
            "システムの Python 3 で実行してください"
            "（仮想環境には gi が入っていない場合があります）。",
            file=sys.stderr,
        )
        return 1

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
