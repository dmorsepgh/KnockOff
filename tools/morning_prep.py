#!/usr/bin/env python3
"""
Morning Prep Agent - Runs at 6 AM to prepare daily video content.

Generates:
- Daily video script based on trending topics
- Shot list for what to film
- Pre-filled template ready to go

Sends notification when ready.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import subprocess
import json

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Text notification script
TEXT_SCRIPT = Path.home() / "Documents" / "scripts" / "text-me.sh"

def get_trending_topics():
    """Get trending controversies and hot topics for today."""

    # CONTROVERSY PAYS GENERATOR
    # Strategy: Find what's trending, find the AI angle, ride the wave

    # TODO: Integrate with web search to auto-pull trending topics
    # For now, manual curation based on recent news cycles

    controversies = [
        {
            "title": "AI Replaces [Celebrity/Job]",
            "angle": "What this means for everyone else",
            "keywords": ["AI", "jobs", "automation", "controversy"],
            "hook": "Everyone is talking about this, but here's what they're missing",
            "category": "tech_controversy"
        },
        {
            "title": "Tech CEO Says [Controversial Thing]",
            "angle": "Break down the drama and who benefits",
            "keywords": ["tech", "controversy", "drama"],
            "hook": "The tech world is melting down over this",
            "category": "tech_drama"
        },
        {
            "title": "[Company] New AI Feature Backlash",
            "angle": "Why people are furious and what to do",
            "keywords": ["AI", "privacy", "backlash"],
            "hook": "This new AI feature has everyone worried",
            "category": "privacy_controversy"
        },
        {
            "title": "AI Tool [Does Something Crazy]",
            "angle": "How you can use this before it's banned",
            "keywords": ["AI", "viral", "trending"],
            "hook": "This AI tool went viral overnight",
            "category": "viral_tool"
        },
        {
            "title": "[Platform] Changes Algorithm",
            "angle": "How creators are adapting to win",
            "keywords": ["algorithm", "strategy", "growth"],
            "hook": "If you're on [platform], you need to know this",
            "category": "platform_change"
        }
    ]

    # Rotate through controversies
    day_of_year = datetime.now().timetuple().tm_yday
    return controversies[day_of_year % len(controversies)]

def generate_script(topic):
    """Generate video script based on topic."""

    script_content = f"""# {topic['title']}

**Generated:** {datetime.now().strftime('%Y-%m-%d %I:%M %p')}
**Duration Target:** 90s
**Format:** portrait
**Avatar:** doug

---

## Pre-Production Checklist

- [ ] Avatar video recorded (5-10 seconds)
- [ ] Screen recording of example/demo
- [ ] Intro graphic created (optional)
- [ ] Music track selected (optional)

---

## Shot List

**Avatar Base:**
- Filename: `doug.mp4`
- Duration: 5-10 seconds minimum
- Notes: Energetic, looking at camera

**B-roll Needed:**
- [ ] Screen recording of {topic['title'].lower()} in action → `broll/demo-{datetime.now().strftime('%Y%m%d')}.mp4`
- [ ] Optional: Workspace shot → `broll/workspace.mp4`

**Overlays/Graphics:**
- [ ] Title card with topic → `overlays/title-{datetime.now().strftime('%Y%m%d')}.png`

---

## Script (TEMPLATE - CUSTOMIZE BEFORE SHOOTING)

{topic['hook']}. Here's what you need to know.

[OVERLAY: title-{datetime.now().strftime('%Y%m%d')}.png | 3s]

The problem is [describe specific pain point your audience faces].

Most people don't realize [key insight about {topic['title'].lower()}].

Let me show you exactly how this works.

[BROLL: demo-{datetime.now().strftime('%Y%m%d')}.mp4 | 8s]

Here's what just happened: [explain the demo clearly].

The reason this matters is [connect to audience's goals].

You can start using this today. [Give specific next step].

[CTA: Follow for more | Daily AI tips at dmpgh.com]

The best part? [Final benefit or insight]. Try it and let me know how it goes.

---

## Keywords
{', '.join(topic['keywords'])}

---

## CONTROVERSY PAYS - Find Today's Hot Topic

**Before customizing this script:**
1. Check trending news (Twitter, Google Trends, YouTube trending)
2. Find AI angle on biggest controversy
3. Replace template with REAL hot topic
4. Strike while it's trending (24-48 hour window max)

**Example topics that work:**
- Tech CEO scandal + AI angle
- AI replaces [celebrity/job role]
- Platform algorithm change
- Viral AI tool drama
- Privacy controversy

## Next Steps

1. **Find actual controversy** - Check trending now, replace template
2. **Customize script** - Make it about the REAL hot topic
3. **Record avatar base video** - Save as `avatars/doug.mp4`
4. **Capture screen demo** - Save as `broll/demo-{datetime.now().strftime('%Y%m%d')}.mp4`
5. **(Optional) Create title graphic** - Save as `overlays/title-{datetime.now().strftime('%Y%m%d')}.png`
6. **Run preflight check:**
   ```bash
   python tools/preflight_check.py -s scripts/daily-{datetime.now().strftime('%Y%m%d')}.md -a doug
   ```
6. **Generate video:**
   ```bash
   python tools/generate_avatar_video.py -s scripts/daily-{datetime.now().strftime('%Y%m%d')}.md -a doug -f portrait
   ```
"""

    return script_content

def save_script(content):
    """Save generated script to scripts folder."""
    SCRIPTS_DIR.mkdir(exist_ok=True)

    today = datetime.now().strftime('%Y%m%d')
    filename = f"daily-{today}.md"
    filepath = SCRIPTS_DIR / filename

    filepath.write_text(content)
    print(f"✅ Script saved: {filepath}")

    return filepath

def send_notification(script_path, topic):
    """Send text notification that script is ready."""
    if not TEXT_SCRIPT.exists():
        print(f"⚠️  Text script not found at {TEXT_SCRIPT}")
        return

    message = f"Good morning! Your video script is ready: {topic['title']}. Check {script_path.name}"

    try:
        result = subprocess.run(
            [str(TEXT_SCRIPT), message],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ Notification sent")
        else:
            print(f"⚠️  Notification failed: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Could not send notification: {e}")

def main():
    print("=" * 80)
    print("MORNING PREP AGENT")
    print(f"Running at: {datetime.now().strftime('%I:%M %p')}")
    print("=" * 80)

    # Get today's topic
    print("\n1️⃣  Finding trending topic...")
    topic = get_trending_topics()
    print(f"   Topic: {topic['title']}")
    print(f"   Angle: {topic['angle']}")

    # Generate script
    print("\n2️⃣  Generating script...")
    script_content = generate_script(topic)

    # Save to file
    print("\n3️⃣  Saving script...")
    script_path = save_script(script_content)

    # Send notification
    print("\n4️⃣  Sending notification...")
    send_notification(script_path, topic)

    print("\n" + "=" * 80)
    print("✅ MORNING PREP COMPLETE")
    print(f"📝 Script ready: {script_path}")
    print(f"⏰ Time to shoot: 7:00 AM")
    print("=" * 80)

if __name__ == "__main__":
    main()
