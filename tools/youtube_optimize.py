#!/usr/bin/env python3
"""
YouTube Optimizer — generate title, description, tags, and thumbnail
optimized for maximum CTR and discoverability.

Usage:
    python tools/youtube_optimize.py --episode 4
    python tools/youtube_optimize.py --title "Claude Code Leaked" --stories "story1" "story2" "story3"
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"
OUTPUT_DIR = PROJECT_ROOT / "thumbnails"


def generate_youtube_package(episode_num=None, stories=None, date_str=None):
    """Generate complete YouTube upload package."""

    # Load episode data
    episode_data = None
    if episode_num:
        ep_dir = SHOW_DIR / f"ep{episode_num}"
        json_path = ep_dir / "episode.json"
        if json_path.exists():
            episode_data = json.loads(json_path.read_text())
            if not stories:
                stories = [s["title"] for s in episode_data.get("stories", [])]
            if not date_str:
                date_str = episode_data.get("date")

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    formatted_date = dt.strftime("%B %d, %Y")

    if not stories or len(stories) < 3:
        print("ERROR: Need at least 3 story titles")
        return

    # =====================================================
    # TITLE — The most important element
    # Rules:
    # - Under 60 characters (so it doesn't get cut off)
    # - Lead with the most shocking/interesting story
    # - Use power words: leaked, exposed, destroyed, killed
    # - Include a number or list when possible
    # - Don't give away the answer — create curiosity
    # =====================================================

    # Generate multiple title options — pick the best
    titles = []

    # Pattern 1: Lead story + "and it's worse than you think"
    lead = stories[0].split("—")[0].split(":")[0].strip()
    titles.append(f"{lead} — And It's Worse Than You Think")

    # Pattern 2: Number + topic
    titles.append(f"3 AI Stories That Should Terrify You This Week")

    # Pattern 3: Question format
    titles.append(f"Did Anthropic Just Expose Their Own AI? | AI News {formatted_date}")

    # Pattern 4: Direct + date
    titles.append(f"AI News: {lead} | {dt.strftime('%b %d')}")

    # Pattern 5: Shock + show name
    short_lead = lead[:40] if len(lead) > 40 else lead
    titles.append(f"{short_lead} | AI Views and News Ep{episode_num}")

    # =====================================================
    # DESCRIPTION — SEO + engagement
    # Rules:
    # - First 2 lines show in search (before "Show more")
    # - Include keywords naturally
    # - Timestamps for each segment
    # - Links to sources
    # - Call to action
    # - Hashtags at the bottom
    # =====================================================

    description = f"""This week on AI Views and News: {stories[0]}. Plus: {stories[1]} and {stories[2]}.

New episodes every week. Subscribe for the latest AI news analysis.

📋 TIMESTAMPS:
0:00 — Introduction
0:30 — Story 1: {stories[0]}
2:30 — Story 2: {stories[1]}
5:00 — Story 3: {stories[2]}
7:30 — Wrap-up & Discussion Questions

📰 SOURCES:"""

    if episode_data:
        for s in episode_data.get("stories", []):
            description += f"\n• {s['title']}: {s['link']}"

    description += f"""

💬 DISCUSSION QUESTIONS (for your team/class):
1. Should AI companies be required to disclose all features, even experimental ones?
2. Can a company genuinely prioritize safety while racing to compete?
3. If AI could do 80% of your job tomorrow, would your industry adapt or resist?
4. At what point does "keeping up with AI" become a full-time job?
5. If you could ask any AI CEO one honest question, who and what?

🔗 LINKS:
• Show Notes: https://myaibiweekly.com/ep{episode_num}/
• Website: https://dmpgh.com
• All Episodes: https://myaibiweekly.com

👋 ABOUT:
AI Views and News is a weekly AI news briefing hosted by Doug Morse. We break down the biggest stories in artificial intelligence so you can stay informed without the jargon.

#AI #ArtificialIntelligence #AINews #Claude #Anthropic #TechNews #AIViewsAndNews #DougMorse #WeeklyAINews #MachineLearning #GenerativeAI #AIUpdate #Tech{dt.strftime('%Y')}"""

    # =====================================================
    # TAGS — YouTube search optimization
    # Rules:
    # - Mix broad + specific
    # - Include misspellings people search
    # - Include competitor names (people searching for them find you)
    # - Max 500 characters total
    # =====================================================

    tags = [
        "AI news",
        "artificial intelligence news",
        "AI news this week",
        "AI weekly update",
        "AI Views and News",
        "Doug Morse",
        "Claude AI",
        "Anthropic",
        "Claude code leak",
        "AI art schools",
        "AI news today",
        "tech news",
        "AI update",
        "generative AI",
        "machine learning news",
        "AI 2026",
        "weekly AI roundup",
        "AI briefing",
        "AI for beginners",
        "what happened in AI this week",
        "AI news analysis",
        "artificial intelligence update",
        "AI trends",
        "ChatGPT alternative",
        "Claude vs ChatGPT",
    ]

    # Add story-specific tags
    for story in stories:
        words = story.lower().split()
        for w in words:
            if len(w) > 4 and w not in ["about", "being", "their", "these", "those", "which", "where"]:
                if w not in [t.lower() for t in tags]:
                    tags.append(w)

    # =====================================================
    # THUMBNAIL HOOKS — multiple options to test
    # =====================================================

    thumb_hooks = [
        "CLAUDE LEAKED",
        "AI EXPOSED",
        "ART IS DEAD?",
        "THEY HID THIS",
        "AI GONE WRONG",
    ]

    # =====================================================
    # OUTPUT
    # =====================================================

    print("=" * 60)
    print(f"YOUTUBE PACKAGE — Episode {episode_num}")
    print(f"Date: {formatted_date}")
    print("=" * 60)

    print("\n📌 TITLE OPTIONS (pick one):\n")
    for i, t in enumerate(titles, 1):
        chars = len(t)
        status = "✓" if chars <= 60 else f"⚠ {chars} chars"
        print(f"  {i}. {t}")
        print(f"     [{status}]")

    print(f"\n📝 DESCRIPTION:\n")
    print(description)

    print(f"\n🏷️  TAGS ({len(tags)} tags):\n")
    print(", ".join(tags))

    print(f"\n🖼️  THUMBNAIL HOOKS (for A/B testing):\n")
    for h in thumb_hooks:
        print(f"  • {h}")

    # Save to file
    output = {
        "episode": episode_num,
        "date": date_str,
        "titles": titles,
        "description": description,
        "tags": tags,
        "thumbnail_hooks": thumb_hooks,
    }

    output_path = OUTPUT_DIR / f"ep{episode_num}-youtube-package.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Saved to: {output_path}")

    # Also save description as plain text for easy copy/paste
    desc_path = OUTPUT_DIR / f"ep{episode_num}-description.txt"
    with open(desc_path, "w") as f:
        f.write(description)
    print(f"📋 Description: {desc_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube upload package")
    parser.add_argument("--episode", "-e", type=int, help="Episode number")
    parser.add_argument("--stories", nargs="+", help="Story titles")
    parser.add_argument("--date", help="Episode date YYYY-MM-DD")

    args = parser.parse_args()
    generate_youtube_package(args.episode, args.stories, args.date)


if __name__ == "__main__":
    main()
