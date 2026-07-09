"""
Generate a mining news thumbnail image for a daily report.

Usage:
  python scripts/generate_thumbnail.py "2026-07-10" "Kamoa-Kakula copper mine Q3 production record"

This generates Sources/mining_2026-07-10_{slug}.png and outputs the filename.
Update index.html to use it as the report thumbnail.

Requirements: ImageGen is available as a deferred tool if run inside WorkBuddy.
For automated runs (GitHub Actions), this step is replaced by a placeholder
that prompts the operator to run this manually or via an API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Generate mining news thumbnail")
    parser.add_argument("date", help="Date in YYYY-MM-DD format")
    parser.add_argument("description", nargs="+", help="Brief description for the image prompt")
    parser.add_argument("--output-dir", default=None, help="Output directory for the image")
    args = parser.parse_args()

    date = args.date
    description = " ".join(args.description)
    slug = description.lower().replace(" ", "_").replace(",", "")[:40]
    filename = f"mining_{date}_{slug}.png"

    output_dir = Path(args.output_dir) if args.output_dir else Path("Sources")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[thumbnail] Date: {date}")
    print(f"[thumbnail] Description: {description}")
    print(f"[thumbnail] Target: {output_dir / filename}")
    print()
    print("TODO: Generate image via ImageGen with prompt:")
    print(f'  "Mining industry photograph: {description}, photorealistic, high quality"')
    print()
    print("Then update index.html:")
    print(f'  <div class="thumb"><img src="./Sources/{filename}" alt="{description}"></div>')
    print()
    print("STEPS for WorkBuddy:")
    print(f"  1. ImageGen(prompt='Mining photograph: {description}')")
    print(f"  2. Rename output → Sources/{filename}")
    print(f"  3. Update index.html report-row <img> src")
    print(f"  4. git add Sources/{filename} index.html && git commit && git push")


if __name__ == "__main__":
    main()
