#!/usr/bin/env python3
"""
HeyGen API Client — Photo avatar creation + video generation.

Docs: https://docs.heygen.com/reference
"""

import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load central keys
load_dotenv("/Users/douglasmorse/.keys/.env")

API_KEY = os.environ.get("HEYGEN_API_KEY")
if not API_KEY:
    raise RuntimeError("HEYGEN_API_KEY not found in ~/.keys/.env")

BASE_URL = "https://api.heygen.com"
UPLOAD_URL = "https://upload.heygen.com"

HEADERS = {
    "X-Api-Key": API_KEY,
    "Accept": "application/json",
}


def upload_asset(file_path, asset_type="image"):
    """Upload a file (photo or audio) to HeyGen. Returns asset_id."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # HeyGen uses v1/asset endpoint with multipart upload
    content_type = "image/jpeg" if asset_type == "image" else "audio/mpeg"
    if p.suffix.lower() in (".png",):
        content_type = "image/png"
    elif p.suffix.lower() in (".wav",):
        content_type = "audio/wav"
    elif p.suffix.lower() in (".mp3",):
        content_type = "audio/mpeg"

    with open(p, "rb") as f:
        resp = requests.post(
            f"{UPLOAD_URL}/v1/asset",
            headers={**HEADERS, "Content-Type": content_type},
            data=f.read(),
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("id") or data.get("id")


def create_photo_avatar(photo_path, name="Custom Avatar"):
    """
    Create a photo avatar from an uploaded image.
    Returns {avatar_id, group_id, status}.
    """
    # Step 1: upload the image
    asset_id = upload_asset(photo_path, asset_type="image")

    # Step 2: create photo avatar group
    resp = requests.post(
        f"{BASE_URL}/v2/photo_avatar/photo/generate",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"name": name, "image_key": asset_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def list_avatars():
    """List available avatars (includes stock + your custom ones)."""
    resp = requests.get(f"{BASE_URL}/v2/avatars", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {})


def list_voices():
    """List available voices."""
    resp = requests.get(f"{BASE_URL}/v2/voices", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {})


def generate_video(
    avatar_id,
    script,
    voice_id=None,
    width=1920,
    height=1080,
    background_color="#FFFFFF",
):
    """
    Generate a video using an avatar + script.
    Returns video_id (used to poll status).
    """
    voice_obj = {"type": "text", "input_text": script}
    if voice_id:
        voice_obj["voice_id"] = voice_id

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": voice_obj,
                "background": {"type": "color", "value": background_color},
            }
        ],
        "dimension": {"width": width, "height": height},
    }

    resp = requests.post(
        f"{BASE_URL}/v2/video/generate",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("video_id")


def get_video_status(video_id):
    """Check status of a video generation. Returns dict with status + video_url."""
    resp = requests.get(
        f"{BASE_URL}/v1/video_status.get",
        headers=HEADERS,
        params={"video_id": video_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def wait_for_video(video_id, max_wait=600, poll_interval=10):
    """Poll until video is ready. Returns video URL."""
    elapsed = 0
    while elapsed < max_wait:
        status_data = get_video_status(video_id)
        status = status_data.get("status", "")
        print(f"[{elapsed}s] HeyGen status: {status}")

        if status == "completed":
            return status_data.get("video_url")
        if status == "failed":
            raise RuntimeError(f"HeyGen video failed: {status_data.get('error', {})}")

        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"HeyGen video not ready after {max_wait}s")


def download_video(url, output_path):
    """Download a finished video from HeyGen's CDN."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


def check_remaining_credits():
    """Get your remaining HeyGen credits."""
    resp = requests.get(f"{BASE_URL}/v2/user/remaining_quota", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {})


if __name__ == "__main__":
    # Smoke test
    print("=== HeyGen API Smoke Test ===")
    try:
        credits = check_remaining_credits()
        print(f"Remaining credits: {credits}")
    except Exception as e:
        print(f"Credit check failed: {e}")

    try:
        voices = list_voices()
        voice_list = voices.get("voices", [])
        print(f"Available voices: {len(voice_list)}")
        if voice_list:
            print(f"First voice: {voice_list[0].get('name')} ({voice_list[0].get('voice_id')})")
    except Exception as e:
        print(f"Voice list failed: {e}")

    try:
        avatars = list_avatars()
        avatar_list = avatars.get("avatars", [])
        print(f"Available avatars: {len(avatar_list)}")
    except Exception as e:
        print(f"Avatar list failed: {e}")
