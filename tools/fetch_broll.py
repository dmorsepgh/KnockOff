#!/usr/bin/env python3
"""Fetch B-roll footage from Pexels API and save to broll/ folder."""

import argparse
import os
import re
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
BROLL_DIR = PROJECT_ROOT / "broll"

load_dotenv(PROJECT_ROOT / ".env")
API_KEY = os.getenv("PEXELS_API_KEY")


def search_videos(query, per_page=5, orientation="landscape", min_duration=3, max_duration=30):
    """Search Pexels for videos matching query."""
    headers = {"Authorization": API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
    }
    resp = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for video in data.get("videos", []):
        duration = video.get("duration", 0)
        if min_duration <= duration <= max_duration:
            # Get best HD file
            best = None
            for f in video.get("video_files", []):
                if f.get("quality") == "hd" and f.get("width", 0) >= 1280:
                    best = f
                    break
            if not best:
                # Fall back to any HD
                for f in video.get("video_files", []):
                    if f.get("quality") == "hd":
                        best = f
                        break
            if not best and video.get("video_files"):
                best = video["video_files"][0]

            if best:
                results.append({
                    "id": video["id"],
                    "duration": duration,
                    "width": best.get("width", 0),
                    "height": best.get("height", 0),
                    "url": best["link"],
                    "photographer": video.get("user", {}).get("name", "Unknown"),
                })
    return results


def download_video(url, output_path):
    """Download video from URL."""
    print(f"  Downloading → {output_path.name}...", end=" ", flush=True)
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    size = 0
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            size += len(chunk)
    print(f"({size / 1024 / 1024:.1f}MB)")


def slugify(text):
    """Convert text to filename-safe slug."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:50]


def fetch_broll(query, count=1):
    """Search and download B-roll for a query."""
    BROLL_DIR.mkdir(exist_ok=True)

    # Check if we already have footage for this query
    slug = slugify(query)
    existing = list(BROLL_DIR.glob(f"{slug}*"))
    if existing:
        print(f"Already have B-roll for '{query}': {[f.name for f in existing]}")
        return existing

    print(f"Searching Pexels for: '{query}'")
    results = search_videos(query, per_page=count + 2)

    if not results:
        print(f"  No results found for '{query}'")
        return []

    downloaded = []
    for i, video in enumerate(results[:count]):
        suffix = f"-{i+1}" if count > 1 else ""
        filename = f"{slug}{suffix}.mp4"
        output_path = BROLL_DIR / filename
        download_video(video["url"], output_path)
        print(f"  {video['width']}x{video['height']}, {video['duration']}s, by {video['photographer']}")
        downloaded.append(output_path)

    return downloaded


def fetch_broll_for_script(script_path):
    """Parse a script file and auto-fetch any missing B-roll."""
    sys.path.insert(0, str(Path(__file__).parent))
    from parse_script import parse_script

    with open(script_path) as f:
        text = f.read()

    segments = parse_script(text)
    fetched = []

    for seg in segments:
        if seg.type == "broll":
            content = seg.content.strip()
            broll_path = BROLL_DIR / content
            if not broll_path.exists() and not Path(content).exists():
                # Content is a keyword/description, not a file — fetch it
                keyword = content.replace(".mp4", "").replace("-", " ")
                result = fetch_broll(keyword, count=1)
                if result:
                    fetched.extend(result)
            else:
                print(f"B-roll exists: {content}")

    if fetched:
        print(f"\nFetched {len(fetched)} B-roll clip(s)")
    else:
        print("\nAll B-roll already available")
    return fetched


def main():
    if not API_KEY:
        print("Error: PEXELS_API_KEY not found in .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Fetch B-roll from Pexels")
    parser.add_argument("query", nargs="?", help="Search query (e.g. 'city traffic')")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of clips to download")
    parser.add_argument("--script", "-s", help="Parse script and fetch all missing B-roll")
    parser.add_argument("--list", "-l", action="store_true", help="List existing B-roll")

    args = parser.parse_args()

    if args.list:
        files = sorted(BROLL_DIR.glob("*.mp4"))
        if files:
            print(f"B-roll library ({len(files)} clips):")
            for f in files:
                size = f.stat().st_size / 1024 / 1024
                print(f"  {f.name} ({size:.1f}MB)")
        else:
            print("No B-roll clips yet. Use: python tools/fetch_broll.py 'search term'")
        return

    if args.script:
        fetch_broll_for_script(args.script)
        return

    if not args.query:
        parser.print_help()
        return

    fetch_broll(args.query, args.count)


if __name__ == "__main__":
    main()
