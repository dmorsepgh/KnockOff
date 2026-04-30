#!/usr/bin/env python3.12
"""
reaction_builder.py — Build a reaction/commentary video from a source clip + script.

Takes a reaction_script.json that interleaves "clip" segments (from the source video)
with "commentary" segments (narrated by TTS with B-roll).

Usage:
  python3.12 reaction_builder.py reactions/msnbc_polymarket_20260412/reaction_script.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".keys" / ".env")
except ImportError:
    pass

import requests

sys.path.insert(0, str(Path(__file__).parent))
from fundraiser_generator import (
    fetch_broll,
    narrate_scene,
    probe_duration,
    concat_scenes,
    PEXELS_KEY,
    OPENAI_KEY,
)

PROJECT_ROOT = Path(__file__).parent
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

USER_OUT_DIR = Path.home() / "Documents" / "Reaction Videos"
USER_OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_clip(source_path: str, start: float, end: float, out_path: Path):
    """Extract a segment from the source video, scaled to 1920x1080."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", source_path,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Clip extract failed: {result.stderr[-300:]}")
        raise RuntimeError("Clip extraction failed")


def add_source_banner(clip_path: Path, out_path: Path, label: str, brand_color: str):
    """Add a small source attribution banner to a clip (e.g. 'MSNBC')."""
    safe_label = label.replace("'", "").replace(":", " -").replace('"', "")
    filter_str = (
        f"drawbox=x=0:y=0:w=1920:h=50:color=0x0a0e1a@0.75:t=fill,"
        f"drawtext=fontfile='{FONT}':text='{safe_label}':"
        f"fontcolor=0xaaaaaa:fontsize=24:x=20:y=14"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(clip_path),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Banner add failed: {result.stderr[-300:]}")
        raise RuntimeError("Banner add failed")


def assemble_commentary(broll_files, narration_wav, out_path, duration,
                        show_name="", brand_color="0x00aaff"):
    """Build a commentary scene: B-roll + narration + 'COMMENTARY' banner."""
    if not broll_files:
        filter_in = ["-f", "lavfi", "-i", f"color=c=0x0a0e1a:s=1920x1080:d={duration}:r=30"]
    else:
        filter_in = ["-stream_loop", "-1", "-i", str(broll_files[0])]

    safe_show = show_name.upper().replace("'", "").replace(":", "").replace('"', "")

    main_chain = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "fps=30,"
        "eq=saturation=0.85:contrast=1.08,"
        # Banner
        f"drawbox=x=0:y=918:w=1920:h=162:color=0x0a0e1a@0.85:t=fill,"
        f"drawbox=x=0:y=918:w=1920:h=4:color={brand_color}@1.0:t=fill,"
        # Show name
        f"drawtext=fontfile='{FONT_BOLD}':text='{safe_show}':"
        f"fontcolor=white:fontsize=44:x=40:y=935,"
        # Commentary label
        f"drawtext=fontfile='{FONT}':text='COMMENTARY':"
        f"fontcolor={brand_color}:fontsize=28:x=40:y=995"
    )

    inputs = list(filter_in)
    inputs.extend(["-i", str(narration_wav)])

    filter_complex = f"[0:v]{main_chain}[vout]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "1:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Commentary scene failed: {result.stderr[-500:]}")
        raise RuntimeError("Commentary assembly failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="Path to reaction_script.json")
    ap.add_argument("--voice", default="onyx")
    ap.add_argument("--music", default="")
    ap.add_argument("--reuse", action="store_true", help="Reuse existing narration/broll")
    args = ap.parse_args()

    import fundraiser_generator
    fundraiser_generator.OPENAI_VOICE = args.voice

    script_path = Path(args.script)
    script = json.loads(script_path.read_text())
    job_dir = script_path.parent

    source_clip = script["source_clip"]
    show_name = script.get("show_name", "Commentary")
    brand_color = script.get("brand_color", "0x00aaff")

    music_path = args.music
    if not music_path:
        default_music = PROJECT_ROOT / "music" / "upbeat.mp3"
        if default_music.exists():
            music_path = str(default_music)

    scene_files = []
    scene_idx = 0

    for seg in script["segments"]:
        seg_type = seg["type"]
        scene_idx += 1
        scene_dir = job_dir / f"seg{scene_idx:02d}_{seg_type}"
        scene_dir.mkdir(exist_ok=True)

        if seg_type == "clip":
            # Extract clip from source
            raw_clip = scene_dir / "raw_clip.mp4"
            final_clip = scene_dir / "clip.mp4"

            if final_clip.exists() and args.reuse:
                print(f"  Seg {scene_idx} (clip): reusing {seg.get('label', '')[:50]}")
            else:
                print(f"  Seg {scene_idx} (clip): {seg['start']:.1f}s - {seg['end']:.1f}s — {seg.get('label', '')[:50]}")
                extract_clip(source_clip, seg["start"], seg["end"], raw_clip)
                label = seg.get("label", "SOURCE")
                add_source_banner(raw_clip, final_clip, label, brand_color)
                # Clean up raw
                if raw_clip.exists():
                    raw_clip.unlink()

            scene_files.append(final_clip)

        elif seg_type in ("intro", "commentary", "outro"):
            narration_text = seg["narration"]
            keywords = seg.get("keywords", ["abstract background"])
            target_dur = seg.get("duration_target", 20)

            print(f"  Seg {scene_idx} ({seg_type}): {narration_text[:60]}...")

            # B-roll
            existing_broll = sorted(scene_dir.glob("broll_*.mp4"))
            if existing_broll and args.reuse:
                broll = existing_broll
                print(f"    Reusing b-roll")
            else:
                broll = fetch_broll(keywords, scene_dir, count=1)

            # Narration
            narration_wav = scene_dir / "narration.wav"
            if narration_wav.exists() and narration_wav.stat().st_size > 1000 and args.reuse:
                print(f"    Reusing narration")
            else:
                narrate_scene(narration_text, narration_wav)

            narration_dur = probe_duration(narration_wav)
            scene_dur = max(target_dur, narration_dur + 0.5)

            scene_mp4 = scene_dir / "scene.mp4"
            assemble_commentary(
                broll, narration_wav, scene_mp4, scene_dur,
                show_name=show_name,
                brand_color=brand_color,
            )
            scene_files.append(scene_mp4)
            print(f"    Done: {scene_dur:.1f}s")

    # Concat
    version = 1
    while (job_dir / f"reaction_v{version}.mp4").exists():
        version += 1
    final = job_dir / f"reaction_v{version}.mp4"

    print(f"\n  Concatenating {len(scene_files)} segments -> {final.name}")
    concat_scenes(scene_files, final, music_path=music_path)

    # Copy to user folder
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    user_name = f"Reaction_{stamp}_v{version}.mp4"
    user_copy = USER_OUT_DIR / user_name
    shutil.copy2(final, user_copy)

    total_dur = probe_duration(final)
    print(f"\n  DONE — {total_dur:.1f}s ({total_dur/60:.1f} min)")
    print(f"  Final: {final}")
    print(f"  User copy: {user_copy}")


if __name__ == "__main__":
    main()
