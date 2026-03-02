#!/usr/bin/env python3
"""
Sync Labs API Integration - Commercial lip-sync for video inputs.

MIT-style usage - commercial OK.
Pricing: ~$3/min (standard) or ~$5/min (pro)

Usage:
    from sync_labs import lipsync_video

    result = lipsync_video(
        video_path="avatar.mp4",
        audio_path="speech.wav",
        output_path="synced.mp4"
    )
"""

import os
import requests
import time
from pathlib import Path

# API Configuration
SYNC_LABS_API_KEY = os.environ.get("SYNC_LABS_API_KEY", "")
SYNC_LABS_API_URL = "https://api.synclabs.so/lipsync"

def get_api_key():
    """Get API key from environment or config file."""
    if SYNC_LABS_API_KEY:
        return SYNC_LABS_API_KEY

    # Check config file
    config_path = Path(__file__).parent.parent / ".env"
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.startswith("SYNC_LABS_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise ValueError("SYNC_LABS_API_KEY not set. Add to .env file or environment.")


def upload_file(file_path: Path, api_key: str) -> str:
    """Upload file to Sync Labs and return URL."""
    # Sync Labs accepts direct file uploads or URLs
    # For now, we'll use their upload endpoint
    headers = {"x-api-key": api_key}

    with open(file_path, "rb") as f:
        response = requests.post(
            "https://api.synclabs.so/upload",
            headers=headers,
            files={"file": f}
        )

    if response.status_code != 200:
        raise Exception(f"Upload failed: {response.text}")

    return response.json()["url"]


def lipsync_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    model: str = "lipsync-2",  # or "lipsync-2-pro"
    webhook_url: str = None
) -> Path:
    """
    Sync lips in video to match audio using Sync Labs API.

    Args:
        video_path: Input video with face
        audio_path: Audio to sync to
        output_path: Where to save result
        model: "lipsync-2" (faster, $3/min) or "lipsync-2-pro" (better, $5/min)
        webhook_url: Optional webhook for completion notification

    Returns:
        Path to synced video
    """
    api_key = get_api_key()
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    print(f"Uploading video to Sync Labs...")
    video_url = upload_file(video_path, api_key)

    print(f"Uploading audio to Sync Labs...")
    audio_url = upload_file(audio_path, api_key)

    # Submit lip-sync job
    print(f"Submitting lip-sync job (model: {model})...")
    payload = {
        "videoUrl": video_url,
        "audioUrl": audio_url,
        "model": model,
        "synergize": True,  # Improve quality
    }

    if webhook_url:
        payload["webhookUrl"] = webhook_url

    response = requests.post(
        f"{SYNC_LABS_API_URL}",
        headers=headers,
        json=payload
    )

    if response.status_code != 201:
        raise Exception(f"Lip-sync submission failed: {response.text}")

    job_id = response.json()["id"]
    print(f"Job submitted: {job_id}")

    # Poll for completion
    print("Waiting for processing...")
    while True:
        status_response = requests.get(
            f"{SYNC_LABS_API_URL}/{job_id}",
            headers=headers
        )

        status = status_response.json()
        state = status.get("status")

        if state == "COMPLETED":
            result_url = status["videoUrl"]
            break
        elif state == "FAILED":
            raise Exception(f"Lip-sync failed: {status.get('error')}")
        else:
            print(f"  Status: {state}...")
            time.sleep(5)

    # Download result
    print(f"Downloading result...")
    video_response = requests.get(result_url)
    output_path.write_bytes(video_response.content)

    print(f"Lip-synced video saved: {output_path}")
    return output_path


def estimate_cost(video_path: Path, model: str = "lipsync-2") -> dict:
    """Estimate cost before processing."""
    api_key = get_api_key()
    headers = {"x-api-key": api_key}

    # Get video duration
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())

    # Estimate based on pricing
    rate = 5.0 if model == "lipsync-2-pro" else 3.0
    cost = (duration / 60) * rate

    return {
        "duration_seconds": duration,
        "model": model,
        "estimated_cost": f"${cost:.2f}"
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync Labs lip-sync")
    parser.add_argument("video", type=Path, help="Input video")
    parser.add_argument("audio", type=Path, help="Audio to sync")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--model", default="lipsync-2", choices=["lipsync-2", "lipsync-2-pro"])
    parser.add_argument("--estimate", action="store_true", help="Just estimate cost")

    args = parser.parse_args()

    if args.estimate:
        est = estimate_cost(args.video, args.model)
        print(f"Duration: {est['duration_seconds']:.1f}s")
        print(f"Model: {est['model']}")
        print(f"Estimated cost: {est['estimated_cost']}")
    else:
        lipsync_video(args.video, args.audio, args.output, args.model)
