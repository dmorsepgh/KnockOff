#!/usr/bin/env python3
"""
Script-to-YouTube Pipeline

Takes a script file or text input, generates video with KnockOff,
and uploads to YouTube automatically.

Usage:
    # From script file
    python tools/script_to_youtube.py --script docs/explainer.md --title "AI Tips"

    # From text
    python tools/script_to_youtube.py "Your video script here" --title "Quick Tip"

    # Generate video only (no upload)
    python tools/script_to_youtube.py --script docs/my-script.md --no-upload

    # With all options
    python tools/script_to_youtube.py --script docs/script.md \
        --title "My Video Title" \
        --avatar doug \
        --voice doug \
        --format portrait \
        --short
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
YOUTUBE_MANAGER = Path.home() / "Projects/ai-education-business/tools/youtube_manager.py"

def generate_video(script_text: str = None, script_file: str = None,
                   avatar: str = "doug", voice: str = "doug",
                   video_format: str = "portrait", output_path: str = None) -> Path:
    """Generate video using KnockOff."""

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = PROJECT_ROOT / ".tmp" / "avatar" / "output" / f"video-{timestamp}.mp4"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "tools" / "generate_avatar_video.py"),
        "--avatar", avatar,
        "--voice", voice,
        "--format", video_format,
        "--output", str(output_path)
    ]

    if script_file:
        cmd.extend(["--script", script_file])
    elif script_text:
        cmd.append(script_text)
    else:
        raise ValueError("Either script_text or script_file required")

    print(f"\n🎬 Generating video...")
    print(f"   Avatar: {avatar}")
    print(f"   Voice: {voice}")
    print(f"   Format: {video_format}")

    result = subprocess.run(cmd, capture_output=False, text=True, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        raise RuntimeError(f"Video generation failed with code {result.returncode}")

    if not output_path.exists():
        raise RuntimeError(f"Video not found at {output_path}")

    print(f"✅ Video generated: {output_path}")
    return output_path


def upload_to_youtube(video_path: Path, title: str, description: str = None,
                      is_short: bool = False, public: bool = False) -> dict:
    """Upload video to YouTube using youtube_manager.py."""

    if not YOUTUBE_MANAGER.exists():
        raise FileNotFoundError(f"YouTube manager not found at {YOUTUBE_MANAGER}")

    cmd = [
        sys.executable,
        str(YOUTUBE_MANAGER),
        "upload",
        str(video_path),
        title
    ]

    if is_short:
        cmd.append("--short")

    if public:
        cmd.append("--public")

    if description:
        cmd.extend(["--description", description])

    print(f"\n📤 Uploading to YouTube...")
    print(f"   Title: {title}")
    print(f"   Short: {is_short}")
    print(f"   Public: {public}")

    # Need to run from the youtube_manager's directory for OAuth
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(YOUTUBE_MANAGER.parent.parent)
    )

    if result.returncode != 0:
        print(f"❌ Upload failed: {result.stderr}")
        raise RuntimeError(f"YouTube upload failed: {result.stderr}")

    # Parse video URL from output
    output = result.stdout
    print(output)

    # Look for video ID in output
    for line in output.split('\n'):
        if 'youtube.com/watch' in line or 'Video ID:' in line:
            print(f"✅ {line.strip()}")

    return {"success": True, "output": output}


def main():
    parser = argparse.ArgumentParser(description="Script-to-YouTube Pipeline")
    parser.add_argument("text", nargs="?", help="Script text (or use --script)")
    parser.add_argument("--script", "-s", help="Path to script file")
    parser.add_argument("--title", "-t", required=True, help="YouTube video title")
    parser.add_argument("--description", "-d", help="YouTube description")
    parser.add_argument("--avatar", "-a", default="doug", help="Avatar name (default: doug)")
    parser.add_argument("--voice", "-v", default="doug", help="Voice name (default: doug)")
    parser.add_argument("--format", "-f", default="portrait",
                        choices=["portrait", "landscape", "square"],
                        help="Video format (default: portrait)")
    parser.add_argument("--output", "-o", help="Output video path")
    parser.add_argument("--short", action="store_true", help="Mark as YouTube Short")
    parser.add_argument("--public", action="store_true", help="Make video public (default: unlisted)")
    parser.add_argument("--no-upload", action="store_true", help="Generate video only, don't upload")

    args = parser.parse_args()

    if not args.text and not args.script:
        parser.error("Either provide text argument or use --script")

    try:
        # Step 1: Generate video
        video_path = generate_video(
            script_text=args.text,
            script_file=args.script,
            avatar=args.avatar,
            voice=args.voice,
            video_format=args.format,
            output_path=args.output
        )

        # Step 2: Upload to YouTube (unless --no-upload)
        if not args.no_upload:
            upload_to_youtube(
                video_path=video_path,
                title=args.title,
                description=args.description,
                is_short=args.short,
                public=args.public
            )
            print(f"\n🎉 Pipeline complete! Video uploaded to YouTube.")
        else:
            print(f"\n✅ Video ready at: {video_path}")
            print("   (Skipped upload due to --no-upload)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
