from __future__ import annotations

import pathlib
import sys


def main() -> None:
    try:
        import PyInstaller.__main__
    except ImportError:  # pragma: no cover - runtime guard
        print("PyInstaller 未安装，请先运行 pip install pyinstaller", file=sys.stderr)
        sys.exit(1)

    project_root = pathlib.Path(__file__).resolve().parent
    PyInstaller.__main__.run(
        [
            str(project_root / "file_manager.py"),
            "--name",
            "file_manager",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--noconsole",
            "--distpath",
            str(project_root / "dist"),
            "--workpath",
            str(project_root / "build"),
            "--specpath",
            str(project_root / "build"),
            "--icon",
            str(project_root / "icon.ico"),
        ]
    )


if __name__ == "__main__":
    main()
