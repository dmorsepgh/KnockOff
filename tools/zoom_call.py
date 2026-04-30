#!/usr/bin/env python3
"""
Zoom Call Generator - Simulated Zoom-style grid video with multiple speakers.

Creates a 2x3 or 2x2 grid layout where only the active speaker's lips move.
Includes Zoom-style UI elements (name labels, grid borders).

Script format (same as news_desk.py):
    COOPER (avatar: anderson-cooper, voice: lessac):
    Good evening everyone.

    HANNITY (avatar: sean-hannity, voice: joe):
    Thank you Anderson.

Usage:
    python tools/zoom_call.py --script scripts/zoom_iran.md
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
OUTPUT_DIR = PROJECT_ROOT / "output" / "keepers"
OVERLAY_DIR = PROJECT_ROOT / "overlays"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"zoom_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Preview resolution (landscape 16:9)
GRID_W = 1280
GRID_H = 720


def parse_script(script_text: str) -> tuple:
    """Parse script into speakers dict and dialogue lines (same format as news_desk)."""
    speakers = {}
    lines = []
    known_roles = set()

    header_pattern = re.compile(r'^([A-Z][A-Z0-9_]*)\s*\(([^)]+)\)\s*:\s*$', re.IGNORECASE)
    simple_pattern = re.compile(r'^([A-Z][A-Z0-9_]*)\s*:\s*$', re.IGNORECASE)

    for raw_line in script_text.strip().split('\n'):
        line = raw_line.strip()
        m = header_pattern.match(line)
        if m:
            known_roles.add(m.group(1).upper())
            continue
        m = simple_pattern.match(line)
        if m:
            known_roles.add(m.group(1).upper())

    current_role = None
    current_text = []

    for raw_line in script_text.strip().split('\n'):
        line = raw_line.strip()
        if not line:
            if current_role and current_text:
                lines.append({"role": current_role, "text": " ".join(current_text)})
                current_text = []
            continue

        header_match = header_pattern.match(line)
        if header_match:
            if current_role and current_text:
                lines.append({"role": current_role, "text": " ".join(current_text)})
                current_text = []
            role = header_match.group(1).upper()
            config_str = header_match.group(2)
            config = {}
            for part in config_str.split(','):
                key, val = part.strip().split(':')
                config[key.strip().lower()] = val.strip()
            speakers[role] = {
                "avatar": config.get("avatar", role.lower()),
                "voice": config.get("voice", "joe"),
            }
            current_role = role
            continue

        simple_match = simple_pattern.match(line)
        if simple_match:
            candidate = simple_match.group(1).upper()
            if candidate in known_roles:
                if current_role and current_text:
                    lines.append({"role": current_role, "text": " ".join(current_text)})
                    current_text = []
                current_role = candidate
                continue

        if current_role:
            current_text.append(line)

    if current_role and current_text:
        lines.append({"role": current_role, "text": " ".join(current_text)})

    return speakers, lines


def resolve_avatar(name: str) -> Path:
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


def clear_wav2lip_cache():
    cache = WAV2LIP_DIR / "last_detected_face.pkl"
    if cache.exists():
        cache.unlink()


def run_lipsync(avatar_video: Path, audio: Path, output: Path):
    wav2lip_python = WAV2LIP_DIR / ".venv" / "bin" / "python3"
    # Determine cell height for out_height
    cmd = [
        str(wav2lip_python), str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", "checkpoints/Wav2Lip.pth",
        "--face", str(avatar_video.resolve()),
        "--audio", str(audio.resolve()),
        "--outfile", str(output.resolve()),
        "--out_height", "360",
        "--quality", "Fast",
        "--wav2lip_batch_size", "64",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WAV2LIP_DIR))
    return result.returncode == 0


def make_cell_video(avatar_path: Path, duration: float, output: Path, cell_w: int, cell_h: int):
    """Create a video sized for one grid cell from an image."""
    is_image = avatar_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']
    if is_image:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(avatar_path),
            "-t", str(duration),
            "-vf", f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
            "-an", str(output)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(avatar_path),
            "-t", str(duration),
            "-vf", f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-an", str(output)
        ]
    subprocess.run(cmd, capture_output=True, check=True)


def generate_zoom_call(script_path: Path, output_path: Path = None):
    """Generate a Zoom-style grid video from a script."""
    script_text = script_path.read_text()
    speakers, lines = parse_script(script_text)

    logger.info(f"Speakers: {list(speakers.keys())}")
    logger.info(f"Lines: {len(lines)}")

    num_speakers = len(speakers)
    if num_speakers <= 4:
        cols, rows = 2, 2
    elif num_speakers <= 6:
        cols, rows = 3, 2
    elif num_speakers <= 9:
        cols, rows = 3, 3
    else:
        cols, rows = 4, 3

    cell_w = GRID_W // cols
    cell_h = GRID_H // rows
    border = 2  # Dark border between cells

    logger.info(f"Grid: {cols}x{rows} ({cell_w}x{cell_h} per cell)")

    # Resolve avatars
    for role in speakers:
        avatar_path = resolve_avatar(speakers[role]["avatar"])
        if not avatar_path.exists():
            logger.error(f"Avatar not found: {speakers[role]['avatar']}")
            return None
        speakers[role]["avatar_path"] = avatar_path

    role_order = list(speakers.keys())

    with tempfile.TemporaryDirectory(prefix="zoom_call_") as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Generate all TTS audio
        logger.info("Step 1: Generating TTS audio...")
        tts_start = time.time()
        audio_files = []
        durations = []
        for i, line in enumerate(lines):
            audio_path = tmpdir / f"line_{i}.wav"
            voice = speakers[line["role"]]["voice"]
            generate_audio(line["text"], audio_path, voice=voice)
            dur = get_audio_duration(audio_path)
            audio_files.append(audio_path)
            durations.append(dur)
        logger.info(f"TTS done: {time.time() - tts_start:.1f}s, {len(audio_files)} clips")

        # Step 2: Lip sync each speaker's lines
        logger.info("Step 2: Lip syncing...")
        w2l_start = time.time()
        synced_clips = {role: [] for role in speakers}

        for i, line in enumerate(lines):
            role = line["role"]
            dur = durations[i]
            logger.info(f"  Line {i+1}/{len(lines)}: {role} ({dur:.1f}s)")

            # Create cell-sized avatar video
            avatar_vid = tmpdir / f"cell_{i}.mp4"
            make_cell_video(speakers[role]["avatar_path"], dur, avatar_vid, cell_w, cell_h)

            # Lip sync
            clear_wav2lip_cache()
            synced_raw = tmpdir / f"synced_raw_{i}.mp4"
            success = run_lipsync(avatar_vid, audio_files[i], synced_raw)
            if not success:
                logger.warning(f"  Wav2Lip failed for line {i}, using static")
                synced_raw = avatar_vid

            # Force exact duration to prevent drift over many segments
            synced_vid = tmpdir / f"synced_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(synced_raw),
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-r", "30", "-an", str(synced_vid)
            ], capture_output=True, check=True)

            synced_clips[role].append({
                "duration": dur,
                "synced": synced_vid,
                "line_idx": i
            })

        logger.info(f"Lip sync done: {time.time() - w2l_start:.1f}s")

        # Step 3: Build grid per dialogue line (audio+video married per segment)
        # This prevents sync drift by never separating audio from video
        logger.info("Step 3: Building per-line grid segments...")
        asm_start = time.time()

        # Pre-generate one static cell per speaker (reused across lines)
        static_cells = {}
        for role in speakers:
            static_path = tmpdir / f"static_cell_{role}.mp4"
            is_image = speakers[role]["avatar_path"].suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']
            if is_image:
                cmd = [
                    "ffmpeg", "-y", "-loop", "1",
                    "-i", str(speakers[role]["avatar_path"]),
                    "-t", "1",  # 1 second, will be looped as needed
                    "-vf", f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-r", "30", "-an", str(static_path)
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-stream_loop", "-1",
                    "-i", str(speakers[role]["avatar_path"]),
                    "-t", "1",
                    "-vf", f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-r", "30", "-an", str(static_path)
                ]
            subprocess.run(cmd, capture_output=True, check=True)
            static_cells[role] = static_path

        grid_segments = []  # Complete grid+audio segments per line

        for i, line in enumerate(lines):
            dur = durations[i]
            active_role = line["role"]
            logger.info(f"  Grid segment {i+1}/{len(lines)}: {active_role} ({dur:.1f}s)")

            # Build cell video for each speaker in this line
            cell_videos = {}
            for role in role_order:
                if role == active_role:
                    # Use lip-synced clip
                    clip = [c for c in synced_clips[role] if c["line_idx"] == i][0]
                    cell_vid = tmpdir / f"cell_grid_{i}_{role}.mp4"
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(clip["synced"]),
                        "-t", str(dur),
                        "-vf", f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2",
                        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", str(cell_vid)
                    ], capture_output=True, check=True)
                    cell_videos[role] = cell_vid
                else:
                    # Loop static cell to match duration
                    cell_vid = tmpdir / f"cell_grid_{i}_{role}.mp4"
                    subprocess.run([
                        "ffmpeg", "-y", "-stream_loop", "-1",
                        "-i", str(static_cells[role]),
                        "-t", str(dur),
                        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", str(cell_vid)
                    ], capture_output=True, check=True)
                    cell_videos[role] = cell_vid

            # Composite grid for this line using hstack+vstack
            row1_inputs = []
            row1_filter = ""
            for j in range(cols):
                if j < len(role_order):
                    role = role_order[j]
                    row1_inputs.extend(["-i", str(cell_videos[role])])
                    row1_filter += f"[{j}:v]copy[r1_{j}];"
                idx = j
            row1_labels = "".join(f"[r1_{j}]" for j in range(cols))
            row1_filter += f"{row1_labels}hstack=inputs={cols}[row1];"

            row2_inputs = []
            row2_filter = ""
            for j in range(cols):
                speaker_idx = cols + j
                input_idx = cols + j
                if speaker_idx < len(role_order):
                    role = role_order[speaker_idx]
                    row2_inputs.extend(["-i", str(cell_videos[role])])
                    row2_filter += f"[{input_idx}:v]copy[r2_{j}];"
                else:
                    # Empty black cell
                    row2_inputs.extend(["-i", str(static_cells[role_order[0]])])  # placeholder
                    row2_filter += f"color=c=0x1a1a1a:s={cell_w}x{cell_h}:d={dur}:r=30[r2_{j}];"
            row2_labels = "".join(f"[r2_{j}]" for j in range(cols))
            row2_filter += f"{row2_labels}hstack=inputs={cols}[row2];"

            grid_filter = row1_filter + row2_filter + "[row1][row2]vstack=inputs=2[vid]"

            grid_seg = tmpdir / f"grid_{i}.mp4"
            cmd = [
                "ffmpeg", "-y",
            ] + row1_inputs + row2_inputs + [
                "-i", str(audio_files[i]),
                "-filter_complex", grid_filter,
                "-map", "[vid]",
                "-map", f"{cols * rows}:a" if (cols * rows) == len(role_order) else f"{len(role_order)}:a",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                "-t", str(dur),
                "-shortest",
                str(grid_seg)
            ]
            # Audio input index = number of video inputs
            num_vid_inputs = len(row1_inputs + row2_inputs) // 2
            cmd[cmd.index("-map") + 3] = f"{num_vid_inputs}:a"

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Grid segment {i} failed: {result.stderr[-500:]}")
                continue

            grid_segments.append(grid_seg)

        logger.info(f"Grid assembly: {time.time() - asm_start:.1f}s")

        # Step 4: Concatenate all grid segments
        logger.info("Step 4: Concatenating grid segments...")

        concat_list = tmpdir / "grid_concat.txt"
        with open(concat_list, "w") as f:
            for seg in grid_segments:
                f.write(f"file '{seg}'\n")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_path = OUTPUT_DIR / f"zoom_{timestamp}.mp4"

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(output_path)
        ], capture_output=True, check=True)

        total_dur = get_audio_duration(output_path)
        logger.info(f"=== COMPLETE: {output_path} ({total_dur:.1f}s) ===")

        # Now overlay Zoom-style name labels using Pillow
        logger.info("Adding Zoom-style name labels...")
        add_zoom_labels(output_path, role_order, speakers, cols, rows, cell_w, cell_h, tmpdir)

        return output_path


def add_zoom_labels(video_path: Path, role_order: list, speakers: dict, cols: int, rows: int, cell_w: int, cell_h: int, tmpdir: Path):
    """Overlay Zoom-style name labels on the grid video using Pillow + ffmpeg."""
    from PIL import Image, ImageDraw, ImageFont

    # Create transparent overlay with all name labels
    overlay = Image.new("RGBA", (GRID_W, GRID_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()

    for idx, role in enumerate(role_order):
        col = idx % cols
        row = idx // cols
        x = col * cell_w + 8
        y = (row + 1) * cell_h - 28

        name = role.title()
        # Draw semi-transparent background
        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        draw.rectangle([x - 4, y - 2, x + tw + 8, y + 20], fill=(0, 0, 0, 160))
        draw.text((x, y), name, fill=(255, 255, 255, 255), font=font)

    overlay_path = tmpdir / "zoom_labels.png"
    overlay.save(str(overlay_path))

    # Overlay on video
    labeled = video_path.parent / f"{video_path.stem}_labeled{video_path.suffix}"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(overlay_path),
        "-filter_complex", "[0:v][1:v]overlay=0:0[vid]",
        "-map", "[vid]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "copy",
        str(labeled)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        shutil.move(str(labeled), str(video_path))
        logger.info("Name labels added.")
    else:
        logger.warning(f"Label overlay failed: {result.stderr[-200:]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Zoom-style grid video")
    parser.add_argument("--script", required=True, help="Script file path")
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    start = time.time()
    result = generate_zoom_call(Path(args.script), Path(args.output) if args.output else None)
    elapsed = time.time() - start
    if result:
        print(f"\nZoom call video: {result}")
        print(f"Total time: {elapsed/60:.1f} minutes")
