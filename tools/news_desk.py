#!/usr/bin/env python3
"""
News Desk Generator - Split-screen interview/news format video generator.

Takes a script with named role markers, avatar photos, and voice assignments.
Produces a split-screen video where only the active speaker's lips move.
Supports 2 or 3 speakers with automatic layout detection.

Script format (any role names work):
    MODERATOR (avatar: photo.jpg, voice: joe):
    Welcome to the debate.

    LEFT (avatar: guest1.jpg, voice: lessac):
    Thank you for having me.

    RIGHT (avatar: guest2.jpg, voice: amy):
    Glad to be here.

    MODERATOR:
    Let's begin.

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
SADTALKER_DIR = Path.home() / "SadTalker"
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

# Default speaker config (used when roles match these names and no config given)
DEFAULT_VOICES = {"HOST": "joe", "GUEST": "lessac", "MODERATOR": "joe", "LEFT": "lessac", "RIGHT": "amy"}
DEFAULT_AVATARS = {"HOST": "dp-avatar-tight", "GUEST": "stock-test"}


def parse_script(script_text: str) -> tuple[dict, list]:
    """
    Parse a news desk script into speaker config and dialogue lines.
    Supports any role names (HOST, GUEST, MODERATOR, LEFT, RIGHT, etc.)

    Returns:
        speakers: dict of {role: {avatar, voice}} from header declarations
        lines: list of {role, text} for each dialogue line
    """
    speakers = {}
    lines = []
    known_roles = set()

    # Pattern for speaker line with config: ROLENAME (avatar: x, voice: y):
    header_pattern = re.compile(
        r'^([A-Z][A-Z0-9_]*)\s*\(([^)]+)\)\s*:\s*$', re.IGNORECASE
    )
    # Pattern for speaker line without config: ROLENAME:
    simple_pattern = re.compile(
        r'^([A-Z][A-Z0-9_]*)\s*:\s*$', re.IGNORECASE
    )

    # First pass: discover all roles (headers define them, simple lines use them)
    for raw_line in script_text.strip().split('\n'):
        line = raw_line.strip()
        header_match = header_pattern.match(line)
        if header_match:
            known_roles.add(header_match.group(1).upper())
            continue
        simple_match = simple_pattern.match(line)
        if simple_match:
            known_roles.add(simple_match.group(1).upper())

    current_role = None
    current_text = []

    for raw_line in script_text.strip().split('\n'):
        line = raw_line.strip()

        # Check for header with config
        header_match = header_pattern.match(line)
        if header_match and header_match.group(1).upper() in known_roles:
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
        if simple_match and simple_match.group(1).upper() in known_roles:
            if current_role and current_text:
                lines.append({"role": current_role, "text": ' '.join(current_text)})
                current_text = []
            current_role = simple_match.group(1).upper()
            continue

        # Check for inline dialogue: "HOST: some text here" on one line
        inline_match = re.match(r'^([A-Z][A-Z0-9_]*)\s*:\s+(.+)$', line, re.IGNORECASE)
        if inline_match and inline_match.group(1).upper() in known_roles:
            if current_role and current_text:
                lines.append({"role": current_role, "text": ' '.join(current_text)})
                current_text = []
            current_role = inline_match.group(1).upper()
            current_text = [inline_match.group(2).strip()]
            continue

        # Content line
        if line and current_role:
            current_text.append(line)

    # Save last block
    if current_role and current_text:
        lines.append({"role": current_role, "text": ' '.join(current_text)})

    # Fill in defaults for any role that appeared in lines but wasn't in a header
    for line in lines:
        role = line["role"]
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
            "-vf", "scale=960:1080:force_original_aspect_ratio=increase,crop=960:1080",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
            "-an", str(output)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(avatar_path),
            "-t", str(duration),
            "-vf", "scale=960:1080:force_original_aspect_ratio=increase,crop=960:1080",
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
        "--out_height", "360",
        "--quality", quality,
        "--wav2lip_batch_size", "64",
    ]

    result = subprocess.run(cmd, cwd=str(WAV2LIP_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Wav2Lip failed: {result.stderr}")
        raise RuntimeError(f"Wav2Lip failed (exit {result.returncode})")

    return output


def run_sadtalker(avatar_image: Path, audio: Path, output: Path):
    """Run SadTalker on a still image + audio to produce video with head movement."""
    sadtalker_python = SADTALKER_DIR / ".venv" / "bin" / "python"
    result_dir = output.parent / "sadtalker_out"
    result_dir.mkdir(exist_ok=True)

    cmd = [
        str(sadtalker_python), str(SADTALKER_DIR / "inference.py"),
        "--driven_audio", str(audio.resolve()),
        "--source_image", str(avatar_image.resolve()),
        "--result_dir", str(result_dir),
        "--still",
        "--preprocess", "crop",
    ]

    result = subprocess.run(cmd, cwd=str(SADTALKER_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"SadTalker failed: {result.stderr}")
        raise RuntimeError(f"SadTalker failed (exit {result.returncode})")

    # SadTalker outputs to a dated subfolder — find the newest mp4
    import glob
    results = sorted(glob.glob(str(result_dir / "**/*.mp4"), recursive=True), key=lambda x: Path(x).stat().st_mtime)
    if not results:
        raise RuntimeError("SadTalker produced no output video")

    generated = Path(results[-1])
    shutil.copy2(str(generated), str(output))
    return output


def generate_news_desk(script_path: Path, quality: str = "Fast", output_path: Path = None, engine: str = "wav2lip"):
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
            if engine == "sadtalker":
                run_sadtalker(speakers[role]["avatar_path"], audio_files[i], synced_vid)
            else:
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

        # Step 3: Build per-line composited segments (audio+video married per line)
        # This prevents sync drift by never separating audio from video
        asm_start = time.time()

        role_order = list(speakers.keys())
        num_panels = len(role_order)

        # Layout: 2 speakers = equal halves, 3 speakers = large center + smaller sides
        if num_panels == 3:
            center_w = 860   # Host gets biggest panel
            side_w = 530     # Guests get equal sides (530+860+530 = 1920)
            panel_widths = [side_w, center_w, side_w]
            # Reorder: put HOST in center
            host_role = role_order[0]  # First declared role is host
            guest_roles = role_order[1:]
            role_order = [guest_roles[0], host_role, guest_roles[1]] if len(guest_roles) >= 2 else role_order
            panel_h = 810  # Leave room for lower third banner area
        else:
            panel_w = 1920 // num_panels
            panel_widths = [panel_w] * num_panels
            panel_h = 1080

        def find_lower_third(avatar_name):
            """Find lower third overlay by trying each part of the avatar name."""
            parts = avatar_name.lower().replace('_', '-').split('-')
            # Try full name first
            full = PROJECT_ROOT / "overlays" / f"lower_third_{avatar_name.lower().replace('_', '-')}.png"
            if full.exists():
                return full
            for part in parts:
                path = PROJECT_ROOT / "overlays" / f"lower_third_{part}.png"
                if path.exists():
                    return path
            return PROJECT_ROOT / "overlays" / f"lower_third_{parts[0]}.png"

        def smart_scale_filter(target_w, target_h):
            """Scale to fill panel: landscape sources get center-cropped to portrait first."""
            target_ratio = target_w / target_h
            return (
                f"if(gt(iw/ih\\,{target_ratio:.2f})\\,"
                # Landscape source: crop to target aspect ratio centered, then scale
                f"crop=ih*{target_ratio:.2f}:ih:(iw-ih*{target_ratio:.2f})/2:0\\,"
                # Portrait source: just use as-is
                f"),"
                # This doesn't work in a single expression, so use the simpler approach:
            )

        def get_scale_vf(src_path, target_w, target_h):
            """Scale to fill panel completely and center-crop to exact size."""
            return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"

        # Pre-generate one static frame per speaker (freeze frame, no loop seam)
        static_frames = {}
        for idx, role in enumerate(role_order):
            pw = panel_widths[idx] if num_panels == 3 else panel_widths[0]
            frame_path = tmpdir / f"static_frame_{role}.png"
            vf = get_scale_vf(speakers[role]["avatar_path"], pw, panel_h)
            subprocess.run([
                "ffmpeg", "-y", "-i", str(speakers[role]["avatar_path"]),
                "-vf", vf,
                "-frames:v", "1", str(frame_path)
            ], capture_output=True, check=True)
            static_frames[role] = frame_path

        desk_segments = []  # Complete desk+audio segments per line

        for i, line in enumerate(lines):
            dur = durations[i]
            active_role = line["role"]

            # Build panel video for each speaker
            panel_videos = {}
            for idx, role in enumerate(role_order):
                pw = panel_widths[idx] if num_panels == 3 else panel_widths[0]
                if role == active_role:
                    clip = [c for c in synced_clips[role] if c["line_idx"] == i][0]
                    panel_vid = tmpdir / f"panel_{i}_{role}.mp4"
                    vf = get_scale_vf(clip["synced"], pw, panel_h)
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(clip["synced"]),
                        "-t", str(dur),
                        "-vf", vf,
                        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", str(panel_vid)
                    ], capture_output=True, check=True)
                    panel_videos[role] = panel_vid
                else:
                    # Use freeze frame (no loop seam = no avatar pop-in)
                    panel_vid = tmpdir / f"panel_{i}_{role}.mp4"
                    subprocess.run([
                        "ffmpeg", "-y", "-loop", "1",
                        "-i", str(static_frames[role]),
                        "-t", str(dur),
                        "-vf", f"scale={pw}:{panel_h}:force_original_aspect_ratio=increase,crop={pw}:{panel_h}",
                        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", str(panel_vid)
                    ], capture_output=True, check=True)
                    panel_videos[role] = panel_vid

            # Composite panels side by side with audio for this line
            panel_inputs = []
            hstack_filter = ""
            for idx, role in enumerate(role_order):
                panel_inputs.extend(["-i", str(panel_videos[role])])
                hstack_filter += f"[{idx}:v]copy[p{idx}];"

            stack_labels = "".join(f"[p{idx}]" for idx in range(num_panels))

            overlay_inputs = []

            if num_panels == 3:
                # 3-panel broadcast layout: panels on dark blue background with borders
                # Stack panels manually with padding for white borders
                border = 2
                bg_color = "0x0a1a4a"  # dark blue studio background

                # Build composite: dark background, panels flush together with thin dividers
                hstack_filter = ""
                for idx in range(num_panels):
                    hstack_filter += f"[{idx}:v]copy[p{idx}];"

                # Create background
                hstack_filter += f"color=c={bg_color}:s=1920x1080:d={dur}[bg];"

                # Place panels flush on background with thin white divider lines
                x_offset = 0
                current = "bg"
                for idx in range(num_panels):
                    pw = panel_widths[idx]
                    next_label = f"placed{idx}"
                    hstack_filter += f"[{current}][p{idx}]overlay={x_offset}:0[{next_label}];"
                    current = next_label
                    # Draw thin white divider after each panel (except last)
                    if idx < num_panels - 1:
                        div_label = f"div{idx}"
                        hstack_filter += f"[{current}]drawbox=x={x_offset + pw}:y=0:w={border}:h={panel_h}:color=white:t=fill[{div_label}];"
                        current = div_label
                    x_offset += pw

                # Add chyron name labels under each panel
                x_offset = 0
                for idx, role in enumerate(role_order):
                    pw = panel_widths[idx]
                    name = speakers[role].get("avatar", role).replace("-", " ").title()
                    name = name.replace("'", "\u2019").replace(":", "\\:")
                    chyron_x = x_offset + pw // 2
                    chyron_y = panel_h + 20  # below panels
                    next_label = f"chyron{idx}"
                    hstack_filter += (
                        f"[{current}]drawtext=text='{name}':"
                        f"fontsize=28:fontcolor=white:font=Helvetica Neue Bold:"
                        f"x={chyron_x}-(text_w/2):y={chyron_y}:"
                        f"borderw=2:bordercolor=black[{next_label}];"
                    )
                    current = next_label
                    x_offset += pw

                # Add lower third banner bar (red topic bar + white headline)
                banner_y = 980
                # Write text to files to avoid ffmpeg quoting issues
                topic_file = tmpdir / f"topic_{i}.txt"
                topic_file.write_text("KNOCKOFF NEWS")
                headline = line['text'][:80]
                headline_file = tmpdir / f"headline_{i}.txt"
                headline_file.write_text(headline)
                hstack_filter += (
                    f"[{current}]drawbox=x=0:y={banner_y}:w=1920:h=40:color=0xcc0000:t=fill[bar1];"
                    f"[bar1]drawtext=textfile={topic_file}:"
                    f"fontsize=22:fontcolor=white:font=Helvetica Neue Bold:"
                    f"x=20:y={banner_y}+10:"
                    f"borderw=1:bordercolor=0x990000[bar2];"
                    f"[bar2]drawbox=x=0:y={banner_y+40}:w=1920:h=50:color=white:t=fill[bar3];"
                    f"[bar3]drawtext=textfile={headline_file}:"
                    f"fontsize=30:fontcolor=0x111111:font=Helvetica Neue Bold:"
                    f"x=20:y={banner_y+48}[vid]"
                )

            elif num_panels == 2:
                # 2-panel: overlay on background, overlap 4px to hide seam
                pw = panel_widths[0]
                hstack_filter += f"color=c=white:s=1920x1080:d={dur}[bg2];"
                hstack_filter += f"[bg2][p0]overlay=0:0[tmp2];"
                hstack_filter += f"[tmp2][p1]overlay={pw - 10}:0[desk];"

                # Add lower thirds on first line only
                lower_thirds = [find_lower_third(speakers[role]['avatar']) for role in role_order]
                all_lts_exist = all(lt.exists() for lt in lower_thirds)

                overlay_inputs = []
                if all_lts_exist and i == 0:
                    for lt in lower_thirds:
                        overlay_inputs.extend(["-i", str(lt)])

                    pw = panel_widths[0]
                    lt_w = min(350, pw - 20)
                    current_label = "desk"
                    for j, role in enumerate(role_order):
                        lt_idx = num_panels + 1 + j  # after audio
                        lt_label = f"lt_{j}"
                        x_pos = (j * pw) + 20
                        y_pos = panel_h - 60
                        is_last = (j == num_panels - 1)
                        next_label = "vid" if is_last else f"tmp{j}"
                        hstack_filter += (
                            f"[{lt_idx}]scale={lt_w}:40[{lt_label}];"
                            f"[{current_label}][{lt_label}]overlay={x_pos}:{y_pos}[{next_label}]"
                        )
                        if not is_last:
                            hstack_filter += ";"
                        current_label = next_label
                else:
                    hstack_filter += "[desk]copy[vid]"

            desk_seg = tmpdir / f"desk_{i}.mp4"
            cmd = [
                "ffmpeg", "-y",
            ] + panel_inputs + [
                "-i", str(audio_files[i]),
            ] + overlay_inputs + [
                "-filter_complex", hstack_filter,
                "-map", "[vid]", "-map", f"{num_panels}:a",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                "-t", str(dur),
                "-shortest",
                str(desk_seg)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            desk_segments.append(desk_seg)

        # Concatenate all desk segments
        concat_list = tmpdir / "desk_concat.txt"
        with open(concat_list, "w") as f:
            for seg in desk_segments:
                f.write(f"file '{seg}'\n")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_path = OUTPUT_DIR / f"newsdesk_{timestamp}.mp4"

        desk_video = tmpdir / "desk.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(desk_video)
        ], capture_output=True, check=True)

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
                    "-c:a", "aac", "-ar", "44100", "-ac", "2",
                    str(intro_ready)
                ], capture_output=True, check=True)
                parts.append(intro_ready)

            # Scale desk to 1080p to match intro/outro
            desk_1080 = tmpdir / "desk_1080.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(desk_video),
                "-vf", "scale=1920:1080",
                "-c:v", "libx264", "-preset", "fast", "-r", "30",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(desk_1080)
            ], capture_output=True, check=True)
            parts.append(desk_1080)

            # Add bumper video if it exists (plays before disclaimer)
            bumper_path = PROJECT_ROOT / "overlays" / "dmpgh_bumper.mp4"
            if bumper_path.exists():
                print("Adding bumper video...")
                bumper_ready = tmpdir / "bumper_ready.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(bumper_path),
                    "-vf", "scale=1920:1080",
                    "-c:v", "libx264",  "-preset", "fast", "-r", "30",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2",
                    str(bumper_ready)
                ], capture_output=True, check=True)
                parts.append(bumper_ready)

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
    print(f"{'SadTalker' if engine == 'sadtalker' else 'Wav2Lip'}:       {w2l_time:.1f}s")
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
Script format (any role names, 2 or 3 speakers):
  MODERATOR (avatar: photo.jpg, voice: joe):
  Welcome to the debate.

  LEFT (avatar: guest1.jpg, voice: lessac):
  Thank you.

  RIGHT (avatar: guest2.jpg, voice: amy):
  Glad to be here.

Examples:
  %(prog)s --script interview.md
  %(prog)s --script debate.md --quality Improved
  %(prog)s --script interview.md -o output/my_interview.mp4
"""
    )
    parser.add_argument("--script", "-s", type=Path, required=True, help="Path to script file")
    parser.add_argument("--quality", "-q", choices=["Fast", "Improved", "Enhanced"], default="Fast")
    parser.add_argument("--engine", "-e", choices=["wav2lip", "sadtalker"], default="wav2lip", help="Lip sync engine")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output video path")

    args = parser.parse_args()

    if not args.script.exists():
        parser.error(f"Script not found: {args.script}")

    result = generate_news_desk(args.script, args.quality, args.output, args.engine)
    subprocess.run(["open", str(result)])


if __name__ == "__main__":
    main()
