#!/usr/bin/env python3
"""
Avatar Video Generator - HeyGen-style video generation using local AI models.

Features:
- Avatar library: Store avatars in avatars/ folder, reference by name
- Voice selection: Multiple Piper TTS voices (male/female)
- B-roll support: Use [B-ROLL: filename.mp4] markers in scripts

Pipeline:
1. Parse script for B-roll markers
2. Text -> Piper TTS -> Audio (.wav)
3. Audio + Avatar Video -> Wav2Lip -> Lip-synced video
4. Stitch segments with B-roll -> Final video

Usage:
    # Simple (no B-roll)
    python tools/generate_avatar_video.py "Your text" --avatar myavatar

    # With B-roll script
    python tools/generate_avatar_video.py --script explainer.md --avatar host --voice joe

    # List available resources
    python tools/generate_avatar_video.py --list-avatars
    python tools/generate_avatar_video.py --list-voices
"""

import argparse
import os
import subprocess
import sys
import tempfile
import shutil
import time
from pathlib import Path

# Import script parser
sys.path.insert(0, str(Path(__file__).parent))
from parse_script import parse_script, get_full_speech_text, has_visual_markers, Segment, MusicTrack

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
VOICE_DIR = PROJECT_ROOT / "models" / "piper"
AVATAR_LIB_DIR = PROJECT_ROOT / "avatars"
BROLL_DIR = PROJECT_ROOT / "broll"
OVERLAY_DIR = PROJECT_ROOT / "overlays"
MUSIC_DIR = PROJECT_ROOT / "music"
WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "avatar" / "output"
SEGMENTS_DIR = PROJECT_ROOT / ".tmp" / "avatar" / "segments"

# Default voice
DEFAULT_VOICE = "lessac"

# Video format presets (width, height)
VIDEO_FORMATS = {
    "portrait": (1080, 1920),   # 9:16 vertical (TikTok, Reels, Shorts)
    "landscape": (1920, 1080),  # 16:9 horizontal (YouTube, standard)
    "square": (1080, 1080),     # 1:1 (Instagram feed)
}
DEFAULT_FORMAT = "portrait"


def get_voice_path(voice_name: str) -> tuple[Path, Path]:
    """Get model and config paths for a voice."""
    model = VOICE_DIR / f"en_US-{voice_name}-medium.onnx"
    config = VOICE_DIR / f"en_US-{voice_name}-medium.onnx.json"
    return model, config


def list_avatars():
    """List available avatars in the library."""
    AVATAR_LIB_DIR.mkdir(parents=True, exist_ok=True)
    avatars = list(AVATAR_LIB_DIR.glob("*.mp4"))
    if not avatars:
        print(f"No avatars found in {AVATAR_LIB_DIR}")
        print("Add .mp4 files to use them by name.")
        return
    print("Available avatars:")
    for a in sorted(avatars):
        print(f"  {a.stem}")


def list_voices():
    """List available Piper voices."""
    voices = list(VOICE_DIR.glob("en_US-*-medium.onnx"))
    if not voices:
        print(f"No voices found in {VOICE_DIR}")
        return
    print("Available voices:")
    for v in sorted(voices):
        # Extract voice name from en_US-{name}-medium.onnx
        name = v.stem.replace("en_US-", "").replace("-medium", "")
        print(f"  {name}")


def resolve_avatar(avatar_arg: Path) -> Path:
    """Resolve avatar path - check library first, then full path."""
    # If it's already a full path that exists, use it
    if avatar_arg.exists():
        return avatar_arg

    # Check if it's just a name (no extension)
    if not avatar_arg.suffix:
        lib_path = AVATAR_LIB_DIR / f"{avatar_arg.name}.mp4"
        if lib_path.exists():
            return lib_path

    # Check library with extension
    lib_path = AVATAR_LIB_DIR / avatar_arg.name
    if lib_path.exists():
        return lib_path

    # Not found
    return avatar_arg


def resolve_broll(broll_path: str) -> Path:
    """Resolve B-roll path - check broll/ folder first."""
    path = Path(broll_path)

    # Absolute path
    if path.is_absolute() and path.exists():
        return path

    # Check broll/ folder
    broll_file = BROLL_DIR / broll_path
    if broll_file.exists():
        return broll_file

    return path


def resolve_overlay(overlay_path: str) -> Path:
    """Resolve overlay path - check overlays/ folder first."""
    path = Path(overlay_path)

    # Absolute path
    if path.is_absolute() and path.exists():
        return path

    # Check overlays/ folder
    overlay_file = OVERLAY_DIR / overlay_path
    if overlay_file.exists():
        return overlay_file

    # Also check broll folder (overlays can be videos too)
    broll_file = BROLL_DIR / overlay_path
    if broll_file.exists():
        return broll_file

    return path


def resolve_music(music_path: str) -> Path:
    """Resolve music path - check music/ folder first."""
    path = Path(music_path)

    # Absolute path
    if path.is_absolute() and path.exists():
        return path

    # Check music/ folder
    music_file = MUSIC_DIR / music_path
    if music_file.exists():
        return music_file

    return path


def check_dependencies(voice: str = DEFAULT_VOICE):
    """Verify all required components are available."""
    errors = []

    # Check voice model
    model, config = get_voice_path(voice)
    if not model.exists():
        errors.append(f"Voice model not found: {model}")
        errors.append(f"  Available voices: {', '.join(v.stem.split('-')[1] for v in VOICE_DIR.glob('en_US-*-medium.onnx'))}")

    # Check Wav2Lip
    wav2lip_model = WAV2LIP_DIR / "checkpoints" / "Wav2Lip.pth"
    if not wav2lip_model.exists():
        errors.append(f"Wav2Lip model not found: {wav2lip_model}")

    # Check piper via python module
    try:
        subprocess.run([sys.executable, "-m", "piper", "--help"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        errors.append("Piper TTS not installed. Install with: pip install piper-tts")

    # Check ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        errors.append("ffmpeg not installed")

    if errors:
        print("Missing dependencies:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


def text_to_speech(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Convert text to speech using Piper TTS."""
    print(f"Generating speech with voice '{voice}'...")

    model, config = get_voice_path(voice)

    cmd = [
        sys.executable, "-m", "piper",
        "--model", str(model),
        "--config", str(config),
        "-f", str(output_path)
    ]

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate(input=text.encode())

    if process.returncode != 0:
        print(f"Piper TTS failed: {stderr.decode()}")
        sys.exit(1)

    return output_path


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def get_video_duration(video_path: Path) -> float:
    """Get duration of video file in seconds."""
    return get_audio_duration(video_path)  # Same ffprobe command works


def loop_video_to_duration(video_path: Path, duration: float, output_path: Path) -> Path:
    """Loop video to match audio duration."""
    print(f"Looping video to {duration:.1f}s...")

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(video_path),
        "-t", str(duration + 0.5),
        "-c:v", "libx264",
        "-preset", "fast",
        "-an",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Video loop failed: {result.stderr.decode()}")
        sys.exit(1)

    return output_path


MAX_WAV2LIP_CHUNK = 20.0  # Max seconds per Wav2Lip chunk (CPU memory limit)


def run_wav2lip_chunked(video_path: Path, audio_path: Path, output_path: Path, quality: str = "Improved") -> Path:
    """Run Wav2Lip with chunking for long videos."""
    duration = get_audio_duration(audio_path)

    if duration <= MAX_WAV2LIP_CHUNK:
        # Short enough to process in one go
        return run_wav2lip(video_path, audio_path, output_path, quality)

    print(f"Video is {duration:.1f}s, processing in {MAX_WAV2LIP_CHUNK}s chunks...")

    with tempfile.TemporaryDirectory() as chunk_dir:
        chunk_dir = Path(chunk_dir)
        chunk_outputs = []
        num_chunks = int(duration / MAX_WAV2LIP_CHUNK) + 1

        for i in range(num_chunks):
            start = i * MAX_WAV2LIP_CHUNK
            chunk_duration = min(MAX_WAV2LIP_CHUNK, duration - start)
            if chunk_duration < 0.5:
                break

            print(f"\n  Chunk {i+1}/{num_chunks}: {start:.1f}s - {start + chunk_duration:.1f}s")

            # Extract video chunk
            video_chunk = chunk_dir / f"video_chunk_{i}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-ss", str(start),
                "-t", str(chunk_duration),
                "-c:v", "libx264", "-preset", "fast",
                "-an",
                str(video_chunk)
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            # Extract audio chunk
            audio_chunk = chunk_dir / f"audio_chunk_{i}.wav"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", str(start),
                "-t", str(chunk_duration),
                "-c:a", "pcm_s16le",
                str(audio_chunk)
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            # Clear ALL files in Wav2Lip temp directory before each chunk
            # This prevents state issues from previous runs
            wav2lip_temp = WAV2LIP_DIR / "temp"
            if wav2lip_temp.exists():
                for old_file in wav2lip_temp.iterdir():
                    if old_file.is_file():
                        old_file.unlink()

            # Also clean any old synced files in chunk directory (Wav2Lip may output here)
            for old_file in chunk_dir.glob("*_synced*.mp4"):
                if old_file.name != f"synced_chunk_{i}.mp4":
                    old_file.unlink()

            # Small delay between chunks to let system settle
            if i > 0:
                time.sleep(1)

            # Process chunk with Wav2Lip (disable tracking reuse for chunks)
            synced_chunk = chunk_dir / f"synced_chunk_{i}.mp4"
            run_wav2lip(video_chunk, audio_chunk, synced_chunk, quality, use_tracking=False)

            if synced_chunk.exists():
                chunk_outputs.append(synced_chunk)
            else:
                print(f"  WARNING: Chunk {i+1} failed, skipping")

        # Concatenate all chunks
        if chunk_outputs:
            print(f"\n  Concatenating {len(chunk_outputs)} chunks...")
            concatenate_videos(chunk_outputs, output_path)
        else:
            print("ERROR: No chunks were processed successfully")
            sys.exit(1)

    return output_path


def run_wav2lip(video_path: Path, audio_path: Path, output_path: Path, quality: str = "Improved", use_tracking: bool = True) -> Path:
    """Run Wav2Lip to sync lips to audio (single chunk)."""
    print(f"Running Wav2Lip ({quality} quality)...")

    config_path = WAV2LIP_DIR / "config.ini"
    tracking_str = "True" if use_tracking else "False"
    config_content = f"""[OPTIONS]
video_file = {video_path}
vocal_file = {audio_path}
quality = {quality}
output_height = full resolution
wav2lip_version = Wav2Lip
use_previous_tracking_data = {tracking_str}
nosmooth = True
preview_window = False

[PADDING]
u = 0
d = 10
l = 0
r = 0

[MASK]
size = 2.5
feathering = 2
mouth_tracking = False
debug_mask = False

[OTHER]
batch_process = False
output_suffix = _synced
include_settings_in_suffix = False
preview_settings = False
frame_to_preview = 100
"""
    config_path.write_text(config_content)

    cmd = [
        sys.executable,
        str(WAV2LIP_DIR / "run.py"),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(WAV2LIP_DIR)

    result = subprocess.run(
        cmd,
        cwd=str(WAV2LIP_DIR),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Wav2Lip failed:")
        print(result.stderr)
        print(result.stdout)
        sys.exit(1)

    # Debug: list what files exist in video directory
    print(f"  Files in {video_path.parent}:")
    for f in video_path.parent.glob("*.mp4"):
        print(f"    {f.name}")

    # Find output file - Easy-Wav2Lip outputs to temp/result.mp4
    # or to {video_stem}_{audio_stem}_synced.mp4 in video directory
    wav2lip_result = WAV2LIP_DIR / "temp" / "result.mp4"
    expected_output = video_path.parent / f"{video_path.stem}_synced.mp4"
    # Wav2Lip may also combine video+audio stems
    audio_stem = audio_path.stem if audio_path else ""
    combined_output = video_path.parent / f"{video_path.stem}_{audio_stem}_synced.mp4"

    if wav2lip_result.exists():
        print(f"  Found at: {wav2lip_result}")
        shutil.move(str(wav2lip_result), str(output_path))
    elif combined_output.exists():
        print(f"  Found at: {combined_output}")
        shutil.move(str(combined_output), str(output_path))
    elif expected_output.exists():
        print(f"  Found at: {expected_output}")
        shutil.move(str(expected_output), str(output_path))
    else:
        # Fallback search - only use files matching current video stem
        for f in video_path.parent.glob(f"{video_path.stem}*_synced*.mp4"):
            print(f"  Found: {f}")
            shutil.move(str(f), str(output_path))
            break
        else:
            for f in WAV2LIP_DIR.glob("*_synced*.mp4"):
                print(f"  Found: {f}")
                shutil.move(str(f), str(output_path))
                break
            else:
                print(f"  No output found!")

    return output_path


def trim_video(video_path: Path, duration: float, output_path: Path) -> Path:
    """Trim video to specified duration (no audio)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-an",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Video trim failed: {result.stderr.decode()}")
        sys.exit(1)
    return output_path


def concatenate_videos(video_paths: list[Path], output_path: Path) -> Path:
    """Concatenate multiple videos using ffmpeg concat demuxer."""
    print(f"Concatenating {len(video_paths)} video segments...")

    # Create concat manifest
    manifest = output_path.parent / "concat.txt"
    with open(manifest, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(manifest),
        "-c:v", "libx264",
        "-preset", "fast",
        "-an",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Video concatenation failed: {result.stderr.decode()}")
        sys.exit(1)

    manifest.unlink()
    return output_path


def merge_audio_video(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Merge audio track with video."""
    print("Merging audio with video...")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Audio merge failed: {result.stderr.decode()}")
        sys.exit(1)

    return output_path


def overlay_on_video(
    overlay_file: Path,
    output_path: Path,
    duration: float,
    video_format: str = DEFAULT_FORMAT
) -> Path:
    """
    Create full-screen overlay video (no avatar visible).

    Voice continues over the overlay. Avatar cuts away completely.
    Works with both images (png/jpg) and videos (mp4).
    """
    print(f"Creating full-screen overlay...")

    width, height = VIDEO_FORMATS.get(video_format, VIDEO_FORMATS[DEFAULT_FORMAT])
    is_image = overlay_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']

    if is_image:
        # For images, scale to fit frame and loop for duration
        filter_str = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(overlay_file),
            "-vf", filter_str,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path)
        ]
    else:
        # For videos, scale to fit and trim to duration
        filter_str = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(overlay_file),
            "-vf", filter_str,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-an",
            str(output_path)
        ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Overlay failed: {result.stderr.decode()}")
        sys.exit(1)

    return output_path


def add_text_overlay(
    video_path: Path,
    main_text: str,
    subtext: str,
    output_path: Path
) -> Path:
    """
    Add CTA text overlay centered on video.

    Main text is large and bold, subtext is smaller below.
    """
    print(f"Adding CTA text overlay: {main_text}")

    # Escape special characters for ffmpeg drawtext
    main_text = main_text.replace("'", "'\\''").replace(":", "\\:")
    subtext = subtext.replace("'", "'\\''").replace(":", "\\:") if subtext else ""

    # Build filter - main text centered, subtext below
    if subtext:
        filter_str = (
            f"drawtext=text='{main_text}':"
            f"fontsize=72:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-40:"
            f"borderw=3:bordercolor=black,"
            f"drawtext=text='{subtext}':"
            f"fontsize=36:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h/2)+40:"
            f"borderw=2:bordercolor=black"
        )
    else:
        filter_str = (
            f"drawtext=text='{main_text}':"
            f"fontsize=72:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"borderw=3:bordercolor=black"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-an",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Text overlay failed: {result.stderr.decode()}")
        sys.exit(1)

    return output_path


def mix_background_music(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    music_volume: str = "-12dB"
) -> Path:
    """
    Mix background music with video's audio track.

    Music is looped to match video duration and mixed at specified volume.
    """
    print(f"Mixing background music at {music_volume}...")

    video_duration = get_video_duration(video_path)

    # Mix audio: video audio + music (looped and volume adjusted)
    filter_complex = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{video_duration},"
        f"volume={music_volume}[music];"
        f"[0:a][music]amix=inputs=2:duration=first[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Music mix failed: {result.stderr.decode()}")
        sys.exit(1)

    return output_path


def format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(
    speech_segments: list,
    segment_durations: list,
    output_path: Path,
    words_per_caption: int = 8
) -> Path:
    """
    Generate SRT subtitle file from speech segments.

    Splits each segment into smaller caption chunks for readability.
    """
    print("Generating captions...")

    srt_lines = []
    caption_num = 1
    current_time = 0.0

    for seg_text, seg_duration in zip(speech_segments, segment_durations):
        # Split text into words
        words = seg_text.split()
        if not words:
            current_time += seg_duration
            continue

        # Calculate time per word
        time_per_word = seg_duration / len(words)

        # Group words into caption chunks
        for i in range(0, len(words), words_per_caption):
            chunk_words = words[i:i + words_per_caption]
            chunk_text = " ".join(chunk_words)

            # Calculate timing for this chunk
            start_time = current_time + (i * time_per_word)
            end_time = start_time + (len(chunk_words) * time_per_word)

            # Add SRT entry
            srt_lines.append(str(caption_num))
            srt_lines.append(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}")
            srt_lines.append(chunk_text)
            srt_lines.append("")

            caption_num += 1

        current_time += seg_duration

    # Write SRT file
    output_path.write_text("\n".join(srt_lines))
    print(f"  Generated {caption_num - 1} captions: {output_path}")

    return output_path


def burn_captions(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    font_size: int = 18,
    margin_bottom: int = 60
) -> Path:
    """
    Burn SRT captions into video using ffmpeg.

    Captions appear at bottom of frame with black outline for readability.
    """
    print("Burning captions into video...")

    # Escape path for ffmpeg subtitles filter (requires special escaping)
    srt_escaped = str(srt_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    # Subtitles filter with styling
    filter_str = (
        f"subtitles='{srt_escaped}':"
        f"force_style='FontSize={font_size},"
        f"PrimaryColour=&HFFFFFF,"
        f"OutlineColour=&H000000,"
        f"Outline=2,"
        f"MarginV={margin_bottom},"
        f"Alignment=2'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "copy",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Caption burn failed: {result.stderr.decode()}")
        # Try alternative method with drawtext
        print("Trying alternative caption method...")
        return burn_captions_drawtext(video_path, srt_path, output_path, font_size, margin_bottom)

    return output_path


def burn_captions_drawtext(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    font_size: int = 18,
    margin_bottom: int = 60
) -> Path:
    """
    Alternative caption burning using ASS subtitles format.
    """
    # Convert SRT to ASS for better ffmpeg compatibility
    ass_path = srt_path.with_suffix('.ass')

    cmd = [
        "ffmpeg", "-y",
        "-i", str(srt_path),
        str(ass_path)
    ]
    subprocess.run(cmd, capture_output=True)

    if ass_path.exists():
        ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filter_str = f"ass='{ass_escaped}'"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "copy",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            return output_path

    # If all else fails, just copy the video
    print("Warning: Could not burn captions, copying video as-is")
    shutil.copy2(str(video_path), str(output_path))
    return output_path


def generate_simple_video(
    text: str,
    avatar_video: Path,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    quality: str = "Improved",
    captions: bool = False,
    video_format: str = DEFAULT_FORMAT
) -> Path:
    """Generate a simple lip-synced video (no B-roll)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Text to Speech
        audio_path = tmpdir / "speech.wav"
        text_to_speech(text, audio_path, voice)

        duration = get_audio_duration(audio_path)
        print(f"Audio duration: {duration:.1f}s")

        # Loop video
        looped_video = tmpdir / "looped.mp4"
        loop_video_to_duration(avatar_video, duration, looped_video)

        # Wav2Lip (use chunked version for long videos)
        synced_video = tmpdir / "synced.mp4"
        run_wav2lip_chunked(looped_video, audio_path, synced_video, quality)

        # Merge audio with synced video
        video_with_audio = tmpdir / "with_audio.mp4"
        merge_audio_video(synced_video, audio_path, video_with_audio)

        # Add captions if enabled
        if captions:
            srt_path = tmpdir / "captions.srt"
            generate_srt([text], [duration], srt_path)

            captioned_video = tmpdir / "captioned.mp4"
            burn_captions(video_with_audio, srt_path, captioned_video)
            shutil.copy2(str(captioned_video), str(output_path))
        else:
            shutil.copy2(str(video_with_audio), str(output_path))

    print(f"\nVideo generated: {output_path}")
    return output_path


def generate_broll_video(
    script_text: str,
    avatar_video: Path,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    quality: str = "Improved",
    captions: bool = False,
    video_format: str = DEFAULT_FORMAT
) -> Path:
    """
    Generate a video with B-roll, overlays, and CTAs from a script with markers.

    New architecture:
    1. Generate full continuous TTS audio
    2. Generate full lip-synced avatar video
    3. Calculate timestamps for each segment
    4. Apply visual effects (broll/overlay/cta) at timestamps via post-processing
    5. Add background music
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse script
    segments, music_track = parse_script(script_text)
    print(f"Parsed {len(segments)} segments")
    if music_track:
        print(f"Background music: {music_track.filename} at {music_track.volume}")

    # Check for visual markers
    has_visuals = any(s.type in ("broll", "overlay", "cta") for s in segments)
    if not has_visuals:
        # No visual markers, use simple pipeline
        full_text = get_full_speech_text(segments)
        result = generate_simple_video(full_text, avatar_video, output_path, voice, quality, captions, video_format)
        # Add music if specified
        if music_track:
            music_path = resolve_music(music_track.filename)
            if music_path.exists():
                with_music = output_path.parent / f"{output_path.stem}_music{output_path.suffix}"
                mix_background_music(result, music_path, with_music, music_track.volume)
                shutil.move(str(with_music), str(output_path))
        return output_path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Generate full audio track (continuous narration from all speech)
        full_text = get_full_speech_text(segments)
        full_audio = tmpdir / "full_audio.wav"
        text_to_speech(full_text, full_audio, voice)
        total_duration = get_audio_duration(full_audio)
        print(f"Total audio duration: {total_duration:.1f}s")

        # Step 2: Generate full lip-synced avatar video
        print("\nGenerating full lip-synced avatar...")
        looped_avatar = tmpdir / "looped_avatar.mp4"
        loop_video_to_duration(avatar_video, total_duration, looped_avatar)

        if not looped_avatar.exists():
            print(f"ERROR: Looped avatar not created at {looped_avatar}")
            sys.exit(1)
        print(f"Looped avatar created: {looped_avatar} ({looped_avatar.stat().st_size} bytes)")

        full_synced = tmpdir / "full_synced.mp4"
        run_wav2lip_chunked(looped_avatar, full_audio, full_synced, quality)

        if not full_synced.exists():
            print(f"ERROR: Wav2Lip did not produce output at {full_synced}")
            # Check for output in expected locations
            for search_dir in [tmpdir, WAV2LIP_DIR, Path.home() / "Easy-Wav2Lip"]:
                for f in search_dir.glob("*_synced*.mp4"):
                    print(f"  Found: {f}")
            sys.exit(1)

        # Verify synced video duration
        synced_duration = get_video_duration(full_synced)
        print(f"Synced video duration: {synced_duration:.1f}s (expected {total_duration:.1f}s)")

        # Step 3: Calculate timestamps and build visual effects map
        # Visual effects (overlay/broll/cta) apply to the FOLLOWING speech segment
        speech_segments = [s for s in segments if s.type == "speech"]
        segment_durations = []

        for i, seg in enumerate(speech_segments):
            seg_audio = tmpdir / f"seg_{i}.wav"
            text_to_speech(seg.content, seg_audio, voice)
            duration = get_audio_duration(seg_audio)
            segment_durations.append(duration)
            print(f"  Speech segment {i+1}: {duration:.1f}s")

        # Build speech timeline with visual effects attached
        # Format: list of (speech_duration, effect_type, effect_content, effect_duration)
        speech_with_effects = []
        pending_effect = None

        for seg in segments:
            if seg.type == "speech":
                speech_idx = len(speech_with_effects)
                duration = segment_durations[speech_idx]

                # Check if there's a pending visual effect for this speech
                effect = pending_effect
                pending_effect = None

                speech_with_effects.append({
                    "duration": duration,
                    "effect": effect
                })
            elif seg.type in ("broll", "overlay", "cta"):
                # Store this effect to apply to the NEXT speech segment
                effect_duration = seg.duration
                if not effect_duration:
                    if seg.type == "broll":
                        broll_path = resolve_broll(seg.content)
                        effect_duration = get_video_duration(broll_path) if broll_path.exists() else 5.0
                    else:
                        effect_duration = 5.0

                pending_effect = {
                    "type": seg.type,
                    "content": seg.content,
                    "duration": effect_duration,
                    "options": getattr(seg, 'options', {})
                }

        # Step 4: Build video segments
        video_segments = []
        current_time = 0.0

        for i, item in enumerate(speech_with_effects):
            speech_duration = item["duration"]
            effect = item["effect"]

            if effect:
                effect_type = effect["type"]
                effect_duration = min(effect["duration"], speech_duration)  # Don't exceed speech
                remaining_speech = speech_duration - effect_duration

                if effect_type == "broll":
                    # B-roll replaces avatar (voice continues over b-roll)
                    broll_path = resolve_broll(effect["content"])
                    if broll_path.exists():
                        print(f"\nB-roll: {effect['content']} ({effect_duration:.1f}s) @ {current_time:.1f}s")
                        broll_out = tmpdir / f"broll_{len(video_segments)}.mp4"
                        trim_video(broll_path, effect_duration, broll_out)
                        video_segments.append(broll_out)
                    current_time += effect_duration

                    # Remaining speech after b-roll shows avatar
                    if remaining_speech > 0.5:
                        print(f"Speech continues: {remaining_speech:.1f}s @ {current_time:.1f}s")
                        seg_out = tmpdir / f"speech_{len(video_segments)}.mp4"
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", str(full_synced),
                            "-ss", str(current_time),
                            "-t", str(remaining_speech),
                            "-c:v", "libx264", "-preset", "fast", "-an",
                            str(seg_out)
                        ]
                        subprocess.run(cmd, capture_output=True, check=True)
                        video_segments.append(seg_out)
                        current_time += remaining_speech

                elif effect_type == "overlay":
                    # Overlay replaces avatar (full screen, voice continues)
                    overlay_path = resolve_overlay(effect["content"])
                    if overlay_path.exists():
                        print(f"\nOverlay: {effect['content']} ({effect_duration:.1f}s) @ {current_time:.1f}s")
                        overlay_out = tmpdir / f"overlay_{len(video_segments)}.mp4"
                        overlay_on_video(overlay_path, overlay_out, effect_duration, video_format)
                        video_segments.append(overlay_out)
                    current_time += effect_duration

                    # Remaining speech after overlay shows avatar
                    if remaining_speech > 0.5:
                        print(f"Speech continues: {remaining_speech:.1f}s @ {current_time:.1f}s")
                        seg_out = tmpdir / f"speech_{len(video_segments)}.mp4"
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", str(full_synced),
                            "-ss", str(current_time),
                            "-t", str(remaining_speech),
                            "-c:v", "libx264", "-preset", "fast", "-an",
                            str(seg_out)
                        ]
                        subprocess.run(cmd, capture_output=True, check=True)
                        video_segments.append(seg_out)
                        current_time += remaining_speech

                elif effect_type == "cta":
                    # CTA shows text overlay on avatar
                    main_text = effect["content"]
                    subtext = effect["options"].get("subtext", "")

                    # Ensure we don't exceed video duration
                    if current_time >= synced_duration:
                        print(f"\nWARNING: CTA at {current_time:.1f}s exceeds video duration {synced_duration:.1f}s, skipping")
                        current_time += effect_duration
                        continue

                    actual_duration = min(effect_duration, synced_duration - current_time)
                    print(f"\nCTA: {main_text} ({actual_duration:.1f}s) @ {current_time:.1f}s")

                    # Extract avatar portion
                    avatar_portion = tmpdir / f"avatar_cta_{len(video_segments)}.mp4"
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(full_synced),
                        "-ss", str(current_time),
                        "-t", str(actual_duration),
                        "-c:v", "libx264", "-preset", "fast", "-an",
                        str(avatar_portion)
                    ]
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode != 0 or not avatar_portion.exists() or avatar_portion.stat().st_size < 1000:
                        print(f"WARNING: CTA extraction failed at {current_time:.1f}s, skipping")
                        current_time += effect_duration
                        continue

                    # Add text overlay
                    cta_out = tmpdir / f"cta_{len(video_segments)}.mp4"
                    add_text_overlay(avatar_portion, main_text, subtext, cta_out)
                    video_segments.append(cta_out)
                    current_time += actual_duration

                    # Remaining speech after CTA shows avatar
                    remaining_speech = speech_duration - actual_duration
                    if remaining_speech > 0.5 and current_time < synced_duration:
                        print(f"Speech continues: {remaining_speech:.1f}s @ {current_time:.1f}s")
                        seg_out = tmpdir / f"speech_{len(video_segments)}.mp4"
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", str(full_synced),
                            "-ss", str(current_time),
                            "-t", str(remaining_speech),
                            "-c:v", "libx264", "-preset", "fast", "-an",
                            str(seg_out)
                        ]
                        subprocess.run(cmd, capture_output=True, check=True)
                        video_segments.append(seg_out)
                        current_time += remaining_speech
            else:
                # No effect - just show avatar talking
                print(f"\nSpeech: {speech_duration:.1f}s @ {current_time:.1f}s")
                seg_out = tmpdir / f"speech_{len(video_segments)}.mp4"
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(full_synced),
                    "-ss", str(current_time),
                    "-t", str(speech_duration),
                    "-c:v", "libx264", "-preset", "fast", "-an",
                    str(seg_out)
                ]
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode != 0:
                    print(f"FFmpeg error: {result.stderr.decode()}")
                    raise subprocess.CalledProcessError(result.returncode, cmd)
                video_segments.append(seg_out)
                current_time += speech_duration

        # Step 5: Concatenate all video segments
        print(f"\nConcatenating {len(video_segments)} segments...")
        video_only = tmpdir / "video_only.mp4"
        concatenate_videos(video_segments, video_only)

        # Step 6: Merge with full audio
        video_with_audio = tmpdir / "video_with_audio.mp4"
        merge_audio_video(video_only, full_audio, video_with_audio)

        # Step 7: Add background music if specified
        if music_track:
            music_path = resolve_music(music_track.filename)
            if music_path.exists():
                print(f"\nAdding background music: {music_track.filename}")
                video_with_music = tmpdir / "video_with_music.mp4"
                mix_background_music(video_with_audio, music_path, video_with_music, music_track.volume)
                final_video = video_with_music
            else:
                print(f"Warning: Music not found: {music_path}")
                final_video = video_with_audio
        else:
            final_video = video_with_audio

        # Step 8: Add captions if enabled
        if captions:
            print("\nAdding captions...")
            speech_texts = [s.content for s in speech_segments]
            srt_path = tmpdir / "captions.srt"
            generate_srt(speech_texts, segment_durations, srt_path)

            captioned_video = tmpdir / "captioned.mp4"
            burn_captions(final_video, srt_path, captioned_video)
            shutil.copy2(str(captioned_video), str(output_path))
        else:
            shutil.copy2(str(final_video), str(output_path))

    print(f"\nVideo with B-roll generated: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate lip-synced avatar videos from text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Hello world" --avatar host
  %(prog)s --script explainer.md --avatar host --voice joe
  %(prog)s --list-avatars
  %(prog)s --list-voices
"""
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Text to speak (or use --script for file)"
    )
    parser.add_argument(
        "--script", "-s",
        type=Path,
        help="Path to script file (supports B-roll markers)"
    )
    parser.add_argument(
        "--avatar", "-a",
        type=Path,
        help="Avatar name or path (required unless listing)"
    )
    parser.add_argument(
        "--voice", "-v",
        default=DEFAULT_VOICE,
        help=f"Voice name (default: {DEFAULT_VOICE})"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=OUTPUT_DIR / "video.mp4",
        help="Output video path"
    )
    parser.add_argument(
        "--quality", "-q",
        choices=["Fast", "Improved", "Enhanced"],
        default="Improved",
        help="Wav2Lip quality level"
    )
    parser.add_argument(
        "--list-avatars",
        action="store_true",
        help="List available avatars"
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices"
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip dependency checks"
    )
    parser.add_argument(
        "--captions", "-c",
        action="store_true",
        help="Add closed captions synced to speech"
    )
    parser.add_argument(
        "--format", "-f",
        choices=list(VIDEO_FORMATS.keys()),
        default=DEFAULT_FORMAT,
        help=f"Video format: portrait (1080x1920), landscape (1920x1080), square (1080x1080). Default: {DEFAULT_FORMAT}"
    )

    args = parser.parse_args()

    # Handle list commands
    if args.list_avatars:
        list_avatars()
        return

    if args.list_voices:
        list_voices()
        return

    # Require avatar for generation
    if not args.avatar:
        parser.error("--avatar is required for video generation")

    # Get text
    if args.script:
        text = args.script.read_text()
    elif args.text:
        text = args.text
    else:
        parser.error("Provide text as argument or use --script")

    # Resolve avatar path
    avatar_path = resolve_avatar(args.avatar)
    if not avatar_path.exists():
        parser.error(f"Avatar not found: {args.avatar}\nUse --list-avatars to see available options")

    # Check dependencies
    if not args.skip_checks:
        check_dependencies(args.voice)

    # Check for visual markers (B-roll, overlay, CTA, music)
    if has_visual_markers(text) or "[MUSIC:" in text.upper():
        generate_broll_video(
            script_text=text,
            avatar_video=avatar_path,
            output_path=args.output,
            voice=args.voice,
            quality=args.quality,
            captions=args.captions,
            video_format=args.format
        )
    else:
        generate_simple_video(
            text=text,
            avatar_video=avatar_path,
            output_path=args.output,
            voice=args.voice,
            quality=args.quality,
            captions=args.captions,
            video_format=args.format
        )


if __name__ == "__main__":
    main()
