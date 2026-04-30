#!/usr/bin/env python3
"""
Stitch a fundraiser-pipeline episode with Remotion graphics.

Takes:
  - A finished fundraiser render directory (has scene1..scene5 subdirs, each with a rendered MP4)
  - The Remotion clips we pre-rendered for this episode (intro, story-cards, credits)
  - Background music

Produces: final.mp4 with Remotion replacing bumper + title cards + credits.

Final structure:
  [remotion intro 5s] → [scene1 hook] → [story-card-1 2.5s] → [scene2 story1]
  → [story-card-2 2.5s] → [scene3 story2] → [story-card-3 2.5s] → [scene4 story3]
  → [scene5 ask] → [remotion credits 18s]

Usage:
    python3 tools/stitch_with_remotion.py --fundraiser-dir <render_dir> --episode 35 --out final.mp4
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"


def normalize_clip(src, dst, fps=30, w=1920, h=1080):
    """Re-encode to identical specs so concat demuxer doesn't drift audio."""
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if not dst.exists():
        print(f"  normalize failed: {src.name} → {r.stderr[-400:].decode(errors='replace')}")
        return False
    return True


def add_silent_audio(src, dst):
    """Add a silent audio track to a video that has none."""
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True)
    return dst.exists()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundraiser-dir", required=True, help="Path to fundraiser render dir")
    ap.add_argument("--episode", "-e", type=int, required=True)
    ap.add_argument("--out", required=True, help="Final output MP4 path")
    args = ap.parse_args()

    fundraiser_dir = Path(args.fundraiser_dir)
    ep_dir = SHOW_DIR / f"ep{args.episode}"
    remotion_dir = ep_dir / "remotion"

    # Find the fundraiser scene files
    scene_files = []
    for i in range(1, 6):
        # Look for sceneN mp4 inside the render dir
        scene_dir = fundraiser_dir / f"scene{i}"
        candidates = list(scene_dir.glob("*.mp4")) if scene_dir.exists() else []
        # Prefer the largest one (the composed scene, not raw b-roll clips)
        candidates = sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            print(f"  ERROR: no scene{i} MP4 found in {scene_dir}")
            sys.exit(1)
        scene_files.append(candidates[0])

    # Remotion clips
    intro = remotion_dir / "intro.mp4"
    cards = [remotion_dir / f"story-card-{i}.mp4" for i in (1, 2, 3)]
    credits = remotion_dir / "credits.mp4"

    for p in [intro, *cards, credits]:
        if not p.exists():
            print(f"  ERROR: missing Remotion clip {p}")
            sys.exit(1)

    # Normalize everything into a temp dir
    tmp = ep_dir / "_stitch"
    tmp.mkdir(exist_ok=True)

    print("🔧 Normalizing clips...")
    norm_paths = []

    def norm(src, name):
        dst = tmp / f"{name}.mp4"
        # Remotion clips have no audio — add silent track first
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a", "-show_streams", str(src)],
            capture_output=True, text=True
        )
        if "codec_type=audio" not in probe.stdout:
            silent = tmp / f"{name}_with_audio.mp4"
            add_silent_audio(src, silent)
            src = silent
        if not normalize_clip(src, dst):
            sys.exit(1)
        print(f"   ✓ {name}")
        return dst

    norm_paths.append(norm(intro, "00_intro"))
    norm_paths.append(norm(scene_files[0], "01_hook"))
    norm_paths.append(norm(cards[0], "02_card1"))
    norm_paths.append(norm(scene_files[1], "03_story1"))
    norm_paths.append(norm(cards[1], "04_card2"))
    norm_paths.append(norm(scene_files[2], "05_story2"))
    norm_paths.append(norm(cards[2], "06_card3"))
    norm_paths.append(norm(scene_files[3], "07_story3"))
    norm_paths.append(norm(scene_files[4], "08_outro"))
    norm_paths.append(norm(credits, "09_credits"))

    # Write concat file
    list_file = tmp / "concat.txt"
    with open(list_file, "w") as f:
        for p in norm_paths:
            f.write(f"file '{p}'\n")

    print(f"\n🔗 Concatenating {len(norm_paths)} clips...")
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if not out_path.exists():
        print(f"  concat failed: {r.stderr[-500:].decode(errors='replace')}")
        sys.exit(1)

    # Probe final
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(out_path)],
        capture_output=True, text=True,
    )
    fmt = json.loads(probe.stdout)["format"]
    dur = float(fmt["duration"])
    size_mb = out_path.stat().st_size / 1024 / 1024

    print(f"\n✅ Final: {out_path}")
    print(f"   Duration: {int(dur//60)}:{int(dur%60):02d}")
    print(f"   Size: {size_mb:.0f} MB")


if __name__ == "__main__":
    main()
