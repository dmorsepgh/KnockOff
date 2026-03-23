#!/usr/bin/env python3
"""
News Desk Generator - Split-screen interview/news format video generator.

Takes a script with HOST/GUEST markers, avatar photos, and voice assignments.
Produces a split-screen video where only the active speaker's lips move.

Script format:
    HOST (avatar: photo.jpg, voice: joe):
    Welcome back everyone.

    GUEST (avatar: guest.jpg, voice: lessac):
    Thanks for having me.

    HOST:
    So what do you think?

    GUEST:
    I think it's great.

Usage:
    python tools/news_desk.py --script interview.md
    python tools/news_desk.py --script interview.md --quality Improved
"""

import argparse
import re
import subprocess
import shutil
import sys
import tempfile
import time
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tts import generate_audio

PROJECT_ROOT = Path(__file__).parent.parent
AVATAR_DIR = PROJECT_ROOT / "avatars"
WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "avatar" / "output"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"newsdesk_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default speaker config
DEFAULT_VOICES = {"HOST": "joe", "GUEST": "lessac"}
DEFAULT_AVATARS = {"HOST": "dp-avatar-tight", "GUEST": "stock-test"}


def parse_script(script_text: str) -> tuple[dict, list]:
    """
    Parse a news desk script into speaker config and dialogue lines.

    Returns:
        speakers: dict of {role: {avatar, voice}} from header declarations
        lines: list of {role, text} for each dialogue line
    """
    speakers = {}
    lines = []

    # Pattern for speaker line with config: HOST (avatar: x, voice: y):
    header_pattern = re.compile(
        r'^(HOST|GUEST)\s*\(([^)]+)\)\s*:\s*$', re.IGNORECASE
    )
    # Pattern for speaker line without config: HOST:
    simple_pattern = re.compile(
        r'^(HOST|GUEST)\s*:\s*$', re.IGNORECASE
    )

    current_role = None
    current_text = []

    for raw_line in script_text.strip().split('\n'):
        line = raw_line.strip()

        # Check for header with config
        header_match = header_pattern.match(line)
        if header_match:
            # Save previous block
            if current_role and current_text:
                lines.append({"role": current_role, "text": ' '.join(current_text)})
                current_text = []

            role = header_match.group(1).upper()
            config_str = header_match.group(2)

            # Parse config: avatar: x, voice: y
            config = {}
            for part in config_str.split(','):
                key, _, val = part.strip().partition(':')
                config[key.strip().lower()] = val.strip()

            speakers[role] = {
                "avatar": config.get("avatar", DEFAULT_AVATARS.get(role, "")),
                "voice": config.get("voice", DEFAULT_VOICES.get(role, "joe")),
            }
            current_role = role
            continue

        # Check for simple speaker line
        simple_match = simple_pattern.match(line)
        if simple_match:
            if current_role and current_text:
                lines.append({"role": current_role, "text": ' '.join(current_text)})
                current_text = []
            current_role = simple_match.group(1).upper()
            continue

        # Content line
        if line and current_role:
            current_text.append(line)

    # Save last block
    if current_role and current_text:
        lines.append({"role": current_role, "text": ' '.join(current_text)})

    # Fill in defaults for any speaker without config
    for role in ["HOST", "GUEST"]:
        if role not in speakers:
            speakers[role] = {
                "avatar": DEFAULT_AVATARS.get(role, ""),
                "voice": DEFAULT_VOICES.get(role, "joe"),
            }

    return speakers, lines


def resolve_avatar(name: str) -> Path:
    """Find avatar file by name."""
    # Direct path
    path = Path(name)
    if path.exists():
        return path

    # Check avatars dir with various extensions
    for ext in ['.mp4', '.jpg', '.jpeg', '.png', '.webp', '']:
        candidate = AVATAR_DIR / f"{name}{ext}"
        if candidate.exists():
            return candidate

    return AVATAR_DIR / name


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def make_avatar_video(avatar_path: Path, duration: float, output: Path):
    """Create a video from an image or loop a video to duration."""
    is_image = avatar_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']

    if is_image:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(avatar_path),
            "-t", str(duration),
            "-vf", "scale=960:1080:force_original_aspect_ratio=decrease,pad=960:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
            "-an", str(output)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(avatar_path),
            "-t", str(duration),
            "-vf", "scale=960:1080:force_original_aspect_ratio=decrease,pad=960:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-an", str(output)
        ]

    subprocess.run(cmd, capture_output=True, check=True)


def run_lipsync(avatar_video: Path, audio: Path, output: Path, quality: str = "Fast"):
    """Run Wav2Lip on a single clip."""
    # Clear stale cache
    cache = WAV2LIP_DIR / "last_detected_face.pkl"
    if cache.exists():
        cache.unlink()

    wav2lip_python = WAV2LIP_DIR / ".venv" / "bin" / "python3"
    cmd = [
        str(wav2lip_python), str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", f"checkpoints/Wav2Lip.pth",
        "--face", str(avatar_video.resolve()),
        "--audio", str(audio.resolve()),
        "--outfile", str(output.resolve()),
        "--out_height", "720",
        "--quality", quality,
        "--wav2lip_batch_size", "64",
    ]

    result = subprocess.run(cmd, cwd=str(WAV2LIP_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Wav2Lip failed: {result.stderr}")
        raise RuntimeError(f"Wav2Lip failed (exit {result.returncode})")

    return output


def generate_news_desk(script_path: Path, quality: str = "Fast", output_path: Path = None):
    """Generate a full news desk video from a script file."""
    total_start = time.time()

    script_text = script_path.read_text()
    speakers, lines = parse_script(script_text)

    logger.info(f"Parsed {len(lines)} dialogue lines")
    for role, config in speakers.items():
        logger.info(f"  {role}: avatar={config['avatar']}, voice={config['voice']}")

    # Resolve avatars
    for role in speakers:
        avatar_path = resolve_avatar(speakers[role]["avatar"])
        if not avatar_path.exists():
            print(f"ERROR: Avatar not found for {role}: {speakers[role]['avatar']}")
            sys.exit(1)
        speakers[role]["avatar_path"] = avatar_path
        logger.info(f"  {role} avatar: {avatar_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Generate TTS for each line
        tts_start = time.time()
        audio_files = []
        durations = []

        for i, line in enumerate(lines):
            audio_file = tmpdir / f"line_{i}.wav"
            voice = speakers[line["role"]]["voice"]
            logger.info(f"TTS line {i}: [{line['role']}] {line['text'][:50]}...")
            generate_audio(line["text"], audio_file, voice)
            dur = get_audio_duration(audio_file)
            audio_files.append(audio_file)
            durations.append(dur)
            print(f"  Line {i+1} [{line['role']}]: {dur:.1f}s")

        tts_time = time.time() - tts_start
        total_duration = sum(durations)
        logger.info(f"TTS complete: {tts_time:.1f}s for {total_duration:.1f}s of audio")

        # Step 2: Generate lip-synced clips for each line
        w2l_start = time.time()
        synced_clips = {}  # {role: [(start_time, duration, synced_path), ...]}
        for role in speakers:
            synced_clips[role] = []

        cumulative_time = 0.0
        for i, line in enumerate(lines):
            role = line["role"]
            dur = durations[i]

            print(f"\nLip-syncing line {i+1}/{len(lines)} [{role}] ({dur:.1f}s)...")

            # Create avatar video for this line's duration
            avatar_vid = tmpdir / f"avatar_{role}_{i}.mp4"
            make_avatar_video(speakers[role]["avatar_path"], dur, avatar_vid)

            # Lip sync
            synced_vid = tmpdir / f"synced_{role}_{i}.mp4"
            run_lipsync(avatar_vid, audio_files[i], synced_vid, quality)

            synced_clips[role].append({
                "start": cumulative_time,
                "duration": dur,
                "synced": synced_vid,
                "line_idx": i
            })

            cumulative_time += dur

        w2l_time = time.time() - w2l_start
        logger.info(f"Wav2Lip complete: {w2l_time:.1f}s")

        # Step 3: Build full timeline for each speaker
        # Each speaker needs: synced video when talking, static when not
        asm_start = time.time()

        role_timelines = {}
        for role in speakers:
            segments = []
            current_pos = 0.0

            for i, line in enumerate(lines):
                dur = durations[i]

                if line["role"] == role:
                    # This speaker is talking — use synced clip
                    clip = [c for c in synced_clips[role] if c["line_idx"] == i][0]

                    # Get synced video resolution for matching static segments
                    synced_res = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v",
                         "-show_entries", "stream=width,height",
                         "-of", "csv=p=0", str(clip["synced"])],
                        capture_output=True, text=True
                    ).stdout.strip()
                    w, h = synced_res.split(',')

                    segments.append({"type": "synced", "path": clip["synced"], "duration": dur, "w": int(w), "h": int(h)})
                else:
                    # Other speaker is talking — show static
                    static = tmpdir / f"static_{role}_{i}.mp4"

                    # Match resolution of synced clips for this role
                    if synced_clips[role]:
                        ref = synced_clips[role][0]["synced"]
                        ref_res = subprocess.run(
                            ["ffprobe", "-v", "error", "-select_streams", "v",
                             "-show_entries", "stream=width,height",
                             "-of", "csv=p=0", str(ref)],
                            capture_output=True, text=True
                        ).stdout.strip()
                        sw, sh = ref_res.split(',')
                    else:
                        sw, sh = "640", "720"

                    make_static_cmd = [
                        "ffmpeg", "-y", "-stream_loop", "-1",
                        "-i", str(speakers[role]["avatar_path"]),
                        "-t", str(dur),
                        "-vf", f"scale={sw}:{sh}:force_original_aspect_ratio=decrease,pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2",
                        "-c:v", "libx264", "-preset", "fast",
                        "-pix_fmt", "yuv420p", "-r", "30", "-an", str(static)
                    ]
                    # For images, add -loop 1
                    if speakers[role]["avatar_path"].suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                        make_static_cmd.insert(3, "1")
                        make_static_cmd.insert(3, "-loop")
                        # Remove -stream_loop -1
                        make_static_cmd = [x for x in make_static_cmd if x not in ["-stream_loop", "-1"]]

                    subprocess.run(make_static_cmd, capture_output=True, check=True)
                    segments.append({"type": "static", "path": static, "duration": dur, "w": int(sw), "h": int(sh)})

                current_pos += dur

            role_timelines[role] = segments

        # Concatenate each role's timeline
        role_videos = {}
        for role, segments in role_timelines.items():
            concat_list = tmpdir / f"concat_{role}.txt"
            with open(concat_list, "w") as f:
                for seg in segments:
                    f.write(f"file '{seg['path']}'\n")

            role_video = tmpdir / f"full_{role}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "fast", "-an",
                str(role_video)
            ], capture_output=True, check=True)
            role_videos[role] = role_video

        # Build full audio track (all lines concatenated)
        audio_concat = tmpdir / "audio_concat.txt"
        with open(audio_concat, "w") as f:
            for af in audio_files:
                f.write(f"file '{af}'\n")

        full_audio = tmpdir / "full_audio.wav"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(audio_concat),
            "-c:a", "pcm_s16le", str(full_audio)
        ], capture_output=True, check=True)

        # Composite side by side at 1080p
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_path = OUTPUT_DIR / f"newsdesk_{timestamp}.mp4"

        host_video = role_videos.get("HOST")
        guest_video = role_videos.get("GUEST")

        # Build filter with lower thirds overlay
        def find_lower_third(avatar_name):
            """Find lower third overlay by trying each part of the avatar name."""
            parts = avatar_name.lower().replace('_', '-').split('-')
            for part in parts:
                path = PROJECT_ROOT / "overlays" / f"lower_third_{part}.png"
                if path.exists():
                    return path
            return PROJECT_ROOT / "overlays" / f"lower_third_{parts[0]}.png"

        host_lower = find_lower_third(speakers['HOST']['avatar'])
        guest_lower = find_lower_third(speakers['GUEST']['avatar'])

        filter_parts = "[0:v]scale=960:540[left];[1:v]scale=960:540[right];[left][right]hstack=inputs=2[desk]"

        overlay_inputs = []
        input_idx = 3  # 0=host, 1=guest, 2=audio

        if host_lower.exists() and guest_lower.exists():
            overlay_inputs = ["-i", str(host_lower), "-i", str(guest_lower)]
            filter_parts += (
                f";[{input_idx}]scale=350:40[lt_h];"
                f"[{input_idx+1}]scale=350:40[lt_g];"
                f"[desk][lt_h]overlay=20:480:enable='between(t,0,5)'[tmp];"
                f"[tmp][lt_g]overlay=990:480:enable='between(t,0,5)'[vid]"
            )
        else:
            filter_parts += ";[desk]copy[vid]"

        desk_video = tmpdir / "desk.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(host_video),
            "-i", str(guest_video),
            "-i", str(full_audio),
        ] + overlay_inputs + [
            "-filter_complex", filter_parts,
            "-map", "[vid]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
            "-shortest",
            str(desk_video)
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # Add intro and outro if they exist
        intro_path = PROJECT_ROOT / "overlays" / "intro_card.mp4"
        outro_path = PROJECT_ROOT / "overlays" / "outro_card.mp4"

        if intro_path.exists() or outro_path.exists():
            print("Adding broadcast package (intro/outro)...")
            parts = []

            if intro_path.exists():
                intro_ready = tmpdir / "intro_ready.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(intro_path),
                    "-c:v", "libx264", "-preset", "fast", "-r", "30",
                    "-c:a", "aac", "-ar", "44100",
                    str(intro_ready)
                ], capture_output=True, check=True)
                parts.append(intro_ready)

            # Scale desk to 1080p to match intro/outro
            desk_1080 = tmpdir / "desk_1080.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(desk_video),
                "-vf", "scale=1920:1080",
                "-c:v", "libx264", "-preset", "fast", "-r", "30",
                "-c:a", "aac", "-ar", "44100",
                str(desk_1080)
            ], capture_output=True, check=True)
            parts.append(desk_1080)

            if outro_path.exists():
                # Add silent audio to outro
                outro_ready = tmpdir / "outro_ready.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(outro_path),
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", "scale=1920:1080",
                    "-c:v", "libx264", "-preset", "fast", "-r", "30",
                    "-c:a", "aac", "-shortest",
                    str(outro_ready)
                ], capture_output=True, check=True)
                parts.append(outro_ready)

            # Concat all parts
            concat_file = tmpdir / "broadcast_concat.txt"
            with open(concat_file, "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")

            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy",
                str(output_path)
            ], capture_output=True, check=True)
        else:
            shutil.copy2(str(desk_video), str(output_path))

        asm_time = time.time() - asm_start

    total_time = time.time() - total_start

    # Print metrics
    print(f"\n{'='*50}")
    print(f"KNOCKOFF NEWS BROADCAST COMPLETE")
    print(f"{'='*50}")
    print(f"Output:        {output_path}")
    print(f"Duration:      {total_duration:.1f}s of content")
    print(f"{'='*50}")
    print(f"TTS:           {tts_time:.1f}s")
    print(f"Wav2Lip:       {w2l_time:.1f}s")
    print(f"Assembly:      {asm_time:.1f}s")
    print(f"TOTAL:         {total_time:.1f}s")
    print(f"Ratio:         {total_time:.0f}s to produce {total_duration:.1f}s ({total_duration/total_time:.1f}x)")
    print(f"{'='*50}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate split-screen news desk videos from scripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Script format:
  HOST (avatar: photo.jpg, voice: joe):
  Welcome back everyone.

  GUEST (avatar: guest.jpg, voice: lessac):
  Thanks for having me.

  HOST:
  So what do you think?

Examples:
  %(prog)s --script interview.md
  %(prog)s --script interview.md --quality Improved
  %(prog)s --script interview.md -o output/my_interview.mp4
"""
    )
    parser.add_argument("--script", "-s", type=Path, required=True, help="Path to script file")
    parser.add_argument("--quality", "-q", choices=["Fast", "Improved", "Enhanced"], default="Fast")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output video path")

    args = parser.parse_args()

    if not args.script.exists():
        parser.error(f"Script not found: {args.script}")

    result = generate_news_desk(args.script, args.quality, args.output)
    subprocess.run(["open", str(result)])


if __name__ == "__main__":
    main()
