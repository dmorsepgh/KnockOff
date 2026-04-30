#!/usr/bin/env python3
"""
KnockOff API Server — REST API wrapper for showrunner.py

Runs on M4 Pro, exposes endpoints for MotherShowRunner on NAS to call.
"""

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file

# Load central keys
try:
    from dotenv import load_dotenv
    load_dotenv("/Users/douglasmorse/.keys/.env")
except ImportError:
    pass

# Make heygen_client importable
sys.path.insert(0, str(Path(__file__).parent))

app = Flask(__name__)

PROJECT_ROOT = Path(__file__).parent
SHOWRUNNER_SCRIPT = PROJECT_ROOT / "tools" / "showrunner.py"
SHOW_DIR = PROJECT_ROOT / "show"
VENDING_DIR = PROJECT_ROOT / "vending"
VENDING_DIR.mkdir(exist_ok=True)

SCRIPT_FILES = [
    "heygen-opening.txt",
    "heygen-combined.txt",
    "heygen-closing.txt",
    "pictory-combined.txt",
    "pictory-story1.txt",
    "pictory-story2.txt",
    "pictory-story3.txt",
]


def _ep_num(name):
    m = re.match(r"ep(\d+)$", name)
    return int(m.group(1)) if m else None


def load_episode(ep_num):
    """Load an episode's metadata + all script contents from disk."""
    ep_dir = SHOW_DIR / f"ep{ep_num}"
    json_path = ep_dir / "episode.json"
    if not json_path.exists():
        return None

    data = json.loads(json_path.read_text())
    data["episode"] = ep_num

    scripts = {}
    for filename in SCRIPT_FILES:
        f = ep_dir / filename
        if f.exists():
            scripts[filename] = f.read_text()
    data["scripts"] = scripts
    return data


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route('/episodes', methods=['GET'])
def list_episodes():
    """List all episodes with metadata (no script contents - lightweight)."""
    if not SHOW_DIR.exists():
        return jsonify({"episodes": []})

    episodes = []
    for d in sorted(SHOW_DIR.iterdir()):
        if not d.is_dir():
            continue
        num = _ep_num(d.name)
        if num is None:
            continue
        json_path = d / "episode.json"
        if not json_path.exists():
            continue
        try:
            meta = json.loads(json_path.read_text())
            meta["episode"] = num
            # Strip heavy fields for the list view
            meta.pop("scripts", None)
            episodes.append(meta)
        except Exception:
            continue

    episodes.sort(key=lambda e: e.get("episode", 0), reverse=True)
    return jsonify({"episodes": episodes})


@app.route('/episode/<int:ep_num>', methods=['GET'])
def get_episode(ep_num):
    """Get full episode data including all script contents."""
    data = load_episode(ep_num)
    if data is None:
        return jsonify({"error": "Episode not found"}), 404
    return jsonify(data)


@app.route('/episode/<int:ep_num>', methods=['POST'])
def save_episode(ep_num):
    """Save edited script content back to disk."""
    ep_dir = SHOW_DIR / f"ep{ep_num}"
    if not ep_dir.exists():
        return jsonify({"error": "Episode not found"}), 404

    updates = request.json.get("scripts", {})
    for filename, content in updates.items():
        if filename in SCRIPT_FILES:
            (ep_dir / filename).write_text(content)

    return jsonify({"success": True})


@app.route('/generate-episode', methods=['POST'])
def generate_episode():
    """Generate a new episode for a show."""
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        show_name = data.get('show_name', '').strip()
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

        if not topic:
            return jsonify({"error": "topic is required"}), 400

        # Snapshot existing episode numbers so we can detect the new one
        existing = set()
        if SHOW_DIR.exists():
            for d in SHOW_DIR.iterdir():
                n = _ep_num(d.name)
                if n is not None:
                    existing.add(n)

        cmd = [
            sys.executable, str(SHOWRUNNER_SCRIPT),
            topic,
            '--show-name', show_name,
            '--date', date
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(PROJECT_ROOT)
        )

        if result.returncode != 0:
            return jsonify({
                "success": False,
                "error": result.stderr,
                "output": result.stdout
            }), 500

        # Find the newly created episode
        new_num = None
        if SHOW_DIR.exists():
            current = set()
            for d in SHOW_DIR.iterdir():
                n = _ep_num(d.name)
                if n is not None:
                    current.add(n)
            new_nums = current - existing
            if new_nums:
                new_num = max(new_nums)

        response = {
            "success": True,
            "output": result.stdout,
            "error": result.stderr,
        }

        if new_num is not None:
            response["episode_num"] = new_num
            # Include the full episode data so the caller has everything
            ep_data = load_episode(new_num)
            if ep_data:
                response["episode"] = ep_data

        return jsonify(response)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Episode generation timed out"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================================
# Segment endpoint — runs segment_generator.py with user-picked stories
# (the new pipeline: OpenAI TTS + Pexels B-roll, no HeyGen/Pictory)
# =========================================================================

segment_jobs = {}


@app.route('/generate-segment', methods=['POST'])
def generate_segment():
    """Hatch an episode using segment_generator.py with a picked-stories list.

    Body: {
      "picked_stories": [{"title": ..., "source": ..., "description": ..., "summary": ...}, ...],
      "show_name": "AI Views & News",
      "topic": "ai",
      "date": "2026-04-14",          # optional
      "voice": "onyx"                 # optional OpenAI voice
    }
    Returns: { job_id }
    Poll /segment-job/<job_id> for status.
    """
    data = request.json or {}
    picks = data.get("picked_stories") or []
    show_name = data.get("show_name", "AI Views & News")
    topic = data.get("topic", "AI news")
    date_str = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    voice = data.get("voice", "onyx")

    if not picks:
        return jsonify({"error": "picked_stories list is required"}), 400

    job_id = uuid.uuid4().hex[:8]
    segment_jobs[job_id] = {
        "status": "starting",
        "message": "Queued",
        "percent": 2,
        "started_at": datetime.now().isoformat(),
    }

    # Write picks to a temp JSON the subprocess will read
    picks_dir = PROJECT_ROOT / "scripts_fundraiser"
    picks_dir.mkdir(exist_ok=True)
    picks_path = picks_dir / f"picks_{job_id}.json"
    picks_path.write_text(json.dumps(picks, indent=2))

    segment_script = PROJECT_ROOT / "segment_generator.py"
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"segment_{job_id}.log"

    cmd = [
        sys.executable, str(segment_script),
        "--topic", topic,
        "--show-name", show_name,
        "--date", date_str,
        "--voice", voice,
        "--picked-stories-json", str(picks_path),
    ]

    def run():
        segment_jobs[job_id].update(status="running", message="Generating script & narration...", percent=8)
        try:
            with open(log_path, "w") as logf:
                result = subprocess.run(
                    cmd,
                    stdout=logf, stderr=subprocess.STDOUT,
                    text=True, timeout=1800,
                    cwd=str(PROJECT_ROOT),
                )
            if result.returncode == 0:
                # Find the newest news_segments dir we just wrote
                out_root = PROJECT_ROOT / "news_segments"
                newest = None
                if out_root.exists():
                    dirs = [d for d in out_root.iterdir() if d.is_dir()]
                    if dirs:
                        newest = max(dirs, key=lambda d: d.stat().st_mtime)
                segment_jobs[job_id].update(
                    status="complete",
                    message="Segment rendered",
                    percent=100,
                    output_dir=str(newest) if newest else None,
                    video=str(newest / "segment_v1.mp4") if newest and (newest / "segment_v1.mp4").exists() else None,
                    log=str(log_path),
                )
            else:
                segment_jobs[job_id].update(
                    status="failed",
                    message=f"segment_generator exited {result.returncode}",
                    percent=0,
                    log=str(log_path),
                )
        except subprocess.TimeoutExpired:
            segment_jobs[job_id].update(status="failed", message="Timed out after 30 min", percent=0, log=str(log_path))
        except Exception as e:
            segment_jobs[job_id].update(status="failed", message=str(e), percent=0, log=str(log_path))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route('/segment-job/<job_id>', methods=['GET'])
def segment_job_status(job_id):
    job = segment_jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


# =========================================================================
# Vending endpoints — Studio "any script into a video"
# =========================================================================

@app.route('/write-script', methods=['POST'])
def write_script_endpoint():
    """
    Generate a script for a topic using local Ollama.
    Returns {success, script}.
    """
    data = request.json or {}
    topic = data.get('topic', '').strip()
    seconds = int(data.get('seconds', 60))

    if not topic:
        return jsonify({"success": False, "error": "topic required"}), 400

    # Target ~150 words per minute
    target_words = max(20, int((seconds / 60.0) * 150))

    prompt = (
        f"Write a SHORT, punchy script for a {seconds}-second video about: {topic}.\n"
        f"The script should be approximately {target_words} words.\n"
        f"Write it as natural, conversational speech — as if someone is speaking directly to camera.\n"
        f"Do NOT include stage directions, labels, or any text that isn't meant to be spoken.\n"
        f"Just return the script text, nothing else."
    )

    try:
        result = subprocess.run(
            ["ollama", "run", "mistral-small"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
        script = result.stdout.strip()
        if not script:
            return jsonify({"success": False, "error": "empty script from model"}), 500
        return jsonify({"success": True, "script": script, "target_words": target_words})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/vending/generate', methods=['POST'])
def vending_generate():
    """
    Full pipeline: photo + script → HeyGen video → return URL.
    For now, uses default DMPGH avatar and Doug voice (until photo→avatar is wired).
    """
    try:
        from heygen_client import (
            generate_video, wait_for_video, download_video,
            check_remaining_credits,
        )
    except Exception as e:
        return jsonify({"error": f"HeyGen client unavailable: {e}"}), 500

    script = (request.form.get('script') or '').strip()
    email = (request.form.get('email') or '').strip()
    seconds = int(request.form.get('seconds', 60))
    fmt = request.form.get('format', 'landscape')
    job_id = request.form.get('job_id') or uuid.uuid4().hex[:8]

    if not script:
        return jsonify({"error": "script required"}), 400

    # Check credits BEFORE doing anything
    credits = check_remaining_credits()
    api_credits = credits.get('details', {}).get('api', 0)
    needed = max(1, seconds)
    if api_credits < needed:
        return jsonify({"error": f"Insufficient HeyGen credits. Need ~{needed}, have {api_credits}"}), 402

    # Save job data
    job_dir = VENDING_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    photo = request.files.get('photo')
    if photo:
        photo_path = job_dir / f"photo{Path(photo.filename).suffix or '.jpg'}"
        photo.save(photo_path)
    voice = request.files.get('voice')
    if voice:
        voice_path = job_dir / f"voice{Path(voice.filename).suffix or '.mp3'}"
        voice.save(voice_path)

    (job_dir / "script.txt").write_text(script)
    (job_dir / "order.json").write_text(json.dumps({
        "job_id": job_id,
        "email": email,
        "seconds": seconds,
        "format": fmt,
        "created": datetime.now().isoformat(),
    }, indent=2))

    # Dimensions
    if fmt == "vertical":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    # TODO: when photo→avatar is wired, create custom avatar from upload.
    # For now, use default DMPGH + Doug voice.
    AVATAR_ID = os.environ.get("DEFAULT_AVATAR_ID", "c655a8229ba449f99c14fc8ae5b7f64f")
    VOICE_ID = os.environ.get("DEFAULT_VOICE_ID", "2n9kTv3MBZ7LvK33Nhxm")

    try:
        video_id = generate_video(
            AVATAR_ID, script,
            voice_id=VOICE_ID,
            width=width, height=height,
        )
        video_url = wait_for_video(video_id, max_wait=600, poll_interval=10)
        out_path = job_dir / "video.mp4"
        download_video(video_url, out_path)

        after = check_remaining_credits()
        credits_used = api_credits - after.get('details', {}).get('api', 0)

        return jsonify({
            "success": True,
            "job_id": job_id,
            "video_url": f"/vending/download/{job_id}",
            "credits_used": credits_used,
            "cost_estimate": round(credits_used * 0.017, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/vending/download/<job_id>')
def vending_download(job_id):
    """Serve a finished video file."""
    # Allow only safe job_id chars
    if not re.match(r'^[a-f0-9]+$', job_id):
        return jsonify({"error": "invalid job id"}), 400
    video_path = VENDING_DIR / job_id / "video.mp4"
    if not video_path.exists():
        return jsonify({"error": "video not found"}), 404
    return send_file(str(video_path), mimetype='video/mp4')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
