#!/usr/bin/env python3
"""
Vending Pipeline — End-to-end newscast generation.

Flow:
  1. User submits form (photo, topic, duration, email)
  2. Run showrunner.py to get stories + script for the topic
  3. Trim/select script to target duration
  4. Call HeyGen API with avatar + script
  5. Poll for completion
  6. Download finished video
  7. (Optional) Assemble with ffmpeg if extras are added later

Uses:
  - showrunner.py for news + script generation (local, free)
  - heygen_client.py for video rendering (paid API)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/Users/douglasmorse/.keys/.env")

# Local imports — heygen client lives next to this file
sys.path.insert(0, str(Path(__file__).parent))
from heygen_client import (
    generate_video,
    wait_for_video,
    download_video,
    check_remaining_credits,
)

PROJECT_ROOT = Path(__file__).parent
SHOWRUNNER = PROJECT_ROOT / "tools" / "showrunner.py"
VENDING_DIR = PROJECT_ROOT / "vending"
VENDING_DIR.mkdir(exist_ok=True)

# Default DMPGH avatar and voice for when user doesn't supply their own
DEFAULT_AVATAR_ID = "c655a8229ba449f99c14fc8ae5b7f64f"
DEFAULT_VOICE_ID = "2n9kTv3MBZ7LvK33Nhxm"

# Words per minute for HeyGen avatars (empirical)
WPM = 150


def trim_script_to_duration(script, target_seconds):
    """Trim a script down to approximately target_seconds of speech."""
    words = script.split()
    target_words = int((target_seconds / 60.0) * WPM)
    if len(words) <= target_words:
        return script
    return " ".join(words[:target_words])


def build_script(opening, stories, closing, target_seconds):
    """Combine opening + stories + closing, trim to target duration."""
    parts = [opening] + list(stories) + [closing]
    full = "\n\n".join(p.strip() for p in parts if p.strip())
    return trim_script_to_duration(full, target_seconds)


def run_showrunner(topic, show_name, job_dir):
    """
    Run the local showrunner.py to generate news + scripts.
    Returns dict with opening/stories/closing text.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Use python3.12 explicitly since Python 3.14 has a certifi issue
    python_bin = "/opt/homebrew/bin/python3.12" if Path("/opt/homebrew/bin/python3.12").exists() else sys.executable
    cmd = [
        python_bin,
        str(SHOWRUNNER),
        topic,
        "--show-name", show_name,
        "--date", date_str,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        raise RuntimeError(f"showrunner.py failed: {result.stderr}")

    # showrunner writes to PROJECT_ROOT/show/ep<n>/ — find the newest
    show_dir = PROJECT_ROOT / "show"
    ep_dirs = sorted(
        [d for d in show_dir.iterdir() if d.is_dir() and d.name.startswith("ep")],
        key=lambda d: int(re.sub(r"\D", "", d.name) or "0"),
    )
    if not ep_dirs:
        raise RuntimeError("showrunner did not create any episode directory")

    latest = ep_dirs[-1]

    opening = (latest / "heygen-opening.txt").read_text() if (latest / "heygen-opening.txt").exists() else ""
    closing = (latest / "heygen-closing.txt").read_text() if (latest / "heygen-closing.txt").exists() else ""
    stories = []
    for i in (1, 2, 3):
        f = latest / f"pictory-story{i}.txt"
        if f.exists():
            stories.append(f.read_text())

    return {
        "ep_dir": str(latest),
        "opening": opening.strip(),
        "stories": stories,
        "closing": closing.strip(),
    }


def generate_newscast(
    topic,
    show_name,
    duration_seconds,
    email,
    photo_path=None,
    avatar_id=None,
    voice_id=None,
    progress_cb=None,
):
    """
    Full vending pipeline.

    Args:
        topic: What the newscast is about (e.g. "AI news")
        show_name: Display name (e.g. "Doug's AI Update")
        duration_seconds: Target length (15, 60, 180, 300)
        email: Where to send the finished video link
        photo_path: Optional user photo (for now we use default avatar)
        avatar_id: Override the default avatar
        voice_id: Override the default voice
        progress_cb: Optional callable(stage, percent, message) for status updates

    Returns dict with {job_id, video_path, credits_used, cost_estimate}.
    """
    job_id = uuid.uuid4().hex[:8]
    job_dir = VENDING_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def tick(stage, pct, msg):
        print(f"[{pct}%] {stage}: {msg}")
        if progress_cb:
            progress_cb(stage, pct, msg)

    tick("init", 5, "Starting up...")

    # Save order record
    order = {
        "job_id": job_id,
        "topic": topic,
        "show_name": show_name,
        "duration_seconds": duration_seconds,
        "email": email,
        "created": datetime.now().isoformat(),
        "status": "running",
    }
    (job_dir / "order.json").write_text(json.dumps(order, indent=2))

    # Copy photo if provided
    if photo_path:
        dest = job_dir / "photo.jpg"
        shutil.copy(photo_path, dest)
        order["photo"] = str(dest)

    # Check HeyGen credits BEFORE doing any work
    tick("credits", 8, "Checking HeyGen balance...")
    credits = check_remaining_credits()
    api_credits = credits.get("details", {}).get("api", 0)
    needed = max(1, duration_seconds)  # rough estimate: 1 credit/sec
    if api_credits < needed:
        raise RuntimeError(
            f"Insufficient HeyGen API credits. Need ~{needed}, have {api_credits}."
        )

    # Step 1: Generate news + scripts locally (free)
    tick("news", 15, f"Fetching latest news on '{topic}'...")
    script_data = run_showrunner(topic, show_name, job_dir)

    # Step 2: Assemble the final script
    tick("script", 35, "Writing your newscast script...")
    final_script = build_script(
        script_data["opening"],
        script_data["stories"],
        script_data["closing"],
        duration_seconds,
    )
    (job_dir / "script.txt").write_text(final_script)

    # Step 3: Call HeyGen
    tick("heygen", 45, "Sending to HeyGen for rendering...")
    video_id = generate_video(
        avatar_id or DEFAULT_AVATAR_ID,
        final_script,
        voice_id=voice_id or DEFAULT_VOICE_ID,
    )
    order["heygen_video_id"] = video_id
    (job_dir / "order.json").write_text(json.dumps(order, indent=2))

    # Step 4: Poll HeyGen
    tick("render", 55, "HeyGen is rendering your video (2-5 minutes)...")
    video_url = wait_for_video(video_id, max_wait=600, poll_interval=10)

    # Step 5: Download
    tick("download", 85, "Downloading your finished video...")
    video_path = job_dir / "newscast.mp4"
    download_video(video_url, video_path)

    # Step 6: Check credits used
    credits_after = check_remaining_credits()
    credits_used = api_credits - credits_after.get("details", {}).get("api", 0)
    cost_estimate = credits_used * 0.017  # $10 / 600 credits = ~$0.017/credit

    tick("done", 100, f"Done! Used {credits_used} credits (~${cost_estimate:.2f})")

    order["status"] = "complete"
    order["video_path"] = str(video_path)
    order["credits_used"] = credits_used
    order["cost_estimate"] = cost_estimate
    (job_dir / "order.json").write_text(json.dumps(order, indent=2))

    return {
        "job_id": job_id,
        "video_path": str(video_path),
        "credits_used": credits_used,
        "cost_estimate": cost_estimate,
        "script_excerpt": final_script[:200] + "...",
    }


if __name__ == "__main__":
    # Quick test — generates a 15-second AI news video
    result = generate_newscast(
        topic="ai",
        show_name="Vending Test",
        duration_seconds=15,
        email="test@example.com",
    )
    print(json.dumps(result, indent=2))
