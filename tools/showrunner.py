#!/usr/bin/env python3
"""
ShowRunner — Mother of all show generators.

One input, one output. Type a topic, get a show.

Usage:
    python tools/showrunner.py "space news"
    python tools/showrunner.py "AI tech news"
    python tools/showrunner.py "cybersecurity news"
    python tools/showrunner.py "multiple sclerosis research"

    # With options
    python tools/showrunner.py "space news" --show-name "Space This Week" --stories 3
    python tools/showrunner.py "space news" --dry-run   # Just show stories, don't produce
"""

import argparse
import json
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path

import feedparser

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# RSS feeds by topic
FEEDS = {
    "ai": [
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://arstechnica.com/ai/feed/",
        "https://www.wired.com/feed/tag/ai/latest/rss",
    ],
    "tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://arstechnica.com/feed/",
    ],
    "space": [
        "https://www.space.com/feeds/all",
        "https://spacenews.com/feed/",
        "https://www.nasaspaceflight.com/feed/",
        "https://phys.org/rss-feed/space-news/",
        "https://www.universetoday.com/feed/",
    ],
    "cybersecurity": [
        "https://www.bleepingcomputer.com/feed/",
        "https://krebsonsecurity.com/feed/",
        "https://thehackernews.com/feeds/posts/default?alt=rss",
        "https://www.darkreading.com/rss.xml",
    ],
    "ms": [
        "https://news.google.com/rss/search?q=multiple+sclerosis&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=MS+treatment+research&hl=en-US&gl=US&ceid=US:en",
    ],
    "science": [
        "https://www.sciencedaily.com/rss/all.xml",
        "https://phys.org/rss-feed/",
        "https://www.newscientist.com/feed/home/",
    ],
}

# Map loose topic words to feed keys
TOPIC_MAP = {
    "ai": "ai", "artificial intelligence": "ai", "ai tech": "ai",
    "tech": "tech", "technology": "tech",
    "space": "space", "astronomy": "space", "nasa": "space", "rocket": "space",
    "cyber": "cybersecurity", "cybersecurity": "cybersecurity", "security": "cybersecurity", "hacking": "cybersecurity",
    "ms": "ms", "multiple sclerosis": "ms",
    "science": "science",
}


def resolve_topic(topic_input):
    """Map user input to a feed key."""
    topic_lower = topic_input.lower().strip()
    # Direct match
    if topic_lower in TOPIC_MAP:
        return TOPIC_MAP[topic_lower]
    # Partial match
    for key, value in TOPIC_MAP.items():
        if key in topic_lower or topic_lower in key:
            return value
    # Default to using topic as search term
    return topic_lower


def scrape_news(topic_key, max_stories=15):
    """Scrape RSS feeds for a topic, return ranked stories."""
    if topic_key in FEEDS:
        feeds = FEEDS[topic_key]
    else:
        # Unknown topic — use Google News RSS search instead of defaulting to tech
        query = topic_key.replace(" ", "+")
        feeds = [f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"]

    all_stories = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:10]:
                all_stories.append({
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "source": source,
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")[:300],
                })
        except Exception as e:
            print(f"  Warning: Failed to parse {feed_url}: {e}")

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for s in all_stories:
        title_key = s["title"].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(s)

    return unique[:max_stories]


def rank_stories(stories, topic, count=3):
    """Use Ollama to rank and pick the top stories."""
    story_list = "\n".join([f"{i+1}. {s['title']} ({s['source']})" for i, s in enumerate(stories)])

    prompt = f"""You are a news editor. Pick the {count} most interesting, newsworthy stories from this list about {topic}.

RULES:
- Pick stories that are DIFFERENT from each other (variety)
- Prefer breaking news over opinion pieces
- Prefer stories with broad appeal
- Return ONLY the numbers, one per line, nothing else

STORIES:
{story_list}

Return the {count} best story numbers, one per line:"""

    result = subprocess.run(
        ["ollama", "run", "mistral-small"],
        input=prompt, capture_output=True, text=True, timeout=60,
    )

    # Parse numbers from response
    numbers = re.findall(r'\b(\d+)\b', result.stdout)
    picked = []
    for n in numbers:
        idx = int(n) - 1
        if 0 <= idx < len(stories) and stories[idx] not in picked:
            picked.append(stories[idx])
        if len(picked) >= count:
            break

    # Fallback: just take the first N if Ollama didn't cooperate
    if len(picked) < count:
        for s in stories:
            if s not in picked:
                picked.append(s)
            if len(picked) >= count:
                break

    return picked


def write_scripts(stories, topic, show_name, date_str):
    """Use Ollama to write opening, story narrations, and closing."""
    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    story_titles = [s["title"] for s in stories]

    # Opening script
    opening_prompt = f"""Write a short TV news show opening (15-20 seconds when spoken).

SHOW: {show_name}
DATE: {formatted_date}
STORIES TODAY:
1. {story_titles[0]}
2. {story_titles[1]}
3. {story_titles[2]}

RULES:
- Greet the audience, name the show
- Preview all 3 stories briefly
- End with "Let's get into it" or similar
- Conversational, not formal
- NO stage directions, just spoken text
- 4-6 sentences max

Write the opening now:"""

    print("  Writing opening script...")
    opening = subprocess.run(
        ["ollama", "run", "mistral-small"],
        input=opening_prompt, capture_output=True, text=True, timeout=60,
    ).stdout.strip()

    # Story narrations (for Pictory)
    story_scripts = []
    for i, story in enumerate(stories):
        story_prompt = f"""Write a news narration script for a 2-minute video segment with B-roll footage.

STORY: {story['title']}
SOURCE: {story['source']}
SUMMARY: {story['summary']}

RULES:
- Write as voiceover narration (not on-camera dialogue)
- Explain what happened, why it matters, and what's next
- 150-200 words (about 90-120 seconds when spoken)
- Conversational but informative
- ABSOLUTELY NO parenthetical directions like (B-roll footage) or (music plays)
- ABSOLUTELY NO camera directions, scene descriptions, or production notes
- NO text in parentheses of ANY kind
- NO "in this segment", NO meta commentary
- ONLY write the words that should be spoken out loud
- Just plain narration text, nothing else

Write the narration now:"""

        print(f"  Writing story {i+1} script...")
        script = subprocess.run(
            ["ollama", "run", "mistral-small"],
            input=story_prompt, capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        story_scripts.append(script)

    # Closing script
    closing_prompt = f"""Write a short TV news show closing (15-20 seconds when spoken).

SHOW: {show_name}
STORIES COVERED:
1. {story_titles[0]}
2. {story_titles[1]}
3. {story_titles[2]}

RULES:
- Quick recap of what was covered (one line per story)
- Thank the audience
- Mention website dmpgh.com
- Say "see you next week" or similar
- Conversational
- 4-6 sentences max
- NO stage directions

Write the closing now:"""

    print("  Writing closing script...")
    closing = subprocess.run(
        ["ollama", "run", "mistral-small"],
        input=closing_prompt, capture_output=True, text=True, timeout=60,
    ).stdout.strip()

    return opening, story_scripts, closing


def save_episode(topic_key, show_name, date_str, stories, opening, story_scripts, closing):
    """Save episode files and metadata."""
    # Find next episode number
    existing = sorted(SHOW_DIR.glob("ep*"))
    next_num = max([int(d.name.replace("ep", "")) for d in existing if d.name.startswith("ep") and d.name[2:].isdigit()], default=0) + 1

    ep_dir = SHOW_DIR / f"ep{next_num}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    # Save individual scripts (legacy)
    (ep_dir / "heygen-opening.txt").write_text(opening)
    for i, script in enumerate(story_scripts):
        (ep_dir / f"pictory-story{i+1}.txt").write_text(script)
    (ep_dir / "heygen-closing.txt").write_text(closing)

    # Save combined HeyGen script (intro + outro in one take, 5-second pause between)
    heygen_combined = f"""{opening}

[PAUSE FOR 5 SECONDS]

{closing}"""
    (ep_dir / "heygen-combined.txt").write_text(heygen_combined)

    # Save combined Pictory script (all stories in one video)
    pictory_combined = "\n\n".join(story_scripts)
    (ep_dir / "pictory-combined.txt").write_text(pictory_combined)

    # Save metadata
    episode_data = {
        "episode": next_num,
        "date": date_str,
        "show_name": show_name,
        "topic": topic_key,
        "created": datetime.now().isoformat(),
        "stories": [{"title": s["title"], "source": s["source"], "link": s["link"]} for s in stories],
        "scripts": {
            "opening": str(ep_dir / "heygen-opening.txt"),
            "story1": str(ep_dir / "pictory-story1.txt"),
            "story2": str(ep_dir / "pictory-story2.txt"),
            "story3": str(ep_dir / "pictory-story3.txt"),
            "closing": str(ep_dir / "heygen-closing.txt"),
            "heygen_combined": str(ep_dir / "heygen-combined.txt"),
            "pictory_combined": str(ep_dir / "pictory-combined.txt"),
        },
        "include_intro_bumper": True,
        "include_credits_bumper": True,
        "status": "scripts_ready",
    }

    (ep_dir / "episode.json").write_text(json.dumps(episode_data, indent=2))

    return next_num, ep_dir


def main():
    parser = argparse.ArgumentParser(description="ShowRunner — Your news, your way.")
    parser.add_argument("topic", help="Topic to cover (e.g., 'space news', 'AI tech', 'cybersecurity')")
    parser.add_argument("--show-name", help="Show name (auto-generated if not set)")
    parser.add_argument("--stories", type=int, default=3, help="Number of stories (default 3)")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Episode date")
    parser.add_argument("--dry-run", action="store_true", help="Just show stories, don't write scripts")
    parser.add_argument("--list-feeds", action="store_true", help="List available topic feeds")

    args = parser.parse_args()

    if args.list_feeds:
        print("Available topics:")
        for key, feeds in FEEDS.items():
            print(f"\n  {key}:")
            for f in feeds:
                print(f"    - {f}")
        return

    topic_key = resolve_topic(args.topic)
    show_name = args.show_name or {
        "ai": "AI Views and News",
        "tech": "Tech World News",
        "space": "Space This Week",
        "cybersecurity": "Cyber Brief",
        "ms": "MS Watch",
        "science": "Science This Week",
    }.get(topic_key, f"{args.topic.title()} News")

    formatted_date = datetime.strptime(args.date, "%Y-%m-%d").strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"ShowRunner — {show_name}")
    print(f"Date: {formatted_date}")
    print(f"Topic: {topic_key}")
    print(f"{'='*60}")

    # Step 1: Scrape
    print(f"\n📡 Scraping news feeds...")
    stories = scrape_news(topic_key)
    print(f"   Found {len(stories)} stories")

    if not stories:
        print("ERROR: No stories found. Check RSS feeds.")
        return

    # Step 2: Rank
    print(f"\n🏆 Ranking top {args.stories}...")
    top_stories = rank_stories(stories, topic_key, args.stories)

    print(f"\n📰 Selected stories:")
    for i, s in enumerate(top_stories):
        print(f"   {i+1}. {s['title']}")
        print(f"      Source: {s['source']}")
        print(f"      Link: {s['link']}")
        print()

    if args.dry_run:
        print("(Dry run — stopping here)")
        return

    # Step 3: Write scripts
    print(f"✍️  Writing scripts...")
    opening, story_scripts, closing = write_scripts(top_stories, topic_key, show_name, args.date)

    # Step 4: Save everything
    ep_num, ep_dir = save_episode(topic_key, show_name, args.date, top_stories, opening, story_scripts, closing)

    print(f"\n{'='*60}")
    print(f"✅ Episode {ep_num} ready — {show_name}")
    print(f"   Directory: {ep_dir}")
    print(f"   Status: scripts_ready")
    print(f"\n📋 Next steps:")
    print(f"   1. Review/edit scripts in {ep_dir}/")
    print(f"   2. Generate HeyGen videos (opening + closing)")
    print(f"   3. Generate Pictory videos (3 stories)")
    print(f"   4. Run: python tools/assemble_episode.py --episode {ep_num}")
    print(f"{'='*60}")

    # Print scripts for review
    print(f"\n--- OPENING SCRIPT ---")
    print(opening)
    print(f"\n--- STORY 1: {top_stories[0]['title']} ---")
    print(story_scripts[0])
    print(f"\n--- STORY 2: {top_stories[1]['title']} ---")
    print(story_scripts[1])
    print(f"\n--- STORY 3: {top_stories[2]['title']} ---")
    print(story_scripts[2])
    print(f"\n--- CLOSING SCRIPT ---")
    print(closing)


if __name__ == "__main__":
    main()
