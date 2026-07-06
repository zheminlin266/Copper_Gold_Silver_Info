#!/usr/bin/env python3
"""
report_builder.py — Generate weekly trend summary from daily JSON data files.

Reads data/YYYY-MM-DD.json files for the past 7 days and produces:
  - Weekly_Reports/YYYY-WW.md (markdown summary)
  - data/weekly/YYYY-WW.json (structured weekly data)

Usage:
  python scripts/report_builder.py --week 2026-W27
  python scripts/report_builder.py  # defaults to last completed week

Dependencies:
  pip install jinja2  (optional, for HTML rendering)
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))


def get_week_range(year, week_num):
    """Get the date range (Monday-Sunday) for a given ISO week."""
    # ISO week: Monday is day 1
    monday = datetime.fromisocalendar(year, week_num, 1).date()
    sunday = monday + timedelta(days=6)
    return monday, sunday


def load_daily_jsons(data_dir, start_date, end_date):
    """Load all daily JSON files in the date range."""
    daily_data = []
    current = start_date
    while current <= end_date:
        json_file = data_dir / f"{current}.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    daily_data.append(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load {json_file}: {e}", file=sys.stderr)
        else:
            print(f"Info: No data file for {current}", file=sys.stderr)
        current += timedelta(days=1)
    return daily_data


def aggregate_stats(daily_data):
    """Aggregate statistics from daily JSON files."""
    stats = {
        "total_broadcasts": 0,
        "total_x_posts": 0,
        "total_news": 0,
        "total_news_en": 0,
        "total_news_zh": 0,
        "metal_counts": Counter(),
        "supply_demand_counts": Counter(),
        "top_companies": Counter(),
        "top_sources": Counter(),
        "top_guests": [],
        "part2_success_days": 0,
        "part2_total_days": 0,
        "part1_success_days": 0,
        "part1_total_days": 0,
        "all_events": [],
    }

    for day in daily_data:
        date = day.get("date", "unknown")
        search_log = day.get("search_log", {})

        # Part 1 stats
        broadcasts = day.get("part1_broadcasts", [])
        stats["part1_total_days"] += 1
        if broadcasts:
            stats["part1_success_days"] += 1
        stats["total_broadcasts"] += len(broadcasts)

        for b in broadcasts:
            for m in b.get("metal_tags", []):
                stats["metal_counts"][m] += 1
            stats["supply_demand_counts"][b.get("supply_demand", "unknown")] += 1
            for c in b.get("companies", []):
                stats["top_companies"][c] += 1
            if b.get("guest", {}).get("name"):
                stats["top_guests"].append({
                    "name": b["guest"]["name"],
                    "date": date,
                    "title": b.get("title", ""),
                    "url": b.get("url", ""),
                })
            stats["all_events"].append({
                "date": date,
                "type": "broadcast",
                "title": b.get("title", ""),
                "metals": b.get("metal_tags", []),
                "supply_demand": b.get("supply_demand", ""),
                "url": b.get("url", ""),
            })

        # Part 2 stats
        x_posts = day.get("part2_x_posts", [])
        stats["part2_total_days"] += 1
        if search_log.get("part2_channel") != "failed":
            stats["part2_success_days"] += 1
        stats["total_x_posts"] += len(x_posts)

        for x in x_posts:
            for m in x.get("metal_tags", []):
                stats["metal_counts"][m] += 1
            stats["supply_demand_counts"][x.get("supply_demand", "unknown")] += 1
            stats["all_events"].append({
                "date": date,
                "type": "x_post",
                "author": x.get("author", ""),
                "metals": x.get("metal_tags", []),
                "supply_demand": x.get("supply_demand", ""),
                "url": x.get("url", ""),
            })

        # Part 3 stats
        news = day.get("part3_news", [])
        for n in news:
            lang = n.get("language", "en")
            if lang == "en":
                stats["total_news_en"] += 1
            else:
                stats["total_news_zh"] += 1
            stats["top_sources"][n.get("source", "unknown")] += 1
            for m in n.get("metal_tags", []):
                stats["metal_counts"][m] += 1
            stats["supply_demand_counts"][n.get("supply_demand", "unknown")] += 1
            stats["all_events"].append({
                "date": date,
                "type": "news",
                "title": n.get("title", ""),
                "source": n.get("source", ""),
                "metals": n.get("metal_tags", []),
                "supply_demand": n.get("supply_demand", ""),
                "language": lang,
                "url": n.get("url", ""),
            })

    stats["total_news"] = stats["total_news_en"] + stats["total_news_zh"]
    return stats


def generate_markdown(stats, year, week_num, start_date, end_date):
    """Generate markdown weekly report."""
    lines = []
    lines.append(f"# {year}-W{week_num:02d} 周度趋势简报\n")
    lines.append(f"覆盖周期：{start_date} 至 {end_date}（北京时间）\n")

    lines.append("## 概览\n")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 广播/访谈 | {stats['total_broadcasts']} |")
    lines.append(f"| X 原帖 | {stats['total_x_posts']} |")
    lines.append(f"| 新闻（英文） | {stats['total_news_en']} |")
    lines.append(f"| 新闻（中文） | {stats['total_news_zh']} |")
    lines.append(f"| 新闻合计 | {stats['total_news']} |")
    lines.append(f"| 总信号数 | {stats['total_broadcasts'] + stats['total_x_posts'] + stats['total_news']} |")
    lines.append("")

    # Part 1 availability
    if stats["part1_total_days"] > 0:
        p1_rate = stats["part1_success_days"] / stats["part1_total_days"] * 100
        lines.append(f"Part 1 访谈覆盖天数：{stats['part1_success_days']}/{stats['part1_total_days']} ({p1_rate:.0f}%)")
    if stats["part2_total_days"] > 0:
        p2_rate = stats["part2_success_days"] / stats["part2_total_days"] * 100
        lines.append(f"Part 2 X 采集可用天数：{stats['part2_success_days']}/{stats['part2_total_days']} ({p2_rate:.0f}%)")
    lines.append("")

    lines.append("## 金属分布\n")
    lines.append("| 金属 | 信号数 |")
    lines.append("|------|--------|")
    for metal, count in stats["metal_counts"].most_common():
        metal_cn = {"gold": "金", "silver": "银", "copper": "铜"}.get(metal, metal)
        lines.append(f"| {metal_cn} ({metal}) | {count} |")
    lines.append("")

    lines.append("## 供给/需求分布\n")
    lines.append("| 方向 | 信号数 |")
    lines.append("|------|--------|")
    for sd, count in stats["supply_demand_counts"].most_common():
        sd_cn = {"supply": "供给", "demand": "需求", "both": "双向"}.get(sd, sd)
        lines.append(f"| {sd_cn} ({sd}) | {count} |")
    lines.append("")

    lines.append("## 主要新闻来源\n")
    lines.append("| 来源 | 条数 |")
    lines.append("|------|------|")
    for source, count in stats["top_sources"].most_common(10):
        lines.append(f"| {source} | {count} |")
    lines.append("")

    lines.append("## 涉及公司\n")
    lines.append("| 公司 | 出现次数 |")
    lines.append("|------|----------|")
    for company, count in stats["top_companies"].most_common(10):
        lines.append(f"| {company} | {count} |")
    lines.append("")

    # Top events
    lines.append("## 本周所有信号事件\n")
    for event in stats["all_events"]:
        date = event.get("date", "")
        etype = event.get("type", "")
        title = event.get("title", event.get("author", ""))
        metals = ", ".join(event.get("metals", []))
        sd = event.get("supply_demand", "")
        url = event.get("url", "")
        lines.append(f"- [{date}] ({etype}) {title} [{metals}] [{sd}]")
        if url:
            lines.append(f"  {url}")
    lines.append("")

    lines.append("---")
    lines.append("Generated by scripts/report_builder.py")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly trend report from daily JSON data")
    parser.add_argument("--week", type=str, help="ISO week (e.g., 2026-W27)")
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    script_dir = Path(__file__).parent.parent
    data_dir = script_dir / "data"

    if args.week:
        year_str, week_str = args.week.split("-W")
        year, week_num = int(year_str), int(week_str)
    else:
        now = datetime.now(BEIJING_TZ)
        iso_cal = now.isocalendar()
        # Use last completed week
        year, week_num = iso_cal[0], iso_cal[1] - 1
        if week_num == 0:
            year -= 1
            week_num = 52

    start_date, end_date = get_week_range(year, week_num)
    print(f"Generating weekly report for {year}-W{week_num:02d} ({start_date} to {end_date})...")

    daily_data = load_daily_jsons(data_dir, start_date, end_date)

    if not daily_data:
        print("No daily JSON data files found for this week.", file=sys.stderr)
        print("Daily JSON output must be enabled first.", file=sys.stderr)
        sys.exit(0)

    stats = aggregate_stats(daily_data)

    # Generate markdown
    markdown = generate_markdown(stats, year, week_num, start_date, end_date)

    # Output directories
    weekly_md_dir = script_dir / "Weekly_Reports"
    weekly_json_dir = data_dir / "weekly"
    weekly_md_dir.mkdir(parents=True, exist_ok=True)
    weekly_json_dir.mkdir(parents=True, exist_ok=True)

    md_file = weekly_md_dir / f"{year}-W{week_num:02d}.md"
    json_file = weekly_json_dir / f"{year}-W{week_num:02d}.json"

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(markdown)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "year": year,
            "week": week_num,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "stats": dict(stats),
        }, f, ensure_ascii=False, indent=2, default=str)

    print(f"\nMarkdown: {md_file}")
    print(f"JSON: {json_file}")
    print(f"Total signals this week: {stats['total_broadcasts'] + stats['total_x_posts'] + stats['total_news']}")


if __name__ == "__main__":
    main()
