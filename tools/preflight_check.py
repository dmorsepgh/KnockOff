#!/usr/bin/env python3
"""
Pre-flight Check - Validates video script and assets before generation.

Prevents crashes by checking:
- Script syntax and markers
- File existence (avatar, B-roll, overlays, music)
- Chunk boundary issues (overlays crossing 20s boundaries)
- Avatar video quality
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
AVATAR_DIR = PROJECT_ROOT / "avatars"
BROLL_DIR = PROJECT_ROOT / "broll"
OVERLAY_DIR = PROJECT_ROOT / "overlays"
MUSIC_DIR = PROJECT_ROOT / "music"

# Import script parser
sys.path.insert(0, str(Path(__file__).parent))
from parse_script import parse_script

class PreflightError:
    def __init__(self, severity: str, message: str, fix: str = ""):
        self.severity = severity  # ERROR, WARNING, INFO
        self.message = message
        self.fix = fix

def check_script_file(script_path: Path) -> List[PreflightError]:
    """Check if script file exists and is readable."""
    errors = []

    if not script_path.exists():
        errors.append(PreflightError(
            "ERROR",
            f"Script file not found: {script_path}",
            "Create the script file or check the path"
        ))
        return errors

    try:
        script_text = script_path.read_text()
        if not script_text.strip():
            errors.append(PreflightError(
                "ERROR",
                "Script file is empty",
                "Add content to your script"
            ))
    except Exception as e:
        errors.append(PreflightError(
            "ERROR",
            f"Cannot read script file: {e}",
            "Check file permissions"
        ))

    return errors

def check_avatar(avatar_name: str) -> List[PreflightError]:
    """Check if avatar video exists."""
    errors = []

    avatar_path = AVATAR_DIR / f"{avatar_name}.mp4"
    if not avatar_path.exists():
        # Try without extension
        avatar_path = AVATAR_DIR / avatar_name
        if not avatar_path.exists():
            errors.append(PreflightError(
                "ERROR",
                f"Avatar video not found: {avatar_name}",
                f"Record avatar video and save to {AVATAR_DIR}/{avatar_name}.mp4"
            ))
            return errors

    # Check file size
    size_mb = avatar_path.stat().st_size / (1024 * 1024)
    if size_mb < 0.1:
        errors.append(PreflightError(
            "WARNING",
            f"Avatar file is very small ({size_mb:.2f}MB) - may be corrupted",
            "Re-record avatar video"
        ))

    return errors

def check_broll_overlays(script_text: str) -> List[PreflightError]:
    """Check if all B-roll and overlay files exist."""
    errors = []

    # Find all [BROLL: filename | duration] markers
    broll_pattern = r'\[BROLL:\s*([^\|\]]+)'
    for match in re.finditer(broll_pattern, script_text, re.IGNORECASE):
        filename = match.group(1).strip()
        broll_path = BROLL_DIR / filename

        if not broll_path.exists():
            errors.append(PreflightError(
                "ERROR",
                f"B-roll file not found: {filename}",
                f"Capture B-roll footage and save to {BROLL_DIR}/{filename}"
            ))

    # Find all [OVERLAY: filename | duration] markers
    overlay_pattern = r'\[OVERLAY:\s*([^\|\]]+)'
    for match in re.finditer(overlay_pattern, script_text, re.IGNORECASE):
        filename = match.group(1).strip()
        overlay_path = OVERLAY_DIR / filename

        # Also check in broll folder
        if not overlay_path.exists():
            overlay_path = BROLL_DIR / filename
            if not overlay_path.exists():
                errors.append(PreflightError(
                    "ERROR",
                    f"Overlay file not found: {filename}",
                    f"Create overlay graphic and save to {OVERLAY_DIR}/{filename}"
                ))

    # Find all [MUSIC: filename | volume] markers
    music_pattern = r'\[MUSIC:\s*([^\|\]]+)'
    for match in re.finditer(music_pattern, script_text, re.IGNORECASE):
        filename = match.group(1).strip()
        music_path = MUSIC_DIR / filename

        if not music_path.exists():
            errors.append(PreflightError(
                "WARNING",
                f"Music file not found: {filename}",
                f"Add music track to {MUSIC_DIR}/{filename} or remove [MUSIC] marker"
            ))

    return errors

def estimate_speech_duration(text: str) -> float:
    """Rough estimate of speech duration (words per minute)."""
    words = len(text.split())
    wpm = 150  # Average speaking rate
    return (words / wpm) * 60

def check_chunk_boundaries(script_text: str) -> List[PreflightError]:
    """Check if overlays/B-roll cross chunk boundaries (dangerous!)."""
    errors = []

    CHUNK_SIZE = 20.0  # seconds

    try:
        segments, _ = parse_script(script_text)

        current_time = 0.0
        speech_segments = [s for s in segments if s.type == "speech"]

        for i, seg in enumerate(segments):
            if seg.type == "speech":
                # Estimate duration of this speech
                duration = estimate_speech_duration(seg.content)
                current_time += duration

            elif seg.type in ("broll", "overlay"):
                # Check if this visual crosses a chunk boundary
                duration = seg.duration or 5.0  # default 5s
                chunk_start = int(current_time / CHUNK_SIZE)
                chunk_end = int((current_time + duration) / CHUNK_SIZE)

                if chunk_end > chunk_start:
                    errors.append(PreflightError(
                        "WARNING",
                        f"{seg.type.upper()} at ~{current_time:.0f}s crosses chunk boundary",
                        f"Keep {seg.type} duration under {CHUNK_SIZE - (current_time % CHUNK_SIZE):.0f}s or move it earlier/later in script"
                    ))

                if duration > 15:
                    errors.append(PreflightError(
                        "WARNING",
                        f"{seg.type.upper()} duration ({duration}s) is long - may cause issues",
                        "Keep overlays/B-roll under 15s for reliability"
                    ))

    except Exception as e:
        errors.append(PreflightError(
            "WARNING",
            f"Could not analyze chunk boundaries: {e}",
            ""
        ))

    return errors

def print_report(errors: List[PreflightError]) -> bool:
    """Print preflight report. Returns True if safe to proceed."""

    error_count = sum(1 for e in errors if e.severity == "ERROR")
    warning_count = sum(1 for e in errors if e.severity == "WARNING")

    print("=" * 80)
    print("KNOCKOFF PRE-FLIGHT CHECK")
    print("=" * 80)

    if not errors:
        print("\n✅ ALL CHECKS PASSED - Ready to generate video!\n")
        return True

    # Print errors first
    for error in errors:
        if error.severity == "ERROR":
            print(f"\n❌ ERROR: {error.message}")
            if error.fix:
                print(f"   FIX: {error.fix}")

    # Then warnings
    for error in errors:
        if error.severity == "WARNING":
            print(f"\n⚠️  WARNING: {error.message}")
            if error.fix:
                print(f"   FIX: {error.fix}")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {error_count} errors, {warning_count} warnings")
    print("=" * 80)

    if error_count > 0:
        print("\n❌ CANNOT PROCEED - Fix errors above before generating video\n")
        return False
    else:
        print("\n⚠️  You can proceed, but warnings should be addressed\n")
        return True

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight check for KnockOff video generation")
    parser.add_argument("--script", "-s", type=Path, required=True, help="Path to script file")
    parser.add_argument("--avatar", "-a", required=True, help="Avatar name")

    args = parser.parse_args()

    # Run all checks
    all_errors = []

    all_errors.extend(check_script_file(args.script))

    if args.script.exists():
        script_text = args.script.read_text()
        all_errors.extend(check_broll_overlays(script_text))
        all_errors.extend(check_chunk_boundaries(script_text))

    all_errors.extend(check_avatar(args.avatar))

    # Print report
    can_proceed = print_report(all_errors)

    if not can_proceed:
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
