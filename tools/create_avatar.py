#!/usr/bin/env python3
"""
Avatar Creator - Generate animated talking head videos from photos using LivePortrait.

Usage:
    # From a photo (uses default driving video for natural head movement)
    python tools/create_avatar.py --photo path/to/photo.jpg --name client-name

    # From a photo with custom driving video (copies head movements)
    python tools/create_avatar.py --photo path/to/photo.jpg --driving path/to/driving.mp4 --name client-name

    # List existing avatars
    python tools/create_avatar.py --list
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
AVATARS_DIR = PROJECT_ROOT / "avatars"
LIVEPORTRAIT_DIR = Path.home() / "LivePortrait"
LIVEPORTRAIT_PYTHON = LIVEPORTRAIT_DIR / ".venv" / "bin" / "python3"

# Default driving video for natural head movement
DEFAULT_DRIVING = AVATARS_DIR / "dmpgh-2.mp4"


def list_avatars():
    """List available avatars."""
    print("\nAvailable avatars:")
    print("-" * 40)
    for f in sorted(AVATARS_DIR.glob("*.mp4")):
        size_mb = f.stat().st_size / (1024 * 1024)
        status = "OK" if size_mb > 0.01 else "BROKEN"
        print(f"  {f.stem:30s} {size_mb:6.1f} MB  {status}")

    print("\nAvailable photos (for avatar creation):")
    print("-" * 40)
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
        for f in sorted(AVATARS_DIR.glob(ext)):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:30s} {size_kb:6.1f} KB")


def create_avatar(photo_path: Path, name: str, driving_path: Path = None):
    """Create an animated avatar video from a photo using LivePortrait."""

    if not LIVEPORTRAIT_DIR.exists():
        raise FileNotFoundError(f"LivePortrait not found at {LIVEPORTRAIT_DIR}")
    if not LIVEPORTRAIT_PYTHON.exists():
        raise FileNotFoundError(f"LivePortrait venv not found at {LIVEPORTRAIT_PYTHON}")
    if not photo_path.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    driving = driving_path or DEFAULT_DRIVING
    if not driving.exists():
        raise FileNotFoundError(f"Driving video not found: {driving}")

    output_name = f"{name}.mp4"
    output_path = AVATARS_DIR / output_name

    print(f"Creating avatar '{name}' from {photo_path.name}...")
    print(f"  Source photo:   {photo_path}")
    print(f"  Driving video:  {driving}")
    print(f"  Output:         {output_path}")
    print()

    # Run LivePortrait
    env = os.environ.copy()
    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

    cmd = [
        str(LIVEPORTRAIT_PYTHON),
        str(LIVEPORTRAIT_DIR / "inference.py"),
        "-s", str(photo_path.resolve()),
        "-d", str(driving.resolve()),
        "--flag_pasteback",
    ]

    print("Running LivePortrait (this may take a few minutes on CPU)...")
    result = subprocess.run(cmd, cwd=str(LIVEPORTRAIT_DIR), env=env,
                            capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: LivePortrait failed:\n{result.stderr}")
        sys.exit(1)

    # Find the output file
    animations_dir = LIVEPORTRAIT_DIR / "animations"
    photo_stem = photo_path.stem
    driving_stem = driving.stem

    # LivePortrait names output as: {source}--{driving}.mp4
    expected = animations_dir / f"{photo_stem}--{driving_stem}.mp4"

    if not expected.exists():
        # Try to find any matching output
        candidates = list(animations_dir.glob(f"{photo_stem}--*.mp4"))
        candidates = [c for c in candidates if "concat" not in c.name]
        if candidates:
            expected = candidates[0]
        else:
            print(f"ERROR: Could not find output video in {animations_dir}")
            print(f"LivePortrait stdout: {result.stdout}")
            sys.exit(1)

    # Copy to avatars directory
    shutil.copy2(expected, output_path)
    print(f"\nAvatar created: {output_path}")
    print(f"Size: {output_path.stat().st_size / (1024*1024):.1f} MB")
    print(f"\nUse it with: python tools/generate_avatar_video.py \"Your script\" --avatar {name}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Create animated avatars from photos")
    parser.add_argument("--photo", type=Path, help="Path to source photo")
    parser.add_argument("--driving", type=Path, help="Path to driving video (optional)")
    parser.add_argument("--name", type=str, help="Name for the avatar")
    parser.add_argument("--list", action="store_true", help="List available avatars")

    args = parser.parse_args()

    if args.list:
        list_avatars()
        return

    if not args.photo:
        parser.error("--photo is required (or use --list)")
    if not args.name:
        # Default name from photo filename
        args.name = args.photo.stem

    create_avatar(args.photo, args.name, args.driving)


if __name__ == "__main__":
    main()
