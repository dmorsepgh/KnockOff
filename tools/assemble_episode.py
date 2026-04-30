#!/usr/bin/env python3
"""
Assemble Episode — Full AI Views and News episode assembly.

Takes Pictory story videos + episode metadata, generates opening/closing
locally with KnockOff (TTS + Wav2Lip), adds bumpers, stitches everything.

Usage:
    # Auto from episode.json
    python tools/assemble_episode.py --episode 4

    # Manual with files
    python tools/assemble_episode.py --date 2026-04-01 \
        --stories story1.mp4 story2.mp4 story3.mp4

    # With pre-made opening/closing (skip local generation)
    python tools/assemble_episode.py --episode 4 \
        --opening opening.mp4 --closing closing.mp4
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"
WEBSITE_DIR = Path.home() / "myaibiweekly"
AVATAR = PROJECT_ROOT / "avatars" / "dmpgh-3.mp4"
AVATAR_PKL = PROJECT_ROOT / "avatars" / "dmpgh-3.pkl"
PIPER_MODEL = PROJECT_ROOT / "models" / "piper" / "en_US-joe-medium.onnx"
WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
WAV2LIP_PYTHON = WAV2LIP_DIR / ".venv" / "bin" / "python3"
INTRO_BUMPER = None  # Will search show dirs
CREDITS_BUMPER = None

# Standard output specs
SPECS = {
    "fps": "30",
    "resolution": "1920:1080",
    "crf": "20",
    "audio_bitrate": "192k",
    "audio_rate": "48000",
    "audio_channels": "2",
}

CROSSFADE_DURATION = 1.0  # seconds


def find_bumpers():
    """Find intro and credits bumpers from existing episodes."""
    global INTRO_BUMPER, CREDITS_BUMPER
    for ep_dir in sorted(SHOW_DIR.glob("ep*"), reverse=True):
        intro = ep_dir / "intro-bumper.mp4"
        credits = ep_dir / "credits-bumper.mp4"
        if intro.exists() and INTRO_BUMPER is None:
            INTRO_BUMPER = intro
        if credits.exists() and CREDITS_BUMPER is None:
            CREDITS_BUMPER = credits
        if INTRO_BUMPER and CREDITS_BUMPER:
            break


def normalize_clip(input_path, output_path):
    """Normalize a video clip to standard specs."""
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"fps={SPECS['fps']},scale={SPECS['resolution']}",
        "-c:v", "libx264", "-preset", "medium", "-crf", SPECS["crf"],
        "-c:a", "aac", "-b:a", SPECS["audio_bitrate"],
        "-ar", SPECS["audio_rate"], "-ac", SPECS["audio_channels"],
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    return output_path.exists()


def get_duration(path):
    """Get video duration in seconds."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def crossfade_concat(segments, output_path, fade_duration=None):
    """Concatenate segments with crossfade transitions using pairwise chaining."""
    if fade_duration is None:
        fade_duration = CROSSFADE_DURATION

    if len(segments) < 2:
        import shutil
        shutil.copy2(segments[0], output_path)
        return output_path.exists()

    # Chain pairwise: crossfade 0+1 -> tmp1, then tmp1+2 -> tmp2, etc.
    current = segments[0]
    tmpdir = output_path.parent

    for i in range(1, len(segments)):
        next_seg = segments[i]
        dur = get_duration(current)
        offset = dur - fade_duration

        if i < len(segments) - 1:
            out = tmpdir / f"_xfade_step_{i}.mp4"
        else:
            out = output_path

        cmd = [
            "ffmpeg", "-y",
            "-i", str(current), "-i", str(next_seg),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}[v];"
            f"[0:a][1:a]acrossfade=d={fade_duration}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", SPECS["crf"],
            "-c:a", "aac", "-b:a", SPECS["audio_bitrate"],
            "-pix_fmt", "yuv420p",
            str(out)
        ]

        print(f"    Crossfade {i}/{len(segments)-1}: offset={offset:.1f}s")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if not out.exists():
            print(f"  Crossfade error at step {i}: {result.stderr[-300:] if result.stderr else 'unknown'}")
            return False

        # Clean up previous temp
        if i > 1:
            prev_tmp = tmpdir / f"_xfade_step_{i-1}.mp4"
            prev_tmp.unlink(missing_ok=True)

        current = out

    return output_path.exists()


def generate_tts(text, output_wav):
    """Generate speech with Piper TTS."""
    cmd = ["piper", "--model", str(PIPER_MODEL), "--output_file", str(output_wav)]
    result = subprocess.run(cmd, input=text.encode(), capture_output=True)
    return output_wav.exists()


def generate_lipsync(avatar_path, audio_path, output_path):
    """Run Wav2Lip to create lip-synced avatar video."""
    # Get audio duration to loop avatar
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
        capture_output=True, text=True
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])

    # Loop avatar to match audio duration
    looped = output_path.parent / "looped_avatar.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(avatar_path),
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p", str(looped)
    ], capture_output=True)

    # Clear face detection cache
    pkl_cache = Path.home() / "Easy-Wav2Lip" / "temp" / "last_detected_face.pkl"
    pkl_cache.unlink(missing_ok=True)

    # Copy our pkl if available
    if AVATAR_PKL.exists():
        import shutil
        shutil.copy2(AVATAR_PKL, pkl_cache)

    # Run Wav2Lip
    result = subprocess.run([
        str(WAV2LIP_PYTHON), str(WAV2LIP_DIR / "run.py"),
    ], capture_output=True, cwd=str(WAV2LIP_DIR),
       env={**__import__('os').environ,
            "video": str(looped),
            "audio": str(audio_path)})

    wav2lip_output = WAV2LIP_DIR / "temp" / "result.mp4"
    if wav2lip_output.exists():
        import shutil
        shutil.move(str(wav2lip_output), str(output_path))

    # Cleanup
    looped.unlink(missing_ok=True)

    return output_path.exists()


def generate_segment(script_text, tmpdir, name):
    """Generate a lip-synced avatar segment from script text."""
    print(f"  Generating {name}...")

    audio_path = tmpdir / f"{name}.wav"
    video_path = tmpdir / f"{name}_raw.mp4"
    normalized_path = tmpdir / f"{name}.mp4"

    # TTS
    print(f"    TTS...")
    if not generate_tts(script_text, audio_path):
        print(f"    ERROR: TTS failed for {name}")
        return None

    # Use generate_avatar_video.py for proper chunked Wav2Lip
    output_tmp = tmpdir / f"{name}_gen.mp4"
    cmd = [
        sys.executable, str(PROJECT_ROOT / "tools" / "generate_avatar_video.py"),
        script_text,
        "--avatar", "dmpgh-3",
        "--quality", "Fast",
        "--format", "landscape",
        "--output", str(output_tmp),
    ]
    print(f"    Lip sync...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))

    if output_tmp.exists():
        normalize_clip(output_tmp, normalized_path)
        return normalized_path
    else:
        print(f"    ERROR: Lip sync failed for {name}")
        print(f"    stderr: {result.stderr[-500:] if result.stderr else 'none'}")
        return None


def format_date(date_str):
    """Format date string for speech: '2026-04-01' -> 'April 1st, 2026'"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day = dt.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return dt.strftime(f"%B {day}{suffix}, %Y")


def assemble(episode_num=None, date_str=None, story_files=None,
             opening_file=None, closing_file=None, opening_script=None,
             closing_script=None):
    """Assemble a complete episode."""

    find_bumpers()

    # Load episode metadata if available
    ep_dir = None
    episode_data = None
    if episode_num:
        ep_dir = SHOW_DIR / f"ep{episode_num}"
        json_path = ep_dir / "episode.json"
        if json_path.exists():
            episode_data = json.loads(json_path.read_text())
            if not date_str:
                date_str = episode_data.get("date", datetime.now().strftime("%Y-%m-%d"))

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    formatted_date = format_date(date_str)
    print(f"\n=== Assembling Episode {episode_num or '?'} — {formatted_date} ===\n")

    # Load scripts if available
    if episode_data and not opening_script:
        opening_script_file = episode_data.get("scripts", {}).get("opening")
        if opening_script_file and Path(opening_script_file).exists():
            opening_script = Path(opening_script_file).read_text().strip()

    if episode_data and not closing_script:
        closing_script_file = episode_data.get("scripts", {}).get("closing")
        if closing_script_file and Path(closing_script_file).exists():
            closing_script = Path(closing_script_file).read_text().strip()

    # Find story files from episode dir if not provided
    if not story_files and ep_dir:
        story_files = sorted(ep_dir.glob("story*.mp4"))
        if not story_files:
            # Check downloads or other locations
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        segments = []

        # 1. Intro bumper
        if INTRO_BUMPER:
            print("Adding intro bumper...")
            bumper_norm = tmpdir / "0-intro-bumper.mp4"
            normalize_clip(INTRO_BUMPER, bumper_norm)
            segments.append(bumper_norm)

        # 2. Opening (generate or use provided)
        if opening_file:
            print(f"Using provided opening: {opening_file}")
            opening_norm = tmpdir / "1-opening.mp4"
            normalize_clip(Path(opening_file), opening_norm)
            segments.append(opening_norm)
        elif opening_script:
            seg = generate_segment(opening_script, tmpdir, "1-opening")
            if seg:
                segments.append(seg)

        # 3. Stories
        if story_files:
            for i, story in enumerate(story_files):
                print(f"Normalizing story {i+1}: {Path(story).name}")
                story_norm = tmpdir / f"{i+2}-story{i+1}.mp4"
                normalize_clip(Path(story), story_norm)
                segments.append(story_norm)

        # 4. Closing (generate or use provided)
        if closing_file:
            print(f"Using provided closing: {closing_file}")
            closing_norm = tmpdir / f"{len(segments)}-closing.mp4"
            normalize_clip(Path(closing_file), closing_norm)
            segments.append(closing_norm)
        elif closing_script:
            seg = generate_segment(closing_script, tmpdir, f"{len(segments)}-closing")
            if seg:
                segments.append(seg)

        # 5. Credits bumper
        if CREDITS_BUMPER:
            print("Adding credits bumper...")
            credits_norm = tmpdir / f"{len(segments)}-credits.mp4"
            normalize_clip(CREDITS_BUMPER, credits_norm)
            segments.append(credits_norm)

        if not segments:
            print("ERROR: No segments to assemble!")
            return

        # Apply crossfades between main content segments
        # Bumpers get clean cuts, content segments get crossfades
        # Structure: [bumper] [opening] [story1] [story2] [story3] [closing] [credits]
        # Crossfade between: opening↔story1, story1↔story2, story2↔story3, story3↔closing
        print(f"\nApplying crossfades between content segments...")

        # Separate bumpers from content
        content_start = 1 if INTRO_BUMPER else 0
        content_end = len(segments) - (1 if CREDITS_BUMPER else 0)
        content_segments = segments[content_start:content_end]

        final_segments = []

        # Intro bumper (clean cut)
        if INTRO_BUMPER and content_start > 0:
            final_segments.append(segments[0])

        # Crossfade the content segments together
        if len(content_segments) > 1:
            crossfaded = tmpdir / "content_crossfaded.mp4"
            print(f"  Crossfading {len(content_segments)} content segments ({CROSSFADE_DURATION}s dissolve)...")
            if crossfade_concat(content_segments, crossfaded):
                final_segments.append(crossfaded)
            else:
                print("  WARNING: Crossfade failed, falling back to clean cuts")
                final_segments.extend(content_segments)
        else:
            final_segments.extend(content_segments)

        # Credits bumper (clean cut)
        if CREDITS_BUMPER and content_end < len(segments):
            final_segments.append(segments[-1])

        # Final concat (clean cuts between bumpers and content)
        print(f"\nFinal stitch ({len(final_segments)} pieces)...")
        concat_list = tmpdir / "concat.txt"
        with open(concat_list, "w") as f:
            for seg in final_segments:
                f.write(f"file '{seg}'\n")

        # Output paths
        output_name = f"AI-Views-and-News-EP{episode_num or 'X'}.mp4"
        website_dir = WEBSITE_DIR / f"ep{episode_num}" if episode_num else None
        show_output = ep_dir / output_name if ep_dir else PROJECT_ROOT / ".tmp" / output_name

        # Primary output
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy", str(show_output)
        ], capture_output=True)

        if show_output.exists():
            # Get duration
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(show_output)],
                capture_output=True, text=True
            )
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            mins = int(duration // 60)
            secs = int(duration % 60)
            size_mb = show_output.stat().st_size / 1024 / 1024

            print(f"\n{'='*60}")
            print(f"Episode assembled: {output_name}")
            print(f"Duration: {mins}:{secs:02d}")
            print(f"Size: {size_mb:.0f} MB")
            print(f"Output: {show_output}")

            # Copy to website
            if website_dir:
                website_dir.mkdir(exist_ok=True)
                import shutil
                website_output = website_dir / output_name
                shutil.copy2(show_output, website_output)
                print(f"Website: {website_output}")

            # Update episode.json
            if episode_data and ep_dir:
                episode_data["status"] = "complete"
                episode_data["final_video"] = output_name
                (ep_dir / "episode.json").write_text(json.dumps(episode_data, indent=2))
                print(f"Status: updated to 'complete'")

            print(f"{'='*60}")
        else:
            print("ERROR: Assembly failed!")


def main():
    parser = argparse.ArgumentParser(description="Assemble AI Views and News episode")
    parser.add_argument("--episode", "-e", type=int, help="Episode number (loads from show/epN/)")
    parser.add_argument("--date", "-d", help="Episode date (YYYY-MM-DD)")
    parser.add_argument("--stories", nargs="+", help="Pictory story video files in order")
    parser.add_argument("--opening", help="Pre-made opening video (skip local generation)")
    parser.add_argument("--closing", help="Pre-made closing video (skip local generation)")
    parser.add_argument("--opening-script", help="Text for opening (generates locally)")
    parser.add_argument("--closing-script", help="Text for closing (generates locally)")
    parser.add_argument("--crossfade", type=float, default=1.0, help="Crossfade duration in seconds (default 1.0, 0 to disable)")

    args = parser.parse_args()

    assemble(
        episode_num=args.episode,
        date_str=args.date,
        story_files=args.stories,
        opening_file=args.opening,
        closing_file=args.closing,
        opening_script=args.opening_script,
        closing_script=args.closing_script,
    )


if __name__ == "__main__":
    main()
