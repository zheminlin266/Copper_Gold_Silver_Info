#!/usr/bin/env python3
"""批量把 7 篇日报页的 <style> 替换成对 ../assets/report.css + report-detail.css 的引用。
不动 body 任何内容。"""
import re
from pathlib import Path

REPORTS_DIR = Path("D:/Projects/Copper_Gold_Silver_Info/Historical_Daily_Reports")

# 匹配 <style>...</style> 整个块
STYLE_BLOCK = re.compile(r"<style>.*?</style>", re.DOTALL)

NEW_HEAD_LINKS = '''<link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/report.css">
  <link rel="stylesheet" href="../assets/report-detail.css">'''

def transform(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "../assets/report-detail.css" in text:
        return False  # already done
    new_text, n = STYLE_BLOCK.subn(NEW_HEAD_LINKS, text)
    if n == 0:
        print(f"  ! no <style> in {path.name}")
        return False
    path.write_text(new_text, encoding="utf-8")
    return True

if __name__ == "__main__":
    files = sorted(REPORTS_DIR.glob("*.html"))
    for f in files:
        ok = transform(f)
        print(f"{'OK ' if ok else 'skip'} {f.name}")
