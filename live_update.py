"""即時更新：重抓最新浮標資料、累積歷史、重建兩個儀表板頁面。

可手動執行，或用 Windows 工作排程器定時呼叫（搭配頁面自動重整即為準即時）：
    python live_update.py
建議排程：每小時執行一次（浮標為逐時資料）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(r"D:\nodass")
STEPS = ["fetch_buoys.py", "accumulate_history.py", "build_dashboard.py", "build_fishing.py"]


def main() -> None:
    for script in STEPS:
        path = DATA_DIR / script
        print(f"== 執行 {script} ==")
        result = subprocess.run([sys.executable, str(path)], cwd=str(DATA_DIR))
        if result.returncode != 0:
            print(f"!! {script} 失敗（return code {result.returncode}），中止。")
            return
    print("== 完成：兩個儀表板已更新 ==")


if __name__ == "__main__":
    main()
