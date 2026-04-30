#!/usr/bin/env python3
"""
broll_picker.py — fetch N Pexels candidates for a scene and show a picker UI.

Usage:
  python3 broll_picker.py <scene_dir> "<keywords>" [--count 5] [--with-context]

With --with-context, each candidate is shown as a contextual preview:
  [last 2s of prev scene] + [candidate + this scene's narration] + [first 2s of next scene]

So you judge the clip inside the real video flow, not as a floating snippet.

Example:
  python3 broll_picker.py \
    ~/KnockOff/fundraisers/National_MS_Society_20260410-180717/scene3 \
    "mother toddler empty" --count 5 --with-context

Writes:
  <scene_dir>/candidate_0.mp4 ... candidate_{N-1}.mp4      (raw Pexels)
  <scene_dir>/preview_0.mp4  ... preview_{N-1}.mp4         (with context, if --with-context)
  <scene_dir>/picker.html    (opens in browser)

After you pick, tell the assistant which number (e.g. "#2").
"""

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

import requests

# Scene durations from fundraiser_generator.py — keep in sync
SCENE_DURATIONS = {1: 8, 2: 12, 3: 15, 4: 15, 5: 10}
CONTEXT_SECONDS = 2.0  # lead-in and lead-out from neighboring scenes


def load_pexels_key():
    env_path = Path.home() / ".keys" / ".env"
    if not env_path.exists():
        sys.exit(f"ERROR: {env_path} not found")
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("PEXELS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: PEXELS_API_KEY not found in ~/.keys/.env")


def fetch_candidates(keywords: str, scene_dir: Path, count: int, api_key: str):
    """Fetch `count` Pexels videos and save as candidate_0.mp4 ... candidate_{N-1}.mp4."""
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {
        "query": keywords,
        "per_page": max(count * 2, count),  # overshoot in case some have no usable link
        "orientation": "landscape",
        "size": "medium",
    }
    print(f"  Pexels search: {keywords!r}")
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        sys.exit("  No videos found for those keywords.")

    saved = []
    for video in videos:
        if len(saved) >= count:
            break
        files = video.get("video_files", [])
        hd = [f for f in files if f.get("quality") == "hd" and f.get("width", 0) <= 1920]
        sd = [f for f in files if f.get("quality") == "sd"]
        pick = hd[0] if hd else (sd[0] if sd else (files[0] if files else None))
        if not pick or not pick.get("link"):
            continue
        idx = len(saved)
        out = scene_dir / f"candidate_{idx}.mp4"
        print(f"  downloading candidate_{idx}.mp4 ...")
        r = requests.get(pick["link"], stream=True, timeout=60)
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        saved.append({
            "idx": idx,
            "path": out.name,
            "pexels_id": video.get("id"),
            "pexels_url": video.get("url", ""),
            "user": (video.get("user") or {}).get("name", ""),
            "duration": video.get("duration", 0),
        })
    if not saved:
        sys.exit("  No usable candidates downloaded.")
    return saved


def probe_duration(path: Path) -> float:
    """Return media duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) if result.stdout.strip() else 0.0


def parse_scene_num(scene_dir: Path) -> int:
    """Extract scene number from a path like '.../scene3' -> 3."""
    m = re.match(r"scene(\d+)$", scene_dir.name)
    return int(m.group(1)) if m else 0


def build_context_preview(scene_dir: Path, candidate_path: Path, preview_path: Path) -> bool:
    """
    Build a preview clip that plays the candidate inside the video flow:
      [last N sec of prev scene] + [candidate + this scene's narration] + [first N sec of next scene]

    Prev/next scenes are optional (edges of the video).
    """
    scene_num = parse_scene_num(scene_dir)
    if not scene_num:
        print(f"  ⚠  cannot parse scene number from {scene_dir.name}")
        return False

    job_dir = scene_dir.parent
    narration_wav = scene_dir / "narration.wav"
    if not narration_wav.exists():
        print(f"  ⚠  missing narration.wav in {scene_dir}")
        return False

    target_duration = SCENE_DURATIONS.get(scene_num, 12)
    narration_dur = probe_duration(narration_wav)
    scene_dur = max(target_duration, narration_dur + 0.5)

    # Locate neighbor scenes (optional)
    prev_scene_mp4 = job_dir / f"scene{scene_num - 1}" / "scene.mp4"
    next_scene_mp4 = job_dir / f"scene{scene_num + 1}" / "scene.mp4"
    has_prev = prev_scene_mp4.exists()
    has_next = next_scene_mp4.exists()

    # Inputs and filter segments
    inputs = []
    segments = []  # list of (video_label, audio_label)
    idx = 0

    if has_prev:
        prev_dur = probe_duration(prev_scene_mp4)
        prev_ss = max(0.0, prev_dur - CONTEXT_SECONDS)
        inputs.extend(["-ss", f"{prev_ss:.3f}", "-t", f"{CONTEXT_SECONDS:.3f}", "-i", str(prev_scene_mp4)])
        segments.append((f"[{idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                         f"crop=1920:1080,setsar=1,fps=30,format=yuv420p[v{idx}]",
                         f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}]"))
        idx += 1

    # Candidate — stream-looped to scene_dur, with this scene's narration
    cand_input_idx = idx
    inputs.extend(["-stream_loop", "-1", "-t", f"{scene_dur:.3f}", "-i", str(candidate_path)])
    idx += 1
    narr_input_idx = idx
    inputs.extend(["-i", str(narration_wav)])
    idx += 1
    segments.append((
        f"[{cand_input_idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        f"crop=1920:1080,setsar=1,fps=30,format=yuv420p[vc]",
        f"[{narr_input_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad,atrim=0:{scene_dur:.3f}[ac]",
    ))
    # Rename candidate labels so concat grabs them
    cand_v_label = "vc"
    cand_a_label = "ac"

    post_segments_start = len(segments)
    if has_next:
        inputs.extend(["-ss", "0", "-t", f"{CONTEXT_SECONDS:.3f}", "-i", str(next_scene_mp4)])
        segments.append((f"[{idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                         f"crop=1920:1080,setsar=1,fps=30,format=yuv420p[v{idx}]",
                         f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}]"))
        next_v_label = f"v{idx}"
        next_a_label = f"a{idx}"
        idx += 1
    else:
        next_v_label = None
        next_a_label = None

    # Build concat: prev? + candidate + next?
    concat_pairs = []
    if has_prev:
        concat_pairs.append(("v0", "a0"))
    concat_pairs.append((cand_v_label, cand_a_label))
    if has_next:
        concat_pairs.append((next_v_label, next_a_label))

    n_segments = len(concat_pairs)
    concat_inputs_str = "".join(f"[{v}][{a}]" for v, a in concat_pairs)
    concat_filter = f"{concat_inputs_str}concat=n={n_segments}:v=1:a=1[v][a]"

    # Assemble full filter_complex
    filter_parts = []
    for seg in segments:
        filter_parts.append(seg[0])
        filter_parts.append(seg[1])
    filter_parts.append(concat_filter)
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(preview_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠  preview build failed: {result.stderr[-400:]}")
        return False
    return True


def write_picker_html(scene_dir: Path, candidates, keywords: str, scene_name: str, with_context: bool):
    """Generate an HTML page that previews all candidates side-by-side."""
    cards = []
    for c in candidates:
        src = c.get("preview_path") if with_context and c.get("preview_path") else c["path"]
        cards.append(f"""
        <div class="card">
          <div class="num">#{c['idx']}</div>
          <video controls muted preload="metadata" src="{src}"></video>
          <div class="meta">
            <div>Pexels ID: {c['pexels_id']}</div>
            <div>By: {c['user']}</div>
            <div>Duration: {c['duration']}s</div>
            <div><a href="{c['pexels_url']}" target="_blank">View on Pexels</a></div>
          </div>
        </div>
        """)
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>B-roll Picker — {scene_name}</title>
  <style>
    body {{ font-family: -apple-system, system-ui, sans-serif; background: #111; color: #eee; margin: 0; padding: 24px; }}
    h1 {{ margin: 0 0 4px 0; font-size: 20px; }}
    .sub {{ color: #888; margin-bottom: 20px; font-size: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .card {{ background: #1c1c24; border-radius: 8px; padding: 12px; border: 1px solid #2a2a35; }}
    .num {{ font-size: 24px; font-weight: 700; color: #e94560; margin-bottom: 8px; }}
    video {{ width: 100%; border-radius: 4px; background: #000; }}
    .meta {{ margin-top: 8px; font-size: 12px; color: #aaa; line-height: 1.6; }}
    .meta a {{ color: #4fc3f7; text-decoration: none; }}
    .tip {{ margin-top: 24px; padding: 12px; background: #1a1a2e; border-left: 3px solid #e94560; font-size: 13px; color: #ccc; }}
  </style>
</head>
<body>
  <h1>B-roll Picker — {scene_name}</h1>
  <div class="sub">Keywords: <code>{keywords}</code> &nbsp;|&nbsp; {len(candidates)} candidates{' &nbsp;|&nbsp; <b>with context</b> (prev scene tail → candidate + narration → next scene head)' if with_context else ''}</div>
  <div class="grid">
    {''.join(cards)}
  </div>
  <div class="tip">Watch each clip. When you've picked one, tell the assistant the number (e.g. "#2") and it will swap that candidate into <code>broll_0.mp4</code> and re-render.</div>
</body>
</html>
"""
    out = scene_dir / "picker.html"
    out.write_text(html)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir", help="Path to scene folder (e.g. .../scene3)")
    ap.add_argument("keywords", help="Search keywords (quoted)")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--with-context", action="store_true",
                    help="Build contextual previews that include surrounding scenes")
    ap.add_argument("--reuse-candidates", action="store_true",
                    help="Skip Pexels fetch; rebuild previews from existing candidate_*.mp4")
    args = ap.parse_args()

    scene_dir = Path(args.scene_dir).expanduser().resolve()
    if not scene_dir.is_dir():
        sys.exit(f"Scene dir not found: {scene_dir}")

    if args.reuse_candidates:
        existing = sorted(scene_dir.glob("candidate_*.mp4"))
        if not existing:
            sys.exit("No existing candidate_*.mp4 to reuse.")
        candidates = [{
            "idx": i,
            "path": p.name,
            "pexels_id": "",
            "pexels_url": "",
            "user": "",
            "duration": probe_duration(p),
        } for i, p in enumerate(existing)]
        print(f"  ♻  reusing {len(candidates)} existing candidates")
    else:
        api_key = load_pexels_key()
        # Clean old candidates + previews
        for old in scene_dir.glob("candidate_*.mp4"):
            old.unlink()
        for old in scene_dir.glob("preview_*.mp4"):
            old.unlink()
        candidates = fetch_candidates(args.keywords, scene_dir, args.count, api_key)

    if args.with_context:
        print(f"\n  Building contextual previews ({CONTEXT_SECONDS}s lead-in/out) ...")
        for c in candidates:
            cand_path = scene_dir / c["path"]
            preview_path = scene_dir / f"preview_{c['idx']}.mp4"
            ok = build_context_preview(scene_dir, cand_path, preview_path)
            if ok:
                c["preview_path"] = preview_path.name
                print(f"    ✓ preview_{c['idx']}.mp4")
            else:
                print(f"    ✗ preview_{c['idx']}.mp4 — falling back to raw candidate")

    picker_html = write_picker_html(scene_dir, candidates, args.keywords, scene_dir.name, args.with_context)

    print(f"\n  {len(candidates)} candidates in {scene_dir}")
    print(f"  Picker: {picker_html}")
    print(f"\n  Opening in browser...")
    webbrowser.open(f"file://{picker_html}")


if __name__ == "__main__":
    main()
