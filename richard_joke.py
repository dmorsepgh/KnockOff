#!/usr/bin/env python3
"""
One-shot: create Richard Pryor photo avatar and generate the proof-of-concept joke video.
"""

import time
import requests
from pathlib import Path
from heygen_client import (
    upload_asset, create_photo_avatar, generate_video,
    wait_for_video, download_video, check_remaining_credits, BASE_URL, HEADERS
)

PHOTO = "/Users/douglasmorse/Documents/rp.jpg"
OUTPUT = "/Users/douglasmorse/Documents/Fundraiser Videos/richard_pryor_joke_v1.mp4"

JOKE = """I went to the doctor, he says "Richard, your immune system is attacking your nervous system."
I said — my OWN immune system?
He said yes.
I said, so my body hired somebody to come after ME?
That's the most gangster thing I ever heard.
I been set up from the inside."""


def wait_for_avatar(group_id, max_wait=300, poll_interval=10):
    """Poll until photo avatar is trained and ready."""
    elapsed = 0
    while elapsed < max_wait:
        resp = requests.get(
            f"{BASE_URL}/v2/photo_avatar/photo/list",
            headers=HEADERS,
            params={"group_id": group_id},
            timeout=30,
        )
        resp.raise_for_status()
        avatars = resp.json().get("data", {}).get("photo_avatar_list", [])
        if avatars:
            status = avatars[0].get("status", "")
            avatar_id = avatars[0].get("avatar_id") or avatars[0].get("id")
            print(f"[{elapsed}s] Avatar status: {status} | id: {avatar_id}")
            if status == "completed" and avatar_id:
                return avatar_id
            if status == "failed":
                raise RuntimeError("Avatar generation failed")
        time.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError("Avatar not ready in time")


if __name__ == "__main__":
    print("=== Richard Pryor Joke — Proof of Concept ===")

    credits = check_remaining_credits()
    print(f"Credits: {credits}")

    print("\nStep 1: Creating photo avatar from rp.jpg...")
    avatar_data = create_photo_avatar(PHOTO, name="Richard Pryor")
    print(f"Avatar data: {avatar_data}")

    group_id = avatar_data.get("group_id") or avatar_data.get("id")
    if not group_id:
        raise RuntimeError(f"No group_id returned: {avatar_data}")

    print(f"\nStep 2: Waiting for avatar to train (group_id: {group_id})...")
    avatar_id = wait_for_avatar(group_id)
    print(f"Avatar ready: {avatar_id}")

    print("\nStep 3: Generating joke video...")
    video_id = generate_video(
        avatar_id=avatar_id,
        script=JOKE,
        width=1080,
        height=1080,
        background_color="#1a1a1a",
    )
    print(f"Video ID: {video_id}")

    print("\nStep 4: Waiting for video to render...")
    video_url = wait_for_video(video_id)
    print(f"Video URL: {video_url}")

    print(f"\nStep 5: Downloading to {OUTPUT}...")
    download_video(video_url, OUTPUT)
    print(f"\nDone! Richard's ready: {OUTPUT}")

    import subprocess
    subprocess.Popen(["open", OUTPUT])
