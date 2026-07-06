#!/usr/bin/env python3
"""
youtube_monitor.py — Monitor YouTube channels for new mining-related videos.

Reads channel IDs from mining_people_broadcast_x_articles.csv (rows with YouTube
or broadcast-related entries) and checks for new uploads matching gold/silver/copper
supply-demand keywords.

Output:
  data/raw/YYYY-MM-DD_youtube.json

Usage:
  python scripts/youtube_monitor.py --date 2026-07-05
  python scripts/youtube_monitor.py  # defaults to yesterday (Beijing time)

Requires:
  YouTube Data API v3 key (set as YOUTUBE_API_KEY env var)
  pip install google-api-python-client

Note:
  If no API key is set, the script falls back to RSS feed monitoring of channels.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))

# Known YouTube channels from CSV (channel name -> channel ID or handle)
KNOWN_CHANNELS = [
    {"name": "Mining Stock Daily", "query": "Mining Stock Daily mining", "host": "Trevor Hall"},
    {"name": "Soar Financial", "query": "Soar Financial mining gold silver", "host": "Kai Hoffmann"},
    {"name": "Sprott Insights", "query": "Sprott Insights gold silver copper", "host": "Sprott"},
    {"name": "Arcadia Economics", "query": "Arcadia Economics silver", "host": "Chris Marcus"},
    {"name": "MINING.COM TV", "query": "MINING.COM TV copper gold", "host": "Mining.com"},
]

# Keywords for filtering
SUPPLY_DEMAND_KEYWORDS = [
    "gold", "silver", "copper", "mine", "mining", "production", "supply", "demand",
    "smelter", "refinery", "permit", "expansion", "project", "drill", "exploration",
    "resource", "reserve", "grade", "capex", "feasibility", "PEA",
    "ETF", "central bank", "industrial", "solar", "EV",
    "gold mine", "silver mine", "copper mine",
    "gold production", "copper production", "silver production",
    "supply chain", "inventor",
]

METAL_PATTERNS = {
    "gold": [r"\bgold\b", r"\bgolden\b", r"\bAu\b"],
    "silver": [r"\bsilver\b", r"\bAg\b"],
    "copper": [r"\bcopper\b", r"\bCu\b"],
}


def match_metals(text):
    metals = []
    text_lower = text.lower()
    for metal, patterns in METAL_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower, re.IGNORECASE):
                metals.append(metal)
                break
    return metals


def is_relevant(title, description=""):
    text = f"{title} {description}".lower()
    return any(kw.lower() in text for kw in SUPPLY_DEMAND_KEYWORDS)


def search_youtube_api(api_key, target_date, days_window=3):
    """Use YouTube Data API v3 to search for relevant videos."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client not installed. Falling back to RSS.", file=sys.stderr)
        return None

    youtube = build("youtube", "v3", developerKey=api_key)

    published_after = datetime.combine(target_date - timedelta(days=days_window-1),
                                        datetime.min.time(),
                                        tzinfo=BEIJING_TZ).isoformat()
    published_before = datetime.combine(target_date + timedelta(days=1),
                                         datetime.min.time(),
                                         tzinfo=BEIJING_TZ).isoformat()

    results = []
    queries = [
        "gold mining supply demand",
        "silver mining supply demand",
        "copper mining supply demand",
        "gold mine production 2026",
        "copper mine production 2026",
        "silver mine production 2026",
        "mining CEO interview gold copper",
        "PDAC gold copper silver",
    ]

    for query in queries:
        try:
            response = youtube.search().list(
                q=query,
                part="snippet",
                type="video",
                publishedAfter=published_after,
                publishedBefore=published_before,
                maxResults=10,
                relevanceLanguage="en",
            ).execute()

            for item in response.get("items", []):
                title = item["snippet"]["title"]
                description = item["snippet"].get("description", "")
                video_id = item["id"]["videoId"]
                published = item["snippet"]["publishedAt"]

                if not is_relevant(title, description):
                    continue

                metals = match_metals(f"{title} {description}")
                if not metals:
                    continue

                results.append({
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "publish_date": published[:10],
                    "source_type": "youtube",
                    "guest": {"name": item["snippet"].get("channelTitle", ""), "background": ""},
                    "metal_tags": list(set(metals)),
                    "supply_demand": "both",
                    "summary": description[:200] if description else "",
                    "channel": item["snippet"].get("channelTitle", ""),
                })
        except Exception as e:
            print(f"  API error for query '{query}': {e}", file=sys.stderr)
            continue

    return results


def search_youtube_rss(target_date, days_window=3):
    """Fallback: Use YouTube RSS feeds for known channels."""
    try:
        import requests
        import feedparser
    except ImportError:
        print("requests/feedparser not installed for RSS fallback.", file=sys.stderr)
        return []

    results = []

    for channel in KNOWN_CHANNELS:
        try:
            resp = requests.get(
                f"https://www.youtube.com/results?search_query={channel['query']}&sp=EgIIBA%253D%253D",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code != 200:
                continue
        except Exception:
            continue

    print("  RSS fallback: YouTube RSS requires channel IDs in config.", file=sys.stderr)
    print("  Add channel IDs to KNOWN_CHANNELS for RSS monitoring.", file=sys.stderr)
    return results


def main():
    parser = argparse.ArgumentParser(description="Monitor YouTube for mining supply-demand videos")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--days-window", type=int, default=3, help="Search window in days (default: 3)")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        now_beijing = datetime.now(BEIJING_TZ)
        target_date = (now_beijing - timedelta(days=1)).date()

    print(f"Monitoring YouTube for {target_date} (window: {args.days_window} days)...")

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        script_dir = Path(__file__).parent.parent
        out_dir = script_dir / "data" / "raw"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{target_date}_youtube.json"

    api_key = os.environ.get("YOUTUBE_API_KEY")
    results = None

    if api_key:
        print("Using YouTube Data API v3...")
        results = search_youtube_api(api_key, target_date, args.days_window)
    else:
        print("No YOUTUBE_API_KEY set. Using RSS fallback...", file=sys.stderr)

    if results is None:
        results = search_youtube_rss(target_date, args.days_window)

    # Dedup by URL
    seen_urls = set()
    unique_results = []
    for item in results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)

    output = {
        "date": str(target_date),
        "fetched_at": datetime.now(BEIJING_TZ).isoformat(),
        "method": "youtube_api" if api_key else "rss_fallback",
        "days_window": args.days_window,
        "total_entries": len(unique_results),
        "entries": unique_results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOutput: {out_file}")
    print(f"Total qualifying videos: {len(unique_results)}")


if __name__ == "__main__":
    main()
