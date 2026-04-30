#!/usr/bin/env python3
"""
broll_enricher.py — Multi-source b-roll enricher for fundraiser video jobs.

Strategy (per scene):
  1. FLUX.1-schnell — generate 2 AI images using the script's keywords_sceneN prompts
  2. Wikimedia Commons — search for proper nouns found in the narration (biographical/historical scripts)

Keys loaded from ~/.keys/.env (ANTHROPIC_API_KEY) and ~/.env.hf (HF_TOKEN).

Usage:
    python3 broll_enricher.py --job fundraisers/The_Fire_Hose_20260429-120234 \\
                              --script scripts_fundraiser/fire_hose.json
"""

import json, os, sys, time, subprocess, urllib.request, urllib.parse
from pathlib import Path

SCENE_KEYS = [
    ("scene1_hook",     "keywords_scene1", "scene1"),
    ("scene2_problem",  "keywords_scene2", "scene2"),
    ("scene3_stakes",   "keywords_scene3", "scene3"),
    ("scene4_solution", "keywords_scene4", "scene4"),
    ("scene5_ask",      "keywords_scene5", "scene5"),
]

VIDEO_W, VIDEO_H   = 1920, 1080
KEN_BURNS_DURATION = 6   # seconds


# ---------- load keys ----------

def _load_env(path):
    env = {}
    try:
        for line in open(Path(path).expanduser()):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

_KEYS_ENV = _load_env("~/.keys/.env")
_HF_ENV   = _load_env("~/.env.hf")

ANTHROPIC_API_KEY = _KEYS_ENV.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
HF_TOKEN          = _HF_ENV.get("HF_TOKEN")   or os.environ.get("HF_TOKEN", "")
HF_URL            = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"


# ---------- FLUX image generation ----------

def generate_flux_image(prompt, out_path):
    """Generate an image via FLUX.1-schnell and save to out_path. Returns True on success."""
    if not HF_TOKEN:
        print("  ⚠️  No HF_TOKEN — skipping FLUX")
        return False

    full_prompt = f"{prompt}, cinematic dramatic lighting, photorealistic, widescreen, film still, no text, no watermarks"
    data = json.dumps({"inputs": full_prompt}).encode()
    req  = urllib.request.Request(HF_URL, data=data, headers={
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type":  "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            img_bytes = r.read()
        if len(img_bytes) < 5000:
            print(f"  ⚠️  FLUX returned tiny response ({len(img_bytes)} bytes)")
            return False
        with open(out_path, "wb") as f:
            f.write(img_bytes)
        return True
    except Exception as e:
        print(f"  ⚠️  FLUX error: {e}")
        return False


# ---------- proper noun extraction ----------

def extract_proper_nouns(text):
    """Extract proper nouns via Claude API. Falls back to empty list on failure."""
    if not ANTHROPIC_API_KEY:
        return []
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = (
            "Extract proper nouns from this narration. "
            "Return ONLY a JSON array of strings — specific people, organizations, places, "
            "or named events that are likely to have photographs on Wikimedia Commons. "
            "Exclude generic words, adjectives, and abstract concepts.\n\n"
            f"Text: {text}\n\nReturn format: [\"Name1\", \"Name2\"]"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        nouns = json.loads(raw)
        # filter out short, generic, or lowercase words
        return [n for n in nouns if len(n) > 3 and n[0].isupper()]
    except Exception as e:
        print(f"  ⚠️  Claude noun extraction failed: {e}")
        return []


# ---------- Wikimedia Commons with thumbnail URLs ----------

def _wikimedia_get(params):
    base = "https://commons.wikimedia.org/w/api.php"
    url  = base + "?" + urllib.parse.urlencode(params)
    req  = urllib.request.Request(url, headers={"User-Agent": "broll-enricher/1.0 (dmpgh.com)"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def search_wikimedia_thumbnails(query, thumb_width=1920, limit=6):
    """Search Wikimedia Commons and return (title, thumb_url) using thumbnail CDN URLs."""
    try:
        data = _wikimedia_get({
            "action":       "query",
            "generator":    "search",
            "gsrsearch":    query,
            "gsrnamespace": "6",
            "gsrlimit":     limit,
            "prop":         "imageinfo",
            "iiprop":       "url|mime|size|thumburl",
            "iiurlwidth":   thumb_width,
            "format":       "json",
        })
        results = []
        for page in data.get("query", {}).get("pages", {}).values():
            ii   = page.get("imageinfo", [{}])[0]
            mime = ii.get("mime", "")
            w    = ii.get("width", 0)
            h    = ii.get("height", 0)
            turl = ii.get("thumburl") or ii.get("url", "")
            if not mime.startswith("image/"):     continue
            if "svg" in mime.lower():             continue
            if w < 400 or h < 300:               continue
            results.append((page.get("title", ""), turl))
        return results
    except Exception as e:
        print(f"  ⚠️  Wikimedia search failed for '{query}': {e}")
        return []


def download_image(url, out_path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "broll-enricher/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 5000:
            return False
        with open(out_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    Download error: {e}")
        return False


# ---------- Ken Burns clip ----------

def make_ken_burns_clip(image_path, out_path, duration=KEN_BURNS_DURATION):
    """Convert still image → slow-zoom 1920×1080 Ken Burns clip."""
    fps    = 25
    frames = duration * fps
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-filter_complex",
        (
            f"scale={VIDEO_W*2}:{VIDEO_H*2}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_W*2}:{VIDEO_H*2},"
            f"zoompan=z='min(zoom+0.001,1.3)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={VIDEO_W}x{VIDEO_H}:fps={fps}"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"    FFmpeg error: {result.stderr[-200:]}")
    return result.returncode == 0


# ---------- main enricher ----------

def enrich_job(job_dir_path, script_override=None):
    job_dir = Path(job_dir_path).expanduser()
    if not job_dir.exists():
        print(f"❌ Job dir not found: {job_dir}")
        sys.exit(1)

    # locate script JSON
    if script_override:
        script_file = Path(script_override).expanduser()
        if not script_file.is_absolute():
            script_file = Path.cwd() / script_file
    else:
        candidates = sorted(job_dir.glob("script*.json")) + sorted(job_dir.glob("*.json"))
        candidates = [c for c in candidates if "broll" not in c.name]
        if not candidates:
            print(f"❌ No script JSON in {job_dir}. Pass --script explicitly.")
            sys.exit(1)
        script_file = candidates[0]

    print(f"📄 Script: {script_file}")
    with open(script_file) as f:
        script = json.load(f)

    total_clips = 0

    for scene_key, kw_key, scene_dir_name in SCENE_KEYS:
        narration = script.get(scene_key, "")
        keywords  = script.get(kw_key, [])
        if not narration and not keywords:
            continue

        scene_dir = job_dir / scene_dir_name
        if not scene_dir.exists():
            print(f"⚠️  {scene_dir_name} dir missing — skipping")
            continue

        existing = sorted(scene_dir.glob("broll_*.mp4"))
        next_n   = len(existing)

        print(f"\n{'='*52}")
        print(f"🎬 {scene_dir_name} — {len(existing)} existing clips")

        # --- FLUX: generate 2 AI images per scene using keywords ---
        flux_prompts = keywords[:2] if keywords else ([narration[:120]] if narration else [])
        for i, prompt in enumerate(flux_prompts):
            print(f"\n  🤖 FLUX [{i+1}/{len(flux_prompts)}]: {prompt[:70]}")
            img_path  = scene_dir / f"_flux_{next_n}.jpg"
            clip_path = scene_dir / f"broll_{next_n}.mp4"
            if generate_flux_image(prompt, img_path):
                print(f"  🎬 → {clip_path.name}")
                if make_ken_burns_clip(img_path, clip_path):
                    next_n      += 1
                    total_clips += 1
                    print(f"  ✅ Done")
                img_path.unlink(missing_ok=True)
            time.sleep(1)  # be polite to HF API

        # --- Wikimedia: search proper nouns for historical/biographical content ---
        if narration:
            print(f"\n  🔍 Extracting proper nouns for Wikimedia...")
            nouns = extract_proper_nouns(narration)
            print(f"     Nouns: {nouns}")

            wiki_clips = 0
            for noun in nouns:
                if wiki_clips >= 2:
                    break
                results = search_wikimedia_thumbnails(noun, limit=8)
                for title, thumb_url in results:
                    ext = thumb_url.rsplit(".", 1)[-1].lower().split("?")[0]
                    if ext not in ("jpg", "jpeg", "png"):
                        continue
                    img_path  = scene_dir / f"_wiki_{next_n}.{ext}"
                    clip_path = scene_dir / f"broll_{next_n}.mp4"
                    print(f"     ⬇️  {title[:55]}")
                    if download_image(thumb_url, img_path):
                        if make_ken_burns_clip(img_path, clip_path):
                            next_n      += 1
                            total_clips += 1
                            wiki_clips  += 1
                            print(f"     ✅ → {clip_path.name}")
                        img_path.unlink(missing_ok=True)
                        break
                time.sleep(0.5)

        print(f"\n  Scene total: now {next_n} clips in {scene_dir_name}")

    print(f"\n{'='*52}")
    print(f"✅ Enrichment done — {total_clips} new clips added")
    print(f"   Re-render with --reuse to pick them up.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Enrich job with FLUX + Wikimedia b-roll")
    ap.add_argument("--job",    required=True, help="Path to job directory")
    ap.add_argument("--script", default="",    help="Path to script JSON (optional)")
    args = ap.parse_args()
    enrich_job(args.job, args.script or None)
