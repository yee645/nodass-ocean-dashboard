"""把 Python 管線產物（JSON）複製到 web/public/data，供 React 前端 fetch。

重構後 React 端不再內嵌資料，改 fetch 靜態 JSON。請在 build_*.py 跑完後執行本腳本
（或併入 setup.sh / live_update.py 末端），確保 web 前端取得最新資料。
"""
from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEST = BASE / "web" / "public" / "data"

# (來源相對路徑, 目的檔名)
ASSETS = [
    ("sdm/forecast_grid.json", "forecast_grid.json"),
    ("sdm/hires_grid.json", "hires_grid.json"),
    ("sdm/fishing_grid.json", "fishing_grid.json"),
    ("region_coast.json", "region_coast.json"),
    ("sdm/ports.json", "ports.json"),                 # 第二層航線起點(漁港)
    ("sdm/occurrences_web.json", "occurrences_web.json"),  # 第一層 KDE 用出現點
]


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for src_rel, name in ASSETS:
        src = BASE / src_rel
        if not src.exists():
            print(f"  跳過(不存在)：{src_rel}")
            continue
        shutil.copy2(src, DEST / name)
        kb = (DEST / name).stat().st_size / 1024
        print(f"  複製 {src_rel} -> web/public/data/{name}（{kb:.0f} KB）")
    print(f"完成：{DEST}")


if __name__ == "__main__":
    main()
