#!/usr/bin/env python3
"""
Render Remotion graphics for an episode.

Reads show/epN/episode.json, writes intro/story-cards/credits MP4s into the
episode dir so the fundraiser pipeline can consume them.

Usage:
    python3 tools/remotion_render.py --episode 35
    python3 tools/remotion_render.py --episode 35 --accent 0x00d4ff
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"
REMOTION_DIR = Path.home() / "RemotionPlayground"


def render_composition(comp_id, out_path, props):
    """Render a single Remotion composition with given props."""
    cmd = [
        "npx", "remotion", "render",
        comp_id, str(out_path),
        "--props", json.dumps(props),
        "--log=error",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REMOTION_DIR),
        timeout=300,
    )
    if result.returncode != 0 or not out_path.exists():
        print(f"  ERROR rendering {comp_id}: {result.stderr[-500:]}")
        return False
    return True


def format_date_pretty(date_str):
    """Convert 2026-04-15 → April 15, 2026."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%B %-d, %Y")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", "-e", type=int, required=True)
    ap.add_argument("--accent", default="#00d4ff", help="Accent color hex")
    args = ap.parse_args()

    ep_dir = SHOW_DIR / f"ep{args.episode}"
    ep_json = ep_dir / "episode.json"
    if not ep_json.exists():
        print(f"Episode not found: {ep_json}")
        sys.exit(1)

    data = json.loads(ep_json.read_text())
    show_name = data.get("show_name", "AI VIEWS AND NEWS").upper()
    ep_num = int(data.get("episode", args.episode))
    date_pretty = format_date_pretty(data["date"])
    stories = data.get("stories", [])

    out_dir = ep_dir / "remotion"
    out_dir.mkdir(exist_ok=True)

    headlines = [s["title"][:90] for s in stories[:3]]

    print(f"🎬 Rendering Remotion clips for {show_name} EP{ep_num}...")

    # 1. Episode intro (show name, ep #, date, headlines)
    intro_path = out_dir / "intro.mp4"
    print(f"  → intro.mp4 ...")
    if not render_composition("EpisodeIntro", intro_path, {
        "showName": show_name,
        "tagline": "Your News. Your Way.",
        "episodeNumber": ep_num,
        "episodeDate": date_pretty,
        "headlines": headlines,
        "accentColor": args.accent,
    }):
        sys.exit(1)

    # 2. One story card per story
    for i, story in enumerate(stories[:3], start=1):
        card_path = out_dir / f"story-card-{i}.mp4"
        # Strip trailing source info from the title if present (" - Source")
        title = story["title"].split(" - ")[0].strip()
        source = story.get("source", "").replace('"multiple sclerosis" - ', "").strip() or "News"
        # Google News sources are messy; shorten
        if "google news" in source.lower():
            source = "Google News"
        print(f"  → story-card-{i}.mp4 ...")
        if not render_composition("StoryCard", card_path, {
            "storyNumber": i,
            "storyTitle": title,
            "source": source,
            "accentColor": args.accent,
        }):
            sys.exit(1)

    # 3. Rolling credits
    credits_path = out_dir / "credits.mp4"
    sections = [
        {"header": show_name, "lines": ["presents"]},
        {"header": "", "lines": [f"EPISODE {ep_num}", date_pretty]},
        {"header": "HOSTED BY", "lines": ["Douglas Morse"]},
        {"header": "PRODUCED WITH", "lines": ["Mother ShowRunner"]},
        {"header": "WRITTEN BY", "lines": ["Mistral Small"]},
        {"header": "VOICE", "lines": ["OpenAI TTS — Nova"]},
        {"header": "STOCK FOOTAGE", "lines": ["Pexels"]},
        {"header": "ANIMATED GRAPHICS", "lines": ["Remotion"]},
        {"header": "MORE AT", "lines": ["dmpgh.com", "mothershowrunner.com"]},
        {"header": "", "lines": [f"© {datetime.now().year} DMPGH LLC"]},
    ]
    print(f"  → credits.mp4 ...")
    if not render_composition("RollingCredits", credits_path, {
        "showName": show_name,
        "episodeNumber": ep_num,
        "sections": sections,
        "accentColor": args.accent,
    }):
        sys.exit(1)

    print(f"\n✅ Done. Clips in {out_dir}/")
    print(f"   intro.mp4")
    for i in range(1, min(4, len(stories) + 1)):
        print(f"   story-card-{i}.mp4")
    print(f"   credits.mp4")


if __name__ == "__main__":
    main()
