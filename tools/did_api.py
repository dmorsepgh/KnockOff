#!/usr/bin/env python3
"""
D-ID API Integration - Animate photos to talking videos.

Commercial license via API subscription.
Pricing: ~$0.50-1 per minute

Usage:
    from did_api import animate_photo

    result = animate_photo(
        image_path="avatar.jpg",
        audio_path="speech.wav",
        output_path="talking.mp4"
    )
"""

import os
import requests
import time
import base64
from pathlib import Path

# API Configuration
DID_API_KEY = os.environ.get("DID_API_KEY", "")
DID_API_URL = "https://api.d-id.com"


def get_api_key():
    """Get API key from environment or config file."""
    if DID_API_KEY:
        return DID_API_KEY

    # Check config file
    config_path = Path(__file__).parent.parent / ".env"
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.startswith("DID_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise ValueError("DID_API_KEY not set. Add to .env file or environment.")


def image_to_base64(image_path: Path) -> str:
    """Convert image to base64 data URL."""
    suffix = image_path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif"
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return f"data:{mime_type};base64,{data}"


def upload_audio(audio_path: Path, api_key: str) -> str:
    """Upload audio to D-ID and return URL."""
    headers = {
        "Authorization": f"Basic {api_key}",
    }

    with open(audio_path, "rb") as f:
        response = requests.post(
            f"{DID_API_URL}/audios",
            headers=headers,
            files={"audio": (audio_path.name, f, "audio/wav")}
        )

    if response.status_code not in [200, 201]:
        raise Exception(f"Audio upload failed: {response.text}")

    return response.json()["url"]


def animate_photo(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    driver_url: str = None,  # Optional: custom driver video for expressions
    expression: str = "neutral",  # neutral, happy, serious
    stitch: bool = True,  # Stitch result seamlessly
) -> Path:
    """
    Animate a still photo to speak using D-ID API.

    Args:
        image_path: Photo with face to animate
        audio_path: Audio for the avatar to speak
        output_path: Where to save result video
        driver_url: Optional custom driver for expressions
        expression: Base expression (neutral, happy, serious)
        stitch: Whether to stitch for seamless result

    Returns:
        Path to animated video
    """
    api_key = get_api_key()
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }

    # Upload audio first
    print("Uploading audio to D-ID...")
    audio_url = upload_audio(audio_path, api_key)

    # Convert image to base64
    print("Preparing image...")
    image_data = image_to_base64(image_path)

    # Create talk request
    print("Submitting animation job...")
    payload = {
        "source_url": image_data,
        "script": {
            "type": "audio",
            "audio_url": audio_url
        },
        "config": {
            "stitch": stitch,
            "result_format": "mp4"
        }
    }

    if driver_url:
        payload["driver_url"] = driver_url

    response = requests.post(
        f"{DID_API_URL}/talks",
        headers=headers,
        json=payload
    )

    if response.status_code not in [200, 201]:
        raise Exception(f"Animation submission failed: {response.text}")

    talk_id = response.json()["id"]
    print(f"Job submitted: {talk_id}")

    # Poll for completion
    print("Waiting for processing...")
    while True:
        status_response = requests.get(
            f"{DID_API_URL}/talks/{talk_id}",
            headers=headers
        )

        status = status_response.json()
        state = status.get("status")

        if state == "done":
            result_url = status["result_url"]
            break
        elif state == "error":
            raise Exception(f"Animation failed: {status.get('error')}")
        else:
            print(f"  Status: {state}...")
            time.sleep(3)

    # Download result
    print("Downloading result...")
    video_response = requests.get(result_url)
    output_path.write_bytes(video_response.content)

    print(f"Animated video saved: {output_path}")
    return output_path


def list_voices() -> list:
    """List available D-ID voices for text-to-speech."""
    api_key = get_api_key()
    headers = {"Authorization": f"Basic {api_key}"}

    response = requests.get(
        f"{DID_API_URL}/tts/voices",
        headers=headers
    )

    return response.json()


def animate_with_text(
    image_path: Path,
    text: str,
    output_path: Path,
    voice_id: str = "en-US-JennyNeural",  # Microsoft voice
    stitch: bool = True
) -> Path:
    """
    Animate a photo with text-to-speech (no separate audio needed).

    Args:
        image_path: Photo with face
        text: Text for the avatar to speak
        output_path: Where to save result
        voice_id: D-ID voice ID
        stitch: Seamless stitching

    Returns:
        Path to animated video
    """
    api_key = get_api_key()
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }

    image_data = image_to_base64(image_path)

    print("Submitting text-to-video job...")
    payload = {
        "source_url": image_data,
        "script": {
            "type": "text",
            "input": text,
            "provider": {
                "type": "microsoft",
                "voice_id": voice_id
            }
        },
        "config": {
            "stitch": stitch,
            "result_format": "mp4"
        }
    }

    response = requests.post(
        f"{DID_API_URL}/talks",
        headers=headers,
        json=payload
    )

    if response.status_code not in [200, 201]:
        raise Exception(f"Submission failed: {response.text}")

    talk_id = response.json()["id"]
    print(f"Job submitted: {talk_id}")

    # Poll for completion
    while True:
        status_response = requests.get(
            f"{DID_API_URL}/talks/{talk_id}",
            headers=headers
        )

        status = status_response.json()
        state = status.get("status")

        if state == "done":
            result_url = status["result_url"]
            break
        elif state == "error":
            raise Exception(f"Failed: {status.get('error')}")
        else:
            print(f"  Status: {state}...")
            time.sleep(3)

    # Download
    video_response = requests.get(result_url)
    output_path.write_bytes(video_response.content)

    print(f"Video saved: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="D-ID photo animation")
    parser.add_argument("image", type=Path, help="Photo to animate")
    parser.add_argument("--audio", type=Path, help="Audio file")
    parser.add_argument("--text", type=str, help="Text to speak (uses D-ID TTS)")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--voice", default="en-US-JennyNeural")

    args = parser.parse_args()

    if args.audio:
        animate_photo(args.image, args.audio, args.output)
    elif args.text:
        animate_with_text(args.image, args.text, args.output, args.voice)
    else:
        parser.error("Must provide --audio or --text")
