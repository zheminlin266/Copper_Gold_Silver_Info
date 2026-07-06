#!/usr/bin/env python3
"""
rss_fetcher.py — Fetch and filter RSS feeds for gold, silver, copper supply-demand news.

Sources:
  English: Reuters Commodities, Mining.com (Copper/Gold/Silver sections)
  Chinese:  SMM (smm.cn), SHMET (shmet.com)

Output:
  data/raw/YYYY-MM-DD_rss.json

Usage:
  python scripts/rss_fetcher.py --date 2026-07-05
  python scripts/rss_fetcher.py  # defaults to yesterday (Beijing time)

Dependencies:
  pip install feedparser requests
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import feedparser
except ImportError:
    print("Error: feedparser not installed. Run: pip install feedparser", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


BEIJING_TZ = timezone(timedelta(hours=8))

# --- Feed sources ---

FEEDS_EN = [
    {
        "name": "Reuters Commodities",
        "url": "https://www.reuters.com/markets/commodities/rss",
        "language": "en",
        "default_metals": [],
    },
    {
        "name": "Mining.com Copper",
        "url": "https://www.mining.com/category/copper/feed/",
        "language": "en",
        "default_metals": ["copper"],
    },
    {
        "name": "Mining.com Gold",
        "url": "https://www.mining.com/category/gold/feed/",
        "language": "en",
        "default_metals": ["gold"],
    },
    {
        "name": "Mining.com Silver",
        "url": "https://www.mining.com/category/silver/feed/",
        "language": "en",
        "default_metals": ["silver"],
    },
]

FEEDS_ZH = [
    {
        "name": "SMM 有色网-铜",
        "url": "https://www.smm.cn/rss/copper.xml",
        "language": "zh",
        "default_metals": ["copper"],
    },
    {
        "name": "SMM 有色网-贵金属",
        "url": "https://www.smm.cn/rss/precious.xml",
        "language": "zh",
        "default_metals": ["gold", "silver"],
    },
    {
        "name": "SHMET 上海有色网-铜",
        "url": "https://www.shmet.com/rss/copper.xml",
        "language": "zh",
        "default_metals": ["copper"],
    },
]

# --- Keywords for supply-demand relevance filtering ---

KEYWORDS_EN = [
    # Supply
    "production", "output", "mine", "mining", "smelter", "refinery", "refining",
    "mill", "processing", "permit", "licens", "approval", "expansion", "expand",
    "restart", "ramp-up", "commission", "grade", "ore", "reserv", "resource",
    "exploration", "drill", "feasibility", "PEA", "preliminary economic",
    "capital expenditure", "capex", "project", "construction", "development",
    "supply", "inventor", "stockpile", "LME", "COMEX", "deliver", "warehouse",
    "TC", "RC", "treatment charge", "refining charge",
    # Demand
    "demand", "consumption", "ETF", "central bank", "retail", "industrial",
    "solar", "photovoltaic", "PV", "electric vehicle", "EV", "grid",
    "investment demand", "physical", "bar", "coin",
    # Disruption
    "strike", "force majeure", "suspension", "halt", "shutdown", "outage",
    "geotechnical", "slope", "water", "drought", "tailings",
]

KEYWORDS_ZH = [
    # Supply
    "产量", "产能", "矿山", "冶炼", "精炼", "加工", "选矿", "球磨",
    "许可", "审批", "环评", "扩产", "扩建", "复产", "重启", "投产",
    "爬产", "达产", "品位", "矿石", "储量", "资源量",
    "勘探", "钻探", "可研", "预可研", "资本开支",
    "项目", "建设", "开发", "供给", "库存", "交割", "仓单",
    "加工费", "TC", "RC",
    # Demand
    "需求", "消费", "ETF", "央行", "零售", "工业",
    "光伏", "太阳能", "新能源车", "电动汽车", "电网",
    "投资需求", "实物", "金条", "金币",
    # Disruption
    "罢工", "停产", "停工", "中断", "事故", "安全检查", "整顿",
    "滑坡", "尾矿", "水源", "干旱",
]

METAL_PATTERNS = {
    "gold": [r"\bgold\b", r"\b金的?\b", r"\b黄金\b", r"\bAu\b"],
    "silver": [r"\bsilver\b", r"\b银的?\b", r"\b白银\b", r"\bAg\b"],
    "copper": [r"\bcopper\b", r"\b铜的?\b", r"\b紫铜\b", r"\bCu\b"],
}


def parse_date(entry):
    """Parse entry date from feedparser entry, return Beijing time datetime."""
    for field in ("published_parsed", "updated_parsed"):
        dt_struct = entry.get(field)
        if dt_struct:
            try:
                dt = datetime(*dt_struct[:6], tzinfo=timezone.utc)
                return dt.astimezone(BEIJING_TZ)
            except Exception:
                continue
    return None


def match_metals(text):
    """Detect which metals are mentioned in the text."""
    metals = []
    text_lower = text.lower()
    for metal, patterns in METAL_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower, re.IGNORECASE):
                metals.append(metal)
                break
    return metals


def is_supply_demand_relevant(text, language="en"):
    """Check if text contains supply-demand keywords."""
    keywords = KEYWORDS_EN if language == "en" else KEYWORDS_ZH
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def classify_supply_demand(text):
    """Classify as 'supply', 'demand', or 'both'."""
    text_lower = text.lower()
    supply_kw = ["production", "output", "mine", "supply", "smelter", "permit",
                 "expansion", "restart", "ramp-up", "grade", "reserv", "exploration",
                 "drill", "feasibility", "capex", "project", "construction",
                 "inventor", "stockpile", "LME", "TC", "RC",
                 "产量", "产能", "矿山", "冶炼", "供给", "库存", "扩产", "投产",
                 "勘探", "钻探", "加工费", "停产", "复产"]
    demand_kw = ["demand", "consumption", "ETF", "central bank", "industrial",
                 "solar", "EV", "grid", "investment demand", "physical", "coin",
                 "需求", "消费", "央行", "工业", "光伏", "新能源车", "投资需求", "实物"]

    has_supply = any(kw.lower() in text_lower for kw in supply_kw)
    has_demand = any(kw.lower() in text_lower for kw in demand_kw)

    if has_supply and has_demand:
        return "both"
    elif has_supply:
        return "supply"
    elif has_demand:
        return "demand"
    return "supply"


def fetch_feed(feed_config, target_date):
    """Fetch a single RSS feed and filter entries for target date."""
    results = []
    try:
        resp = requests.get(feed_config["url"], timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MiningReportBot/1.0)"
        })
        if resp.status_code != 200:
            print(f"  [{feed_config['name']}] HTTP {resp.status_code}", file=sys.stderr)
            return results

        feed = feedparser.parse(resp.content)

        for entry in feed.entries:
            pub_date = parse_date(entry)
            if pub_date is None:
                continue

            # Check if entry falls within the target date (Beijing time)
            if pub_date.date() != target_date:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            full_text = f"{title} {summary}"

            # Filter: must mention at least one metal
            metals = match_metals(full_text)
            if not metals and feed_config["default_metals"]:
                metals = feed_config["default_metals"]

            if not metals:
                continue

            # Filter: must be supply-demand relevant
            if not is_supply_demand_relevant(full_text, feed_config["language"]):
                continue

            sd_type = classify_supply_demand(full_text)

            results.append({
                "source": feed_config["name"],
                "title": title,
                "url": link,
                "publish_time": pub_date.isoformat(),
                "metal_tags": list(set(metals)),
                "supply_demand": sd_type,
                "excerpt": summary[:300] if summary else "",
                "language": feed_config["language"],
                "duplicate_of": None,
            })

    except requests.RequestException as e:
        print(f"  [{feed_config['name']}] Request error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"  [{feed_config['name']}] Parse error: {e}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds for mining supply-demand news")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD (default: yesterday Beijing time)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory (default: data/raw/)")
    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        now_beijing = datetime.now(BEIJING_TZ)
        target_date = (now_beijing - timedelta(days=1)).date()

    print(f"Fetching RSS feeds for {target_date} (Beijing time)...")

    # Output directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        script_dir = Path(__file__).parent.parent
        out_dir = script_dir / "data" / "raw"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{target_date}_rss.json"

    all_entries = []

    print("\n--- English sources ---")
    for feed in FEEDS_EN:
        print(f"  Fetching {feed['name']}...")
        entries = fetch_feed(feed, target_date)
        print(f"    Found {len(entries)} qualifying entries")
        all_entries.extend(entries)

    print("\n--- Chinese sources ---")
    for feed in FEEDS_ZH:
        print(f"  Fetching {feed['name']}...")
        entries = fetch_feed(feed, target_date)
        print(f"    Found {len(entries)} qualifying entries")
        all_entries.extend(entries)

    output = {
        "date": str(target_date),
        "fetched_at": datetime.now(BEIJING_TZ).isoformat(),
        "total_entries": len(all_entries),
        "entries": all_entries,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOutput: {out_file}")
    print(f"Total qualifying entries: {len(all_entries)}")


if __name__ == "__main__":
    main()
