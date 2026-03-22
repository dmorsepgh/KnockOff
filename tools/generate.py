#!/usr/bin/env python3
"""
KnockOff Generator - Orchestrate parse → TTS → lipsync → assemble.

Usage:
    python tools/generate.py --script scripts/test.md --avatar doug
    python tools/generate.py "Hello world" --avatar doug
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add tools/ to path so sibling modules import cleanly
sys.path.insert(0, str(Path(__file__).parent))

from parse_script import parse_script_file, parse_script, get_full_speech_text
from tts import generate_audio
from lipsync import run_lipsync
from assembler import assemble

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
AVATARS_DIR = PROJECT_ROOT / "avatars"
TMP_DIR = PROJECT_ROOT / ".tmp"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _step(name: str):
    """Context manager-style timer for logging steps."""
    class Timer:
        def __enter__(self):
            self.start = time.time()
            logger.info(f"\n[{name}]")
            return self
        def __exit__(self, *_):
            elapsed = time.time() - self.start
            logger.info(f"  ✓ {name} done ({elapsed:.1f}s)")
    return Timer()


def generate(
    script_path: Path | None,
    script_text: str | None,
    avatar: str,
    voice: str = "joe",
    quality: str = "Improved",
    format: str = "portrait",
) -> Path:
    """
    Full generation pipeline.

    Args:
        script_path: Path to .md script file (or None if script_text given)
        script_text: Inline script text (or None if script_path given)
        avatar: Avatar name (e.g. "doug" → avatars/doug.mp4)
        voice: Piper voice name ("joe" or "lessac")
        quality: Wav2Lip quality ("Fast", "Improved", "Enhanced")
        format: Output format ("portrait", "landscape", "square")

    Returns:
        Path to the final video
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = TMP_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    total_start = time.time()
    logger.info(f"KnockOff generate — run {run_id}")
    logger.info(f"  avatar={avatar}  voice={voice}  quality={quality}  format={format}")

    # --- Resolve avatar ---
    avatar_path = AVATARS_DIR / f"{avatar}.mp4"
    if not avatar_path.exists():
        raise FileNotFoundError(f"Avatar not found: {avatar_path}")

    # --- Parse script ---
    with _step("Parse script"):
        if script_path:
            segments, music_track = parse_script_file(script_path)
            logger.info(f"  Script: {script_path.name}")
        else:
            segments, music_track = parse_script(script_text)

        speech_text = get_full_speech_text(segments)
        logger.info(f"  {len(segments)} segments, {len(speech_text)} chars of speech")

        if not speech_text.strip():
            raise ValueError("Script has no speech text")

    # --- TTS ---
    audio_path = run_dir / "speech.wav"
    with _step("TTS"):
        generate_audio(speech_text, audio_path, voice=voice)
        logger.info(f"  Output: {audio_path.name}")

    # --- Lip sync ---
    lipsync_path = run_dir / "lipsync.mp4"
    with _step("Lip sync"):
        run_lipsync(avatar_path, audio_path, lipsync_path, quality=quality)
        logger.info(f"  Output: {lipsync_path.name}")

    # --- Assemble ---
    # Build a human-readable output filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    if script_path:
        slug = script_path.stem[:60]
    else:
        slug = "_".join(speech_text.split()[:6])[:60]
        slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in slug).strip().replace(" ", "-")
    output_path = OUTPUT_DIR / date_str / f"{slug}__{avatar}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _step("Assemble"):
        assemble(lipsync_path, segments, output_path, music_track=music_track, format=format)
        logger.info(f"  Output: {output_path}")

    total = time.time() - total_start
    logger.info(f"\nDone in {total:.1f}s → {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="KnockOff video generator")
    parser.add_argument("inline", nargs="?", help="Inline script text (quick one-liner)")
    parser.add_argument("--script", type=Path, help="Path to .md script file")
    parser.add_argument("--avatar", required=True, help="Avatar name (e.g. doug)")
    parser.add_argument("--voice", default="joe", choices=["joe", "lessac"])
    parser.add_argument("--quality", default="Improved", choices=["Fast", "Improved", "Enhanced"])
    parser.add_argument("--format", default="portrait", choices=["portrait", "landscape", "square"])
    parser.add_argument("--open", action="store_true", help="Open output video when done")
    args = parser.parse_args()

    if not args.inline and not args.script:
        parser.error("Provide either an inline script or --script path")
    if args.inline and args.script:
        parser.error("Provide either inline text or --script, not both")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output = generate(
        script_path=args.script,
        script_text=args.inline,
        avatar=args.avatar,
        voice=args.voice,
        quality=args.quality,
        format=args.format,
    )

    print(f"\nOutput: {output}")

    if args.open:
        import subprocess
        subprocess.run(["open", str(output)])


if __name__ == "__main__":
    main()
