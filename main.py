from __future__ import annotations

# 软件启动入口（TTCAS）
# 说明：
# - 本工程采用 src/ 目录布局
# - 直接运行本文件时，需要把 src 加入 sys.path

import sys
from pathlib import Path


def _ensure_src_on_path() -> Path:
    # 如果是 PyInstaller 打包后的单文件，使用 _MEIPASS 作为根目录
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        repo_root = Path(sys._MEIPASS)
        # 确保 _MEIPASS 在 sys.path 中（PyInstaller 可能已经添加，但为了保险）
        sys.path.insert(0, str(repo_root))
        return repo_root
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    sys.path.insert(0, str(src_dir))
    return repo_root


def main() -> int:
    repo_root = _ensure_src_on_path()

    from ttcas_app.app import run

    return run(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
