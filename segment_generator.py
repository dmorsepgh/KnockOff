#!/usr/bin/env python3.12
"""
News Segment Generator — 10-minute AI news video from collected articles.

Pipeline:
  1. Load news JSON (from news_collector.py output)
  2. Pick top stories, generate scene-by-scene script
  3. Pexels API pulls b-roll for each scene
  4. OpenAI TTS narrates each scene
  5. ffmpeg assembles scenes with news-style banner
  6. Title cards between stories
  7. Concat everything with music bed

Usage:
  python3.12 segment_generator.py --topic "AI news" --date 2026-04-12 --show-name "AI Views & News"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".keys" / ".env")
except ImportError:
    pass

import requests
from PIL import Image, ImageDraw, ImageFont

# Import reusable functions from the fundraiser generator
sys.path.insert(0, str(Path(__file__).parent))
from fundraiser_generator import (
    fetch_broll,
    narrate_scene,
    probe_duration,
    concat_scenes,
    try_real_footage,
    PEXELS_KEY,
    OPENAI_KEY,
)

PROJECT_ROOT = Path(__file__).parent
OUT_DIR = PROJECT_ROOT / "news_segments"
OUT_DIR.mkdir(exist_ok=True)

USER_OUT_DIR = Path.home() / "Documents" / "News Segments"
USER_OUT_DIR.mkdir(parents=True, exist_ok=True)

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

TTS_ENGINE = "openai"
OPENAI_VOICE = "onyx"  # deeper voice for news anchor feel


# ────────────────────────────────────────────────────
# STEP 1: LOAD + PICK STORIES
# ────────────────────────────────────────────────────

def load_news(date_str: str) -> list:
    """Load collected news JSON for a given date."""
    news_path = PROJECT_ROOT / "news" / f"news-{date_str}.json"
    if not news_path.exists():
        sys.exit(f"No news file found: {news_path}")
    articles = json.loads(news_path.read_text())
    print(f"  Loaded {len(articles)} articles from {news_path.name}")
    return articles


def pick_stories(articles: list, count: int = 6) -> list:
    """Pick the best stories — deduplicate by topic, prefer variety."""
    # Simple approach: take the first `count` that aren't duplicates
    seen_titles = set()
    picked = []
    for article in articles:
        title_words = set(article["title"].lower().split()[:5])
        # Skip if too similar to an already-picked story
        is_dupe = any(len(title_words & s) >= 3 for s in seen_titles)
        if is_dupe:
            continue
        seen_titles.add(frozenset(title_words))
        picked.append(article)
        if len(picked) >= count:
            break
    print(f"  Picked {len(picked)} stories")
    return picked


# ────────────────────────────────────────────────────
# STEP 2: WRITE SCRIPT
# ────────────────────────────────────────────────────

def write_script_from_stories(stories: list, show_name: str, topic: str, date_str: str) -> dict:
    """
    Generate a full segment script from picked stories.
    Each story becomes 2 scenes: headline+context and impact.
    Plus intro and outro.
    """
    scenes = []

    # Intro
    story_count = len(stories)
    scenes.append({
        "type": "intro",
        "narration": (
            f"Welcome to {show_name}. "
            f"Today is {_format_date(date_str)}, and we've got {story_count} stories "
            f"shaping the {topic} landscape this week. Let's get into it."
        ),
        "keywords": ["technology news desk", "digital abstract background"],
        "duration_target": 12,
    })

    for i, story in enumerate(stories, 1):
        title = story["title"]
        source = story.get("source", "")
        description = story.get("description", "")
        summary = story.get("summary", "")

        # Clean up the summary — remove the chatty preamble many summaries have
        narr_text = _clean_summary(summary, title)

        # Generate keywords from the title
        keywords = _extract_keywords(title, description)

        # Title card
        scenes.append({
            "type": "title_card",
            "story_number": i,
            "headline": title,
            "source": source,
        })

        # Story scene (combined — headline + context + impact in one scene)
        scenes.append({
            "type": "story",
            "story_number": i,
            "narration": narr_text,
            "keywords": keywords,
            "duration_target": 25,
            "source_url": story.get("link", ""),
            "headline": title,
        })

    # Outro
    scenes.append({
        "type": "outro",
        "narration": (
            f"That's your {topic} roundup for {_format_date(date_str)}. "
            f"Thanks for watching {show_name}. "
            f"If any of these stories caught your attention, drop a comment below. "
            f"We'll see you next time."
        ),
        "keywords": ["sunset cityscape", "technology abstract light"],
        "duration_target": 15,
    })

    script = {
        "show_name": show_name,
        "topic": topic,
        "date": date_str,
        "brand_color": "0x00aaff",
        "scenes": scenes,
    }
    return script


def _format_date(date_str: str) -> str:
    """Convert 2026-04-12 to 'April 12th, 2026'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day = dt.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return dt.strftime(f"%B {day}{suffix}, %Y")


def _clean_summary(summary: str, title: str) -> str:
    """Strip chatty preamble from the LLM-generated summaries."""
    # Remove lines like "Here's a summary..." or "[Upbeat music plays]"
    lines = summary.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip().strip('"')
        if not line:
            continue
        if line.lower().startswith(("here's", "host:", "[", "breaking news")):
            continue
        cleaned.append(line)
    result = " ".join(cleaned)
    if not result:
        result = f"Next up: {title}."
    return result


def _extract_keywords(title: str, description: str) -> list:
    """Pull 2-3 visual keywords from story title/description for Pexels search."""
    # Common visual mapping for AI/tech news
    keyword_map = {
        "openai": "technology office modern",
        "chatgpt": "person using laptop",
        "google": "google technology office",
        "meta": "social media technology",
        "microsoft": "microsoft technology office",
        "anthropic": "artificial intelligence research",
        "florida": "government building courthouse",
        "investigation": "legal documents courthouse",
        "lawsuit": "courtroom legal",
        "attack": "security surveillance camera",
        "gen z": "young people smartphones",
        "copilot": "person computer screen",
        "subscription": "online payment digital",
        "robot": "robot technology futuristic",
        "tokyo": "tokyo city technology",
        "iran": "news broadcast screen",
        "ai art": "digital art creative",
        "lego": "animation creative colorful",
        "stalking": "phone screen dark",
    }

    combined = (title + " " + description).lower()
    keywords = []
    for trigger, kw in keyword_map.items():
        if trigger in combined:
            keywords.append(kw)
            if len(keywords) >= 2:
                break

    if not keywords:
        keywords = ["technology news abstract", "digital innovation"]

    return keywords


# ────────────────────────────────────────────────────
# STEP 3: TITLE CARD VIDEO
# ────────────────────────────────────────────────────

def make_title_card(out_path: Path, story_number: int, headline: str,
                    source: str, brand_color: str, sting_path: str = None,
                    duration: float = 3.0):
    """
    Build a short title card video: story number + headline on dark background.
    Optionally with a news sting audio.
    """
    # Truncate headline for display
    if len(headline) > 80:
        headline = headline[:77] + "..."
    safe_headline = headline.replace("'", "").replace(":", " -").replace('"', "")
    safe_source = source.replace("'", "").replace(":", "").replace('"', "")

    # Build filter
    filter_parts = (
        f"color=c=0x0a0e1a:s=1920x1080:d={duration}:r=30,"
        f"drawtext=fontfile='{FONT_BOLD}':text='STORY {story_number}':"
        f"fontcolor={brand_color}:fontsize=72:x=(w-text_w)/2:y=380,"
        f"drawtext=fontfile='{FONT}':text='{safe_headline}':"
        f"fontcolor=white:fontsize=42:x=(w-text_w)/2:y=500,"
        f"drawtext=fontfile='{FONT}':text='{safe_source}':"
        f"fontcolor=0x888888:fontsize=28:x=(w-text_w)/2:y=580"
    )

    inputs = ["-f", "lavfi", "-i", filter_parts]

    if sting_path and Path(sting_path).exists():
        inputs.extend(["-i", sting_path])
        maps = ["-map", "0:v", "-map", "1:a", "-shortest"]
    else:
        # Silent audio
        inputs.extend(["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo"])
        maps = ["-map", "0:v", "-map", "1:a"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        *maps,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Title card failed: {result.stderr[-300:]}")
        raise RuntimeError("Title card build failed")


# ────────────────────────────────────────────────────
# STEP 4: NEWS SCENE ASSEMBLER
# ────────────────────────────────────────────────────

def assemble_news_scene(broll_files, narration_wav, out_path, duration,
                        show_name="", headline="", brand_color="0x00aaff"):
    """
    Build a single news scene: b-roll + narration + news-style lower-third banner.
    Simplified version of fundraiser_generator.assemble_scene() — no logo plate,
    no QR card, no overlays.
    """
    if not broll_files:
        filter_in = ["-f", "lavfi", "-i", f"color=c=0x0a0e1a:s=1920x1080:d={duration}:r=30"]
    else:
        filter_in = ["-stream_loop", "-1", "-i", str(broll_files[0])]

    # Clean text for ffmpeg drawtext
    safe_show = show_name.upper().replace("'", "").replace(":", "").replace('"', "")
    safe_headline = headline.replace("'", "").replace(":", " -").replace('"', "")
    if len(safe_headline) > 60:
        safe_headline = safe_headline[:57] + "..."

    show_px_per_char = 26
    show_width = len(safe_show) * show_px_per_char
    headline_x = 40 + show_width + 24

    main_chain = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "fps=30,"
        "eq=saturation=0.85:contrast=1.08,"
        f"drawbox=x=0:y=918:w=1920:h=162:color=0x0a0e1a@0.85:t=fill,"
        f"drawbox=x=0:y=918:w=1920:h=4:color={brand_color}@1.0:t=fill,"
        f"drawtext=fontfile='{FONT_BOLD}':text='{safe_show}':"
        f"fontcolor=white:fontsize=44:x=40:y=965,"
        f"drawtext=fontfile='{FONT}':text='\u2014 {safe_headline}':"
        f"fontcolor=0xcccccc:fontsize=32:x={headline_x}:y=975"
    )

    inputs = list(filter_in)
    inputs.extend(["-i", str(narration_wav)])

    filter_complex = f"[0:v]{main_chain}[vout]"
    maps = ["-map", "[vout]", "-map", "1:a"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *maps,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  News scene failed: {result.stderr[-500:]}")
        raise RuntimeError("News scene assembly failed")


# ────────────────────────────────────────────────────
# MAIN PIPELINE
# ────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate a 10-minute news segment video")
    ap.add_argument("--topic", default="AI news", help="Segment topic")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="News date (YYYY-MM-DD)")
    ap.add_argument("--show-name", default="AI Views & News", help="Show name for banner")
    ap.add_argument("--stories", type=int, default=6, help="Number of stories to include")
    ap.add_argument("--music", default="", help="Path to background music bed")
    ap.add_argument("--sting", default="", help="Path to news sting audio for title cards")
    ap.add_argument("--brand-color", default="0x00aaff", help="Brand accent color (hex)")
    ap.add_argument("--voice", default="onyx", help="OpenAI TTS voice (onyx, nova, fable, etc.)")
    ap.add_argument("--script", default="", help="Path to pre-written script JSON (skip generation)")
    ap.add_argument("--picked-stories-json", default="", help="Path to JSON list of user-picked stories (skip auto-pick)")
    ap.add_argument("--reuse", default="", help="Path to existing job dir to reuse audio/broll")
    ap.add_argument("--no-captions", action="store_true", help="Skip Whisper caption generation (default: captions ON)")
    ap.add_argument("--caption-model", default="base", help="Whisper model size (tiny/base/small/medium/large)")
    args = ap.parse_args()

    global OPENAI_VOICE
    OPENAI_VOICE = args.voice

    # Patch narrate_scene to use our voice choice
    import fundraiser_generator
    fundraiser_generator.OPENAI_VOICE = args.voice

    brand_color = args.brand_color

    # Set up job directory
    reuse_dir = Path(args.reuse) if args.reuse else None
    if reuse_dir and reuse_dir.exists():
        job_dir = reuse_dir
        print(f"  Reusing existing job: {job_dir}")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_topic = args.topic.replace(" ", "_")
        job_dir = OUT_DIR / f"{safe_topic}_{stamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Output: {job_dir}")

    # ── Script ──
    script_path = job_dir / "script.json"
    if args.script and Path(args.script).exists():
        script = json.loads(Path(args.script).read_text())
        script_path.write_text(json.dumps(script, indent=2))
        print(f"  Script loaded from: {args.script}")
    elif args.picked_stories_json and Path(args.picked_stories_json).exists():
        stories = json.loads(Path(args.picked_stories_json).read_text())
        print(f"  Using {len(stories)} user-picked stories (skipping auto-pick)")
        script = write_script_from_stories(stories, args.show_name, args.topic, args.date)
        script_path.write_text(json.dumps(script, indent=2))
        print(f"  Script written: {len(script['scenes'])} scenes")
    elif reuse_dir and script_path.exists():
        script = json.loads(script_path.read_text())
        print(f"  Reusing existing script")
    else:
        articles = load_news(args.date)
        stories = pick_stories(articles, args.stories)
        script = write_script_from_stories(stories, args.show_name, args.topic, args.date)
        script_path.write_text(json.dumps(script, indent=2))
        print(f"  Script written: {len(script['scenes'])} scenes")

    show_name = script.get("show_name", args.show_name)

    # Sting path
    sting_path = args.sting
    if not sting_path:
        default_sting = PROJECT_ROOT / "music" / "news_sting.wav"
        if default_sting.exists():
            sting_path = str(default_sting)

    # Music path
    music_path = args.music if args.music else None
    if not music_path:
        default_music = PROJECT_ROOT / "music" / "upbeat.mp3"
        if default_music.exists():
            music_path = str(default_music)

    # ── Per-scene pipeline ──
    scene_files = []
    scene_idx = 0

    for scene in script["scenes"]:
        scene_type = scene["type"]

        if scene_type == "title_card":
            # Title card — short branded transition
            scene_idx += 1
            tc_dir = job_dir / f"scene{scene_idx:02d}_title"
            tc_dir.mkdir(exist_ok=True)
            tc_path = tc_dir / "title_card.mp4"

            if tc_path.exists() and reuse_dir:
                print(f"  Reusing title card: story {scene['story_number']}")
            else:
                print(f"  Building title card: story {scene['story_number']} — {scene['headline'][:50]}...")
                make_title_card(
                    tc_path,
                    story_number=scene["story_number"],
                    headline=scene["headline"],
                    source=scene.get("source", ""),
                    brand_color=brand_color,
                    sting_path=sting_path,
                    duration=3.0,
                )
            scene_files.append(tc_path)

        elif scene_type in ("intro", "story", "outro"):
            scene_idx += 1
            scene_dir = job_dir / f"scene{scene_idx:02d}_{scene_type}"
            scene_dir.mkdir(exist_ok=True)

            narration_text = scene["narration"]
            keywords = scene.get("keywords", ["technology news"])
            target_duration = scene.get("duration_target", 20)

            headline = ""
            if scene_type == "story":
                headline = scene.get("headline", script["scenes"][scene_idx - 2].get("headline", ""))
                # Find the preceding title_card to get the headline
                for prev in reversed(script["scenes"][:script["scenes"].index(scene)]):
                    if prev.get("type") == "title_card" and prev.get("story_number") == scene.get("story_number"):
                        headline = prev["headline"]
                        break
            elif scene_type == "intro":
                headline = f"{script['topic'].upper()} ROUNDUP"
            elif scene_type == "outro":
                headline = "THANKS FOR WATCHING"

            print(f"\n  Scene {scene_idx} ({scene_type}) — {target_duration}s target")

            # B-roll — try real article footage first for story scenes
            existing_broll = sorted(scene_dir.glob("broll_*.mp4"))
            existing_hero = list(scene_dir.glob("hero_kenburns.mp4"))
            if existing_hero:
                broll = existing_hero
                print(f"    Reusing real footage: {broll[0].name}")
            elif existing_broll:
                broll = existing_broll
                print(f"    Reusing b-roll: {broll[0].name}")
            else:
                broll = None
                if scene_type == "story" and scene.get("source_url"):
                    clip = try_real_footage(
                        scene["source_url"], scene_dir,
                        duration=target_duration + 2,
                    )
                    if clip:
                        broll = [clip]
                if broll is None:
                    broll = fetch_broll(keywords, scene_dir, count=1)

            # Narration
            narration_wav = scene_dir / "narration.wav"
            if narration_wav.exists() and narration_wav.stat().st_size > 1000:
                print(f"    Reusing narration")
            else:
                narrate_scene(narration_text, narration_wav)

            narration_dur = probe_duration(narration_wav)
            scene_dur = max(target_duration, narration_dur + 0.5)

            # Assemble
            scene_mp4 = scene_dir / "scene.mp4"
            assemble_news_scene(
                broll, narration_wav, scene_mp4, scene_dur,
                show_name=show_name,
                headline=headline,
                brand_color=brand_color,
            )
            scene_files.append(scene_mp4)
            print(f"    Done: {scene_dur:.1f}s")

    # ── Concat ──
    version = 1
    while (job_dir / f"segment_v{version}.mp4").exists():
        version += 1
    final = job_dir / f"segment_v{version}.mp4"

    print(f"\n  Concatenating {len(scene_files)} scenes -> {final.name}")
    if music_path:
        print(f"    Music: {Path(music_path).name}")

    concat_scenes(scene_files, final, music_path=music_path)

    # Soft captions — Whisper SRT muxed as mov_text subtitle track
    if not args.no_captions:
        try:
            from fundraiser_generator import add_soft_captions
            add_soft_captions(final, model_size=args.caption_model)
        except Exception as e:
            print(f"  ⚠️  Caption step failed (continuing): {e}")

    # Copy to user-facing folder (+ sidecar SRT if it exists)
    user_stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    user_name = f"{show_name.replace(' ', '_')}_{user_stamp}_v{version}.mp4"
    user_copy = USER_OUT_DIR / user_name
    shutil.copy2(final, user_copy)
    srt_final = final.with_suffix(".srt")
    if srt_final.exists():
        shutil.copy2(srt_final, user_copy.with_suffix(".srt"))
    print(f"    Copied to: {user_copy}")

    # Summary
    total_dur = probe_duration(final)
    print(f"\n  DONE — {total_dur:.1f}s ({total_dur/60:.1f} min), {len(scene_files)} scenes")
    print(f"  Final: {final}")
    print(f"  User copy: {user_copy}")


if __name__ == "__main__":
    main()
