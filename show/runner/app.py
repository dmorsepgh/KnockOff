#!/opt/homebrew/bin/python3
"""
AI Views and News — Weekly Show Runner

Web dashboard for producing AI Views and News episodes:
1. Browse today's collected news stories
2. Check 3 stories to feature
3. Generate all 5 scripts (2 HeyGen avatar + 3 Pictory B-roll)
4. Copy/save scripts, ready for HeyGen and Pictory
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory

PROJECT_ROOT = Path(__file__).parent.parent.parent  # ~/KnockOff
NEWS_DIR = PROJECT_ROOT / "news"
SHOW_DIR = PROJECT_ROOT / "show"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
STATIC_DIR = Path(__file__).parent

JOBS_DIR = Path(__file__).parent / "jobs"
UPLOADS_DIR = Path(__file__).parent / "uploads"

app = Flask(__name__, static_folder=str(STATIC_DIR))

# ─── Episode counter ──────────────────────────────────────────────────────

def get_next_episode_number():
    """Find the next episode number by scanning existing ep directories."""
    existing = sorted(SHOW_DIR.glob("ep*"))
    if not existing:
        return 1
    nums = []
    for d in existing:
        try:
            nums.append(int(d.name.replace("ep", "")))
        except ValueError:
            continue
    return max(nums) + 1 if nums else 1


# ─── News endpoints ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/pitch/<path:filename>")
def serve_pitch_file(filename):
    """Serve files from the pitch directory."""
    pitch_dir = SHOW_DIR / "pitch"
    return send_from_directory(str(pitch_dir), filename)


@app.route("/rendermonkey")
def rendermonkey_page():
    """Serve the Render Monkey landing page."""
    pitch_dir = SHOW_DIR / "pitch"
    return send_from_directory(str(pitch_dir), "render-monkey-landing.html")


@app.route("/partner")
def partner_page():
    """Serve the partner pitch page."""
    pitch_dir = SHOW_DIR / "pitch"
    return send_from_directory(str(pitch_dir), "partner-pitch.html")


@app.route("/invite")
def invite_page():
    """Serve the free trial invitation page."""
    pitch_dir = SHOW_DIR / "pitch"
    return send_from_directory(str(pitch_dir), "free-trial-email.html")


@app.route("/api/news")
def get_news():
    """Return available news dates and stories."""
    # Find all news JSON files, most recent first
    files = sorted(NEWS_DIR.glob("news-*.json"), reverse=True)
    dates = []
    for f in files[:14]:  # Last 2 weeks
        date_str = f.stem.replace("news-", "")
        try:
            stories = json.loads(f.read_text())
            dates.append({
                "date": date_str,
                "count": len(stories),
                "stories": stories
            })
        except Exception:
            continue
    return jsonify(dates)


@app.route("/api/news/<date>")
def get_news_for_date(date):
    """Return stories for a specific date."""
    path = NEWS_DIR / f"news-{date}.json"
    if not path.exists():
        return jsonify({"error": "No news for that date"}), 404
    stories = json.loads(path.read_text())
    return jsonify(stories)


@app.route("/api/collect-news", methods=["POST"])
def collect_news():
    """Run the news collector to get fresh stories."""
    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "news_collector.py")],
            capture_output=True, text=True, timeout=120
        )
        return jsonify({
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Script generation ────────────────────────────────────────────────────

HEYGEN_WORD_LIMIT = 270  # HeyGen Unlimited plan limit per segment

SHOW_NAME = "AI Views and News"
HOST_NAME = "Doug Morse"
WEBSITE = "dmpgh.com"


def generate_opening_script(stories, episode_num):
    """Generate the HeyGen opening script."""
    story_teases = "\n".join(
        f"- {s['title']} ({s['source']})" for s in stories
    )

    prompt = f"""Write a 90-second opening script for episode {episode_num} of "{SHOW_NAME}".

HOST: {HOST_NAME}
FORMAT: Single person speaking directly to camera. Warm, confident, conversational.

RULES:
- MUST be under {HEYGEN_WORD_LIMIT} words (this is critical — count carefully)
- No stage directions, no parentheticals, no [brackets]
- Just the words Doug speaks, nothing else
- Natural, conversational tone — like talking to a smart friend
- Welcome viewers, tease the 3 stories coming up, build excitement
- End with a transition like "Let's get into it" or "Here's what you need to know"

THE 3 STORIES TO TEASE:
{story_teases}

Write ONLY the spoken words. No headers, no labels, no formatting."""

    return _run_ollama(prompt)


def generate_pictory_script(story, segment_num):
    """Generate a Pictory B-roll news script for one story."""
    prompt = f"""Write a 2-3 minute narrated news segment script about this story.

STORY: {story['title']}
SOURCE: {story['source']}
DESCRIPTION: {story.get('description', '')}
SUMMARY: {story.get('summary', '')}

FORMAT: Narration over B-roll video. Pictory will auto-match visuals to the text.

RULES:
- Write in short, punchy paragraphs (2-3 sentences each)
- Each paragraph becomes a scene in Pictory — think visually
- Open with a hook that grabs attention
- Explain the story clearly for a general audience
- Include why this matters and what comes next
- Conversational but authoritative tone
- Aim for 350-450 words (about 2-3 minutes when read)
- No stage directions, no [brackets], no headers
- Just the narration text, paragraph by paragraph
- Use line breaks between paragraphs (Pictory uses these as scene breaks)

Write ONLY the narration. No labels, no scene numbers, no formatting."""

    return _run_ollama(prompt)


def generate_closing_script(stories, episode_num):
    """Generate the HeyGen closing script."""
    story_refs = "\n".join(f"- {s['title']}" for s in stories)

    prompt = f"""Write a 90-second closing script for episode {episode_num} of "{SHOW_NAME}".

HOST: {HOST_NAME}
FORMAT: Single person speaking directly to camera.

RULES:
- MUST be under {HEYGEN_WORD_LIMIT} words (critical — count carefully)
- No stage directions, no parentheticals, no [brackets]
- Just the words Doug speaks
- Briefly recap what we covered (1-2 sentences per story)
- Thank viewers for watching
- Mention the show website: {WEBSITE}
- Hand off to Drake and Carter's Q&A session
- Sign off: "I'm {HOST_NAME}. See you next week."
- Warm, natural tone

STORIES COVERED:
{story_refs}

Write ONLY the spoken words. No headers, no labels."""

    return _run_ollama(prompt)


def _run_ollama(prompt):
    """Run a prompt through Ollama and return the response."""
    result = subprocess.run(
        ["ollama", "run", "llama3.1:8b"],
        input=prompt,
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama failed: {result.stderr}")
    return result.stdout.strip()


@app.route("/api/generate-scripts", methods=["POST"])
def generate_scripts():
    """Generate all 5 scripts from 3 selected stories."""
    data = request.json
    date = data.get("date")
    selected_indices = data.get("stories", [])  # List of story indices

    if len(selected_indices) != 3:
        return jsonify({"error": "Select exactly 3 stories"}), 400

    # Load stories
    path = NEWS_DIR / f"news-{date}.json"
    if not path.exists():
        return jsonify({"error": f"No news for {date}"}), 404

    all_stories = json.loads(path.read_text())
    stories = [all_stories[i] for i in selected_indices]

    episode_num = get_next_episode_number()

    scripts = {}
    errors = []

    # Generate all 5 scripts
    try:
        scripts["opening"] = generate_opening_script(stories, episode_num)
    except Exception as e:
        errors.append(f"Opening: {e}")
        scripts["opening"] = ""

    for i, story in enumerate(stories):
        try:
            scripts[f"story{i+1}"] = generate_pictory_script(story, i + 1)
        except Exception as e:
            errors.append(f"Story {i+1}: {e}")
            scripts[f"story{i+1}"] = ""

    try:
        scripts["closing"] = generate_closing_script(stories, episode_num)
    except Exception as e:
        errors.append(f"Closing: {e}")
        scripts["closing"] = ""

    return jsonify({
        "episode": episode_num,
        "scripts": scripts,
        "stories": [{"title": s["title"], "source": s["source"]} for s in stories],
        "errors": errors if errors else None
    })


@app.route("/api/save-episode", methods=["POST"])
def save_episode():
    """Save all scripts to an episode directory."""
    data = request.json
    episode_num = data.get("episode")
    scripts = data.get("scripts", {})
    stories = data.get("stories", [])
    date = data.get("date")

    ep_dir = SHOW_DIR / f"ep{episode_num}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    # Save each script
    files_saved = []

    if scripts.get("opening"):
        p = ep_dir / "heygen-opening.txt"
        p.write_text(scripts["opening"])
        files_saved.append(str(p))

    for i in range(1, 4):
        key = f"story{i}"
        if scripts.get(key):
            p = ep_dir / f"pictory-story{i}.txt"
            p.write_text(scripts[key])
            files_saved.append(str(p))

    if scripts.get("closing"):
        p = ep_dir / "heygen-closing.txt"
        p.write_text(scripts["closing"])
        files_saved.append(str(p))

    # Generate host notes
    host_notes = generate_host_notes(episode_num, date, stories, scripts)
    (ep_dir / "host-notes.md").write_text(host_notes)
    files_saved.append(str(ep_dir / "host-notes.md"))

    # Save episode metadata
    meta = {
        "episode": episode_num,
        "date": date,
        "created": datetime.now().isoformat(),
        "stories": stories,
        "scripts": {k: str(ep_dir / f) for k, f in {
            "opening": "heygen-opening.txt",
            "story1": "pictory-story1.txt",
            "story2": "pictory-story2.txt",
            "story3": "pictory-story3.txt",
            "closing": "heygen-closing.txt",
        }.items()},
        "include_intro_bumper": data.get("include_intro_bumper", True),
        "include_credits_bumper": data.get("include_credits_bumper", True),
        "status": "scripts_ready"
    }
    (ep_dir / "episode.json").write_text(json.dumps(meta, indent=2))
    files_saved.append(str(ep_dir / "episode.json"))

    return jsonify({
        "success": True,
        "episode_dir": str(ep_dir),
        "files": files_saved
    })


@app.route("/api/episodes/<int:episode_num>/scripts")
def get_episode_scripts(episode_num):
    """Return all scripts for an episode so it can be loaded in the editor."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    meta_path = ep_dir / "episode.json"
    if not meta_path.exists():
        return jsonify({"error": "Episode not found"}), 404

    meta = json.loads(meta_path.read_text())
    scripts = {}

    # Read each script file
    for key, filename in [
        ("opening", "heygen-opening.txt"),
        ("story1", "pictory-story1.txt"),
        ("story2", "pictory-story2.txt"),
        ("story3", "pictory-story3.txt"),
        ("closing", "heygen-closing.txt"),
    ]:
        script_path = ep_dir / filename
        if script_path.exists():
            scripts[key] = script_path.read_text()
        else:
            scripts[key] = ""

    return jsonify({
        "episode": meta.get("episode", episode_num),
        "date": meta.get("date", ""),
        "stories": meta.get("stories", []),
        "scripts": scripts,
        "status": meta.get("status", "unknown"),
        "include_intro_bumper": meta.get("include_intro_bumper", True),
        "include_credits_bumper": meta.get("include_credits_bumper", True),
    })


@app.route("/api/episodes/<int:episode_num>/video")
def serve_episode_video(episode_num):
    """Serve the final episode video for streaming or download."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    meta_path = ep_dir / "episode.json"
    if not meta_path.exists():
        return jsonify({"error": "Episode not found"}), 404

    meta = json.loads(meta_path.read_text())
    video_file = meta.get("final_video")
    if not video_file:
        return jsonify({"error": "No video for this episode"}), 404

    video_path = ep_dir / video_file
    if not video_path.exists():
        return jsonify({"error": "Video file missing"}), 404

    return send_from_directory(str(ep_dir), video_file, mimetype="video/mp4")


@app.route("/api/episodes/<int:episode_num>/download")
def download_episode_video(episode_num):
    """Download the final episode video."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    meta_path = ep_dir / "episode.json"
    if not meta_path.exists():
        return jsonify({"error": "Episode not found"}), 404

    meta = json.loads(meta_path.read_text())
    video_file = meta.get("final_video")
    if not video_file:
        return jsonify({"error": "No video for this episode"}), 404

    video_path = ep_dir / video_file
    if not video_path.exists():
        return jsonify({"error": "Video file missing"}), 404

    return send_from_directory(
        str(ep_dir), video_file, mimetype="video/mp4",
        as_attachment=True,
        download_name=f"AI-Views-and-News-EP{episode_num}.mp4"
    )


@app.route("/api/episodes/<int:episode_num>/crypt-notes")
def serve_crypt_notes(episode_num):
    """Serve the Crypt Notes HTML page."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    crypt_path = ep_dir / "crypt-notes.html"
    if not crypt_path.exists():
        return jsonify({"error": "No Crypt Notes for this episode"}), 404
    return send_from_directory(str(ep_dir), "crypt-notes.html")


@app.route("/api/episodes/<int:episode_num>/stitch", methods=["POST"])
def api_stitch_episode(episode_num):
    """Auto-stitch an episode from uploaded renders + bumpers."""
    if not check_manager_auth():
        return jsonify({"error": "Unauthorized"}), 401

    ep_dir = SHOW_DIR / f"ep{episode_num}"
    if not ep_dir.exists():
        return jsonify({"error": "Episode not found"}), 404

    meta_path = ep_dir / "episode.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    date = meta.get("date", datetime.now().strftime("%Y-%m-%d"))

    import shutil

    # 1. Generate bumpers
    generate_intro_bumper(ep_dir, episode_num, date)
    generate_credits_bumper(ep_dir, episode_num, date)

    # 2. Find the uploaded renders
    heygen_raw = ep_dir / "heygen-combined.mp4"
    pictory_raw = ep_dir / "pictory-combined.mp4"

    if not heygen_raw.exists() or not pictory_raw.exists():
        return jsonify({"error": "Missing renders. Need both heygen-combined.mp4 and pictory-combined.mp4"}), 400

    # 3. Re-encode everything to 30fps
    segments = [
        ("intro-bumper.mp4", None),   # Already 30fps from generation
        ("heygen-combined.mp4", "seg1.mp4"),
        ("pictory-combined.mp4", "seg2.mp4"),
        ("credits-bumper.mp4", None),  # Already 30fps
    ]

    for src, dest in segments:
        if dest:
            src_path = ep_dir / src
            dest_path = ep_dir / dest
            result = subprocess.run([
                "ffmpeg", "-y", "-i", str(src_path),
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(dest_path)
            ], capture_output=True, timeout=300)
            if result.returncode != 0:
                return jsonify({"error": f"Failed to re-encode {src}: {result.stderr[-200:]}"}), 500

    # 4. Build concat file
    concat_path = ep_dir / "concat.txt"
    concat_path.write_text(
        "file 'intro-bumper.mp4'\n"
        "file 'seg1.mp4'\n"
        "file 'seg2.mp4'\n"
        "file 'credits-bumper.mp4'\n"
    )

    # 5. Stitch
    output_name = f"AI-Views-and-News-EP{episode_num}.mp4"
    output_path = ep_dir / output_name
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_path), "-c", "copy", str(output_path)
    ], capture_output=True, timeout=120)

    if result.returncode != 0:
        return jsonify({"error": f"Stitch failed: {result.stderr[-200:]}"}), 500

    # 6. Get duration
    dur_result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)
    ], capture_output=True, text=True)
    duration_sec = float(dur_result.stdout.strip()) if dur_result.stdout.strip() else 0
    mins = int(duration_sec // 60)
    secs = int(duration_sec % 60)
    duration_str = f"{mins}:{secs:02d}"

    # 7. Update episode metadata
    meta["final_video"] = output_name
    meta["duration"] = duration_str
    meta["status"] = "complete"
    meta["stitched_at"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, indent=2))

    # 8. Notify Doug
    send_pushover(
        f"Episode {episode_num} stitched! {duration_str} runtime. Ready to watch.",
        title="Show Runner — Episode Complete!"
    )

    return jsonify({
        "success": True,
        "video": output_name,
        "duration": duration_str,
        "path": str(output_path)
    })


@app.route("/api/host-notes/<int:episode_num>")
def get_host_notes(episode_num):
    """Return host notes for an episode."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    notes_path = ep_dir / "host-notes.md"
    if notes_path.exists():
        return notes_path.read_text(), 200, {"Content-Type": "text/plain; charset=utf-8"}
    return jsonify({"error": "No host notes found"}), 404


@app.route("/api/episodes")
def list_episodes():
    """List all episodes."""
    episodes = []
    for d in sorted(SHOW_DIR.glob("ep*")):
        meta_path = d / "episode.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                episodes.append(meta)
            except Exception:
                continue
        else:
            episodes.append({
                "episode": int(d.name.replace("ep", "")),
                "date": "unknown",
                "status": "legacy"
            })
    return jsonify(episodes)


# ─── Doug Bug: Notifications & Queue ─────────────────────────────────────

import urllib.request
import urllib.parse

# Pushover credentials — set these in environment or replace with your keys
PUSHOVER_USER_KEY = ""
PUSHOVER_APP_TOKEN = ""
TWILIO_ACCOUNT_SID = ""
TWILIO_AUTH_TOKEN = ""
TWILIO_PHONE_NUMBER = ""
MANAGER_PASSWORD = ""

# Try loading from env file
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("PUSHOVER_USER_KEY="):
            PUSHOVER_USER_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("PUSHOVER_APP_TOKEN="):
            PUSHOVER_APP_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TWILIO_ACCOUNT_SID="):
            TWILIO_ACCOUNT_SID = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TWILIO_AUTH_TOKEN="):
            TWILIO_AUTH_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TWILIO_PHONE_NUMBER="):
            TWILIO_PHONE_NUMBER = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("MANAGER_PASSWORD="):
            MANAGER_PASSWORD = line.split("=", 1)[1].strip().strip('"').strip("'")

# In-memory notification queue
notification_queue = []

NOTIFY_MESSAGES = {
    "show_ready": "AI Views and News: Episode ready to produce! Open the Show Runner.",
    "stories_picked": "AI Views and News: Stories have been picked. Ready for script generation.",
}


def send_sms(to_number, message):
    """Send an SMS via Twilio."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        return False, "Twilio not configured"
    try:
        import base64
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        data = urllib.parse.urlencode({
            "To": to_number,
            "From": TWILIO_PHONE_NUMBER,
            "Body": message,
        }).encode()
        auth = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req) as resp:
            return resp.status in (200, 201), None
    except Exception as e:
        return False, str(e)


def notify_all_runners(message):
    """Text all registered Render Runners about new jobs."""
    count = 0
    for f in WORKERS_DIR.glob("*.json"):
        try:
            worker = json.loads(f.read_text())
            phone = worker.get("phone")
            if phone:
                send_sms(phone, message)
                count += 1
        except Exception:
            continue
    return count


def send_pushover(message, title="Doug Bug"):
    """Send a Pushover notification to Doug's phone and desktop."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_APP_TOKEN:
        return False, "Pushover credentials not configured"

    try:
        data = urllib.parse.urlencode({
            "token": PUSHOVER_APP_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "title": title,
            "message": message,
            "url": "https://showrunner.dmpgh.com",
            "url_title": "Open Show Runner",
            "sound": "cosmic",
        }).encode()

        req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
        with urllib.request.urlopen(req) as resp:
            return resp.status == 200, None
    except Exception as e:
        return False, str(e)


@app.route("/api/notify", methods=["POST"])
def notify_doug():
    """Send a notification to Doug via Pushover."""
    data = request.json
    notify_type = data.get("type", "note")
    message = data.get("message") or NOTIFY_MESSAGES.get(notify_type, f"Notification: {notify_type}")

    # Add to queue
    notification_queue.append({
        "type": notify_type,
        "message": message if notify_type == "note" else None,
        "time": datetime.now().strftime("%H:%M"),
        "timestamp": datetime.now().isoformat()
    })

    # Send Pushover
    success, error = send_pushover(message, title="AI Views and News")

    if not success and error and "credentials" in error:
        return jsonify({"success": False, "error": "Pushover not configured. Add keys to .env file."})

    return jsonify({"success": success, "error": error})


@app.route("/api/queue")
def get_queue():
    """Return the notification queue."""
    return jsonify(notification_queue[-20:])  # Last 20


@app.route("/api/queue/clear", methods=["POST"])
def clear_queue():
    """Clear the notification queue."""
    notification_queue.clear()
    return jsonify({"success": True})


# ─── Job Board ────────────────────────────────────────────────────────────

JOBS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
WORKERS_DIR = Path(__file__).parent / "workers"
WORKERS_DIR.mkdir(parents=True, exist_ok=True)

JOB_TIMEOUT_SECONDS = 3600  # 1 hour
WORKERS_DIR = Path(__file__).parent / "workers"
WORKERS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/api/workers/register", methods=["POST"])
def api_register_worker():
    """Register a Render Runner with phone number for SMS notifications."""
    data = request.json
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    worker_id = name.lower().replace(" ", "-").replace(".", "")[:20]
    payment_method = data.get("payment_method", "")
    payment_handle = data.get("payment_handle", "")

    worker = {
        "id": worker_id,
        "name": name,
        "phone": phone,
        "payment_method": payment_method,
        "payment_handle": payment_handle,
        "registered": datetime.now().isoformat(),
        "jobs_completed": 0,
        "total_earned": 0.0,
        "total_paid": 0.0,
        "star_rating": 3,
        "practice_heygen": False,
        "practice_pictory": False,
        "qualified": False,
    }
    path = WORKERS_DIR / f"{worker_id}.json"
    if not path.exists():
        path.write_text(json.dumps(worker, indent=2))
        send_pushover(f"New Render Runner: {name} ({phone})", title="Render Monkey")
    return jsonify({"success": True, "worker": worker})


@app.route("/api/workers/<worker_id>/practice", methods=["POST"])
def api_complete_practice(worker_id):
    """Mark a practice render as complete for a worker."""
    data = request.json
    practice_type = data.get("type")  # "heygen" or "pictory"
    if practice_type not in ("heygen", "pictory"):
        return jsonify({"error": "type must be heygen or pictory"}), 400

    path = WORKERS_DIR / f"{worker_id}.json"
    if not path.exists():
        return jsonify({"error": "Worker not found"}), 404

    worker = json.loads(path.read_text())
    worker[f"practice_{practice_type}"] = True

    # Qualified when both practices are done
    if worker.get("practice_heygen") and worker.get("practice_pictory"):
        worker["qualified"] = True

    path.write_text(json.dumps(worker, indent=2))

    return jsonify({
        "success": True,
        "practice_heygen": worker["practice_heygen"],
        "practice_pictory": worker["practice_pictory"],
        "qualified": worker["qualified"]
    })


@app.route("/api/workers/<worker_id>/practice-upload", methods=["POST"])
def api_upload_practice(worker_id):
    """Upload a practice render as proof of completion."""
    path = WORKERS_DIR / f"{worker_id}.json"
    if not path.exists():
        return jsonify({"error": "Worker not found"}), 404

    practice_type = request.form.get("type")
    if practice_type not in ("heygen", "pictory"):
        return jsonify({"error": "type must be heygen or pictory"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".mp4"):
        return jsonify({"error": "Only MP4 files accepted"}), 400

    # Save practice render
    practice_dir = WORKERS_DIR / worker_id
    practice_dir.mkdir(exist_ok=True)
    save_path = practice_dir / f"practice-{practice_type}.mp4"
    f.save(str(save_path))

    # Mark practice complete
    worker = json.loads(path.read_text())
    worker[f"practice_{practice_type}"] = True
    if worker.get("practice_heygen") and worker.get("practice_pictory"):
        worker["qualified"] = True
    path.write_text(json.dumps(worker, indent=2))

    send_pushover(
        f"Render Runner '{worker['name']}' completed {practice_type} practice (uploaded proof).",
        title="Render Monkey — Practice Complete"
    )

    return jsonify({
        "success": True,
        "practice_heygen": worker["practice_heygen"],
        "practice_pictory": worker["practice_pictory"],
        "qualified": worker["qualified"]
    })


@app.route("/api/workers/<worker_id>/rate", methods=["POST"])
def api_rate_worker(worker_id):
    """Set a worker's star rating (1-5). Higher = priority job notifications."""
    data = request.json
    rating = data.get("rating", 3)
    rating = max(1, min(5, int(rating)))

    path = WORKERS_DIR / f"{worker_id}.json"
    if not path.exists():
        return jsonify({"error": "Worker not found"}), 404

    worker = json.loads(path.read_text())
    worker["star_rating"] = rating
    path.write_text(json.dumps(worker, indent=2))
    return jsonify({"success": True, "rating": rating})


@app.route("/api/workers/<worker_id>/earnings")
def api_worker_earnings(worker_id):
    """Get a worker's earnings and job history."""
    path = WORKERS_DIR / f"{worker_id}.json"
    if not path.exists():
        return jsonify({"error": "Worker not found"}), 404

    worker = json.loads(path.read_text())

    # Find all completed jobs by this worker
    history = []
    total = 0.0
    for f in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(f.read_text())
            if job.get("claimed_by") == worker.get("name") and job.get("status") == "approved":
                history.append({
                    "job": job["title"],
                    "pay": job["pay"],
                    "completed": job.get("completed_at", ""),
                    "episode": job.get("episode"),
                })
                total += job["pay"]
        except Exception:
            continue

    return jsonify({
        "name": worker["name"],
        "star_rating": worker.get("star_rating", 3),
        "qualified": worker.get("qualified", False),
        "total_earned": total,
        "total_paid": worker.get("total_paid", 0.0),
        "balance": total - worker.get("total_paid", 0.0),
        "jobs_completed": len(history),
        "history": sorted(history, key=lambda x: x.get("completed", ""), reverse=True),
    })


@app.route("/api/workers")
def api_list_workers():
    """List all registered workers."""
    workers = []
    for f in WORKERS_DIR.glob("*.json"):
        try:
            workers.append(json.loads(f.read_text()))
        except Exception:
            continue
    return jsonify(workers)


def load_jobs():
    """Load all jobs from disk."""
    jobs = []
    for f in sorted(JOBS_DIR.glob("*.json")):
        try:
            jobs.append(json.loads(f.read_text()))
        except Exception:
            continue
    return jobs


def save_job(job):
    """Save a job to disk."""
    path = JOBS_DIR / f"{job['id']}.json"
    path.write_text(json.dumps(job, indent=2, default=str))


def create_jobs_for_episode(episode_num):
    """Create 2 jobs (HeyGen + Pictory) for an episode."""
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    meta_path = ep_dir / "episode.json"
    if not meta_path.exists():
        return []

    meta = json.loads(meta_path.read_text())
    stories = meta.get("stories", [])
    job_id_base = f"ep{episode_num}"
    created = datetime.now().isoformat()

    # Read scripts
    opening = (ep_dir / "heygen-opening.txt").read_text() if (ep_dir / "heygen-opening.txt").exists() else ""
    closing = (ep_dir / "heygen-closing.txt").read_text() if (ep_dir / "heygen-closing.txt").exists() else ""
    story_scripts = []
    for i in range(1, 4):
        p = ep_dir / f"pictory-story{i}.txt"
        story_scripts.append(p.read_text() if p.exists() else "")

    story_titles = [s.get("title", f"Story {i+1}") for i, s in enumerate(stories)]

    jobs = []

    # Job 1: HeyGen (opening + closing)
    heygen_job = {
        "id": f"{job_id_base}-heygen",
        "episode": episode_num,
        "type": "heygen",
        "title": f"EP{episode_num} — HeyGen (Opening + Closing)",
        "description": "Paste both scripts into HeyGen as one video (opening + closing). Render and upload the single MP4.",
        "pay": 1.00,
        "scripts": [
            {"label": "Opening Script", "text": opening},
            {"label": "Closing Script", "text": closing},
        ],
        "expected_files": 1,
        "uploaded_files": [],
        "status": "available",  # available, claimed, complete, expired
        "claimed_by": None,
        "claimed_at": None,
        "completed_at": None,
        "created": created,
    }
    save_job(heygen_job)
    jobs.append(heygen_job)

    # Job 2: Pictory (3 stories)
    pictory_job = {
        "id": f"{job_id_base}-pictory",
        "episode": episode_num,
        "type": "pictory",
        "title": f"EP{episode_num} — Pictory (3 News Segments)",
        "description": "Paste all 3 scripts into Pictory as one video (3 news stories). Render and upload the single MP4.",
        "pay": 1.00,
        "scripts": [
            {"label": f"Story 1: {story_titles[0]}" if story_titles else "Story 1", "text": story_scripts[0]},
            {"label": f"Story 2: {story_titles[1]}" if len(story_titles) > 1 else "Story 2", "text": story_scripts[1]},
            {"label": f"Story 3: {story_titles[2]}" if len(story_titles) > 2 else "Story 3", "text": story_scripts[2]},
        ],
        "expected_files": 1,
        "uploaded_files": [],
        "status": "available",
        "claimed_by": None,
        "claimed_at": None,
        "completed_at": None,
        "created": created,
    }
    save_job(pictory_job)
    jobs.append(pictory_job)

    return jobs


def check_expired_jobs():
    """Release any claimed jobs that have timed out."""
    now = datetime.now()
    for job in load_jobs():
        if job["status"] == "claimed" and job.get("claimed_at"):
            claimed = datetime.fromisoformat(job["claimed_at"])
            if (now - claimed).total_seconds() > JOB_TIMEOUT_SECONDS:
                job["status"] = "available"
                job["claimed_by"] = None
                job["claimed_at"] = None
                job["uploaded_files"] = []
                save_job(job)


SELLERS_DIR = Path(__file__).parent / "sellers"
SELLERS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/seller")
def seller_page():
    """Serve the seller dashboard."""
    return send_from_directory(str(STATIC_DIR), "seller.html")


@app.route("/api/sellers/register", methods=["POST"])
def api_register_seller():
    """Register a new seller."""
    data = request.json
    name = data.get("name", "")
    email = data.get("email", "")
    code = data.get("code", "")
    if not name or not code:
        return jsonify({"error": "Name and code required"}), 400

    seller = {
        "name": name,
        "email": email,
        "phone": data.get("phone", ""),
        "code": code,
        "payment_method": data.get("payment_method", ""),
        "payment_handle": data.get("payment_handle", ""),
        "registered": datetime.now().isoformat(),
        "referrals": [],
        "total_earned": 0.0,
        "total_paid": 0.0,
    }
    path = SELLERS_DIR / f"{code}.json"
    if not path.exists():
        path.write_text(json.dumps(seller, indent=2))
        send_pushover(
            f"New seller registered: {name} ({email}). Code: {code}",
            title="Render Monkey — New Seller"
        )
    return jsonify({"success": True, "code": code})


@app.route("/api/sellers/<code>/stats")
def api_seller_stats(code):
    """Get stats for a seller."""
    path = SELLERS_DIR / f"{code}.json"
    if not path.exists():
        return jsonify({"earned": 0, "referrals": 0, "pending": 0, "history": []})

    seller = json.loads(path.read_text())
    approved = [r for r in seller.get("referrals", []) if r.get("status") == "approved"]
    pending = [r for r in seller.get("referrals", []) if r.get("status") == "pending"]

    return jsonify({
        "earned": sum(r.get("amount", 2.50) for r in approved),
        "referrals": len(seller.get("referrals", [])),
        "pending": sum(r.get("amount", 2.50) for r in pending),
        "history": seller.get("referrals", []),
    })


@app.route("/api/referral-click", methods=["POST"])
def api_referral_click():
    """Track a referral link click or action."""
    data = request.json
    ref_code = data.get("ref", "")
    action = data.get("action", "unknown")

    if not ref_code:
        return jsonify({"success": False}), 400

    # Find seller by code
    seller_path = SELLERS_DIR / f"{ref_code}.json"
    if seller_path.exists():
        seller = json.loads(seller_path.read_text())
        if "clicks" not in seller:
            seller["clicks"] = []
        seller["clicks"].append({
            "action": action,
            "time": datetime.now().isoformat()
        })
        seller_path.write_text(json.dumps(seller, indent=2))

        # Notify Doug on actual request (not just page visit)
        if action == "request_shows":
            send_pushover(
                f"New client request via {seller['name']}'s referral link!",
                title="Render Monkey — Referral Sale!"
            )

    return jsonify({"success": True})


@app.route("/api/sellers")
def api_list_sellers():
    """List all sellers (manager view)."""
    sellers = []
    for f in SELLERS_DIR.glob("*.json"):
        try:
            sellers.append(json.loads(f.read_text()))
        except Exception:
            continue
    return jsonify(sellers)


CLIENTS_DIR = Path(__file__).parent / "clients"
CLIENTS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/api/sellers/<code>/credit", methods=["POST"])
def api_credit_seller(code):
    """Credit a seller for a referral sale."""
    data = request.json
    client = data.get("client", "Unknown")
    amount = data.get("amount", 2.50)

    path = SELLERS_DIR / f"{code}.json"
    if not path.exists():
        return jsonify({"error": "Seller not found"}), 404

    seller = json.loads(path.read_text())
    seller["referrals"].append({
        "client": client,
        "amount": amount,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "pending",
    })
    path.write_text(json.dumps(seller, indent=2))

    # Save client → seller mapping for recurring commissions
    client_id = client.lower().replace(" ", "-")[:20]
    client_path = CLIENTS_DIR / f"{client_id}.json"
    if not client_path.exists():
        client_path.write_text(json.dumps({
            "client": client,
            "seller_code": code,
            "first_sale": datetime.now().isoformat(),
        }, indent=2))

    return jsonify({"success": True})


@app.route("/api/record-sale", methods=["POST"])
def api_record_sale():
    """Record a sale and auto-credit the seller who originally referred this client."""
    if not check_manager_auth():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    client = data.get("client", "")
    script_price = data.get("script_price", 5.00)
    # Recurring commission = 11.3% of script price
    amount = round(script_price * 0.113, 2)

    if not client:
        return jsonify({"error": "Client name required"}), 400

    # Look up which seller referred this client
    client_id = client.lower().replace(" ", "-")[:20]
    client_path = CLIENTS_DIR / f"{client_id}.json"

    if client_path.exists():
        client_data = json.loads(client_path.read_text())
        seller_code = client_data.get("seller_code")

        if seller_code:
            seller_path = SELLERS_DIR / f"{seller_code}.json"
            if seller_path.exists():
                seller = json.loads(seller_path.read_text())
                seller["referrals"].append({
                    "client": client,
                    "amount": amount,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "status": "pending",
                    "recurring": True,
                })
                seller_path.write_text(json.dumps(seller, indent=2))
                return jsonify({"success": True, "seller": seller["name"], "amount": amount, "recurring": True})

    return jsonify({"success": True, "seller": None, "note": "No seller on record for this client"})


def check_manager_auth():
    """Check if the manager password is provided via query param or header."""
    pw = request.args.get("pw") or request.headers.get("X-Manager-Password") or ""
    return pw == MANAGER_PASSWORD


@app.route("/manager")
def manager_page():
    """Serve the manager panel (Doug only)."""
    if not check_manager_auth():
        # Show a simple password prompt page
        return """<!DOCTYPE html><html><head><title>Manager Login</title>
        <style>body{background:#0a0a14;color:#e0e0e0;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;}
        .box{background:#111122;padding:32px;border-radius:8px;text-align:center;border:1px solid #1e1e30;}
        input{padding:12px;background:#0a0a14;border:1px solid #2a2a3e;border-radius:6px;color:#e0e0e0;font-size:16px;margin:12px 0;width:250px;}
        button{padding:12px 32px;background:#cc2222;color:white;border:none;border-radius:6px;font-size:14px;font-weight:700;cursor:pointer;}
        </style></head><body><div class="box"><h2 style="color:#cc2222;">Manager Login</h2>
        <input type="password" id="pw" placeholder="Password" onkeydown="if(event.key==='Enter')go()"/>
        <br><button onclick="go()">Enter</button>
        <script>function go(){window.location.href='/manager?pw='+document.getElementById('pw').value;}</script>
        </div></body></html>"""
    return send_from_directory(str(STATIC_DIR), "manager.html")


@app.route("/api/jobs/<job_id>/preview")
def api_preview_job(job_id):
    """Preview an uploaded render."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404
    job = json.loads(path.read_text())
    if not job.get("uploaded_files"):
        return jsonify({"error": "No files uploaded"}), 404
    filename = job["uploaded_files"][0]["filename"]
    ep_dir = SHOW_DIR / f"ep{job['episode']}"
    return send_from_directory(str(ep_dir), filename, mimetype="video/mp4")


@app.route("/jobs")
def jobs_page():
    """Serve the job board page."""
    return send_from_directory(str(STATIC_DIR), "jobs.html")


@app.route("/api/jobs")
def api_list_jobs():
    """List all jobs, checking for expired claims."""
    check_expired_jobs()
    return jsonify(load_jobs())


@app.route("/api/jobs/create", methods=["POST"])
def api_create_jobs():
    """Create jobs for an episode."""
    data = request.json
    episode_num = data.get("episode")
    if not episode_num:
        return jsonify({"error": "episode required"}), 400
    jobs = create_jobs_for_episode(episode_num)
    if not jobs:
        return jsonify({"error": "Episode not found or no scripts"}), 404

    # Notify Doug
    send_pushover(
        f"2 new jobs posted for Episode {episode_num}. HeyGen + Pictory renders needed.",
        title="Show Runner — Jobs Posted"
    )

    # Text all Render Runners in priority order (highest star rating first)
    all_workers = []
    for f in WORKERS_DIR.glob("*.json"):
        try:
            all_workers.append(json.loads(f.read_text()))
        except Exception:
            continue

    # Sort by star rating (highest first)
    all_workers.sort(key=lambda w: w.get("star_rating", 3), reverse=True)

    # Batch 1: 5-star and 4-star runners get 15 min head start
    top_runners = [w for w in all_workers if w.get("star_rating", 3) >= 4 and w.get("phone")]
    other_runners = [w for w in all_workers if w.get("star_rating", 3) < 4 and w.get("phone")]

    for w in top_runners:
        send_sms(w["phone"],
            f"Render Monkey: New jobs for Episode {episode_num}! "
            f"You get 15 min priority. Claim now: showrunner.dmpgh.com/jobs")

    # Schedule batch 2 notification (other runners get texted after 15 min delay)
    # For now, text them immediately with a note
    if other_runners:
        import threading
        def notify_batch2():
            import time
            time.sleep(900)  # 15 minutes
            for w in other_runners:
                send_sms(w["phone"],
                    f"Render Monkey: Jobs available for Episode {episode_num}! "
                    f"Claim now: showrunner.dmpgh.com/jobs")
        threading.Thread(target=notify_batch2, daemon=True).start()

    return jsonify({"success": True, "jobs": jobs})


@app.route("/api/jobs/<job_id>/claim", methods=["POST"])
def api_claim_job(job_id):
    """Claim a job. Worker has 1 hour to complete."""
    check_expired_jobs()
    data = request.json or {}
    worker_name = data.get("name", "Anonymous")

    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404

    job = json.loads(path.read_text())
    if job["status"] != "available":
        return jsonify({"error": f"Job is {job['status']}, not available"}), 400

    # Check if worker is qualified (completed both practice renders)
    worker_id = worker_name.lower().replace(" ", "-").replace(".", "")[:20]
    worker_path = WORKERS_DIR / f"{worker_id}.json"
    if worker_path.exists():
        worker = json.loads(worker_path.read_text())
        if not worker.get("qualified"):
            missing = []
            if not worker.get("practice_heygen"):
                missing.append("HeyGen practice")
            if not worker.get("practice_pictory"):
                missing.append("Pictory practice")
            return jsonify({"error": f"Complete {' and '.join(missing)} first"}), 400
    else:
        return jsonify({"error": "Register first before claiming jobs"}), 400

    job["status"] = "claimed"
    job["claimed_by"] = worker_name
    job["claimed_at"] = datetime.now().isoformat()
    save_job(job)

    return jsonify({"success": True, "job": job, "timeout_minutes": JOB_TIMEOUT_SECONDS // 60})


@app.route("/api/jobs/<job_id>/release", methods=["POST"])
def api_release_job(job_id):
    """Release a claimed job back to the board."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404

    job = json.loads(path.read_text())
    job["status"] = "available"
    job["claimed_by"] = None
    job["claimed_at"] = None
    job["uploaded_files"] = []
    save_job(job)

    return jsonify({"success": True})


@app.route("/api/jobs/<job_id>/upload", methods=["POST"])
def api_upload_render(job_id):
    """Upload a rendered MP4 for a job."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404

    job = json.loads(path.read_text())
    if job["status"] != "claimed":
        return jsonify({"error": "Job not claimed"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".mp4"):
        return jsonify({"error": "Only MP4 files accepted"}), 400

    # Save to episode directory
    ep_dir = SHOW_DIR / f"ep{job['episode']}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    # Determine filename — 1 file per job
    if job["type"] == "heygen":
        save_name = "heygen-combined.mp4"
    else:
        save_name = "pictory-combined.mp4"

    save_path = ep_dir / save_name
    f.save(str(save_path))

    job["uploaded_files"].append({"filename": save_name, "uploaded": datetime.now().isoformat()})

    # Mark as pending review (Doug approves before payment)
    if len(job["uploaded_files"]) >= job["expected_files"]:
        job["status"] = "pending_review"
        job["completed_at"] = datetime.now().isoformat()

        # Check if both jobs for this episode are pending/complete
        all_jobs = [j for j in load_jobs() if j["episode"] == job["episode"]]
        other_done = all(j["status"] in ("pending_review", "approved") for j in all_jobs if j["id"] != job["id"])
        if other_done:
            send_pushover(
                f"Both renders uploaded for Episode {job['episode']}! Review and approve.",
                title="Render Monkey — Review Needed"
            )

    save_job(job)

    return jsonify({
        "success": True,
        "uploaded": len(job["uploaded_files"]),
        "expected": job["expected_files"],
        "complete": job["status"] == "complete"
    })


@app.route("/api/jobs/<job_id>/approve", methods=["POST"])
def api_approve_job(job_id):
    """Doug approves a completed job — releases payment."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404

    job = json.loads(path.read_text())
    if job["status"] != "pending_review":
        return jsonify({"error": f"Job is {job['status']}, not pending review"}), 400

    if not check_manager_auth():
        return jsonify({"error": "Unauthorized"}), 401

    job["status"] = "approved"
    job["approved"] = True
    save_job(job)

    return jsonify({"success": True, "job": job})


@app.route("/api/jobs/<job_id>/reject", methods=["POST"])
def api_reject_job(job_id):
    """Doug rejects a job — goes back to available."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return jsonify({"error": "Job not found"}), 404

    job = json.loads(path.read_text())
    data = request.json or {}
    reason = data.get("reason", "")

    job["status"] = "available"
    job["claimed_by"] = None
    job["claimed_at"] = None
    job["completed_at"] = None
    job["uploaded_files"] = []
    job["approved"] = False
    if reason:
        job["reject_reason"] = reason
    save_job(job)

    return jsonify({"success": True})


# ─── Host Notes ───────────────────────────────────────────────────────────

def _generate_qa_topics(title, script_text):
    """Generate 3-4 Q&A discussion questions for Drake & Carter's live session."""
    prompt = f"""Based on this news story, generate exactly 4 discussion questions for a live Q&A session.

STORY: {title}
SCRIPT: {script_text[:500]}

RULES:
- Questions should spark discussion, not have simple yes/no answers
- Mix practical ("How does this affect you?") with bigger picture ("Where is this heading?")
- Keep each question to one sentence
- Make them conversational, not academic
- These are for a Skool community audience — smart but not technical experts

Return ONLY the 4 questions, one per line, no numbering, no bullets, no extra text."""

    try:
        result = _run_ollama(prompt)
        questions = [q.strip().lstrip('- ').lstrip('•').lstrip('1234567890.)')
                     for q in result.strip().split('\n') if len(q.strip()) > 15]
        return questions[:4]
    except Exception:
        return None


def generate_host_notes(episode_num, date, stories, scripts):
    """Generate a host notes rundown sheet for the episode."""
    from datetime import datetime as dt
    try:
        d = dt.strptime(date, "%Y-%m-%d")
        date_display = d.strftime("%A, %B %d, %Y")
    except Exception:
        date_display = date

    # Word counts and estimated durations
    segments = [
        ("Intro Bumper", "", 5),
        ("HeyGen Opening", scripts.get("opening", ""), None),
        ("Pictory Story 1", scripts.get("story1", ""), None),
        ("Pictory Story 2", scripts.get("story2", ""), None),
        ("Pictory Story 3", scripts.get("story3", ""), None),
        ("HeyGen Closing", scripts.get("closing", ""), None),
        ("Credits Bumper", "", 12),
    ]

    lines = []
    lines.append(f"# AI Views and News — Episode {episode_num}")
    lines.append(f"## Host Notes")
    lines.append(f"**Date:** {date_display}")
    lines.append(f"**Host:** Doug Morse")
    lines.append(f"**Format:** 2 HeyGen avatar + 3 Pictory B-roll + bumpers")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Rundown table
    lines.append("## Rundown")
    lines.append("")
    lines.append("| # | Segment | Type | Est. Duration |")
    lines.append("|---|---------|------|---------------|")

    total_seconds = 0
    for i, (label, script, fixed_dur) in enumerate(segments):
        if fixed_dur:
            dur = fixed_dur
        else:
            words = len(script.split()) if script else 0
            dur = int(words / 2.5)  # ~150 wpm = 2.5 wps
        total_seconds += dur
        m, s = divmod(dur, 60)
        seg_type = "Bumper" if "Bumper" in label else ("HeyGen" if "HeyGen" in label else "Pictory")
        lines.append(f"| {i} | {label} | {seg_type} | {m}:{s:02d} |")

    tm, ts = divmod(total_seconds, 60)
    lines.append(f"| | **TOTAL** | | **{tm}:{ts:02d}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Story briefs
    lines.append("## Story Briefs")
    lines.append("")
    for i, story in enumerate(stories):
        title = story.get("title", f"Story {i+1}")
        source = story.get("source", "")
        link = story.get("link", "")
        lines.append(f"### Story {i+1}: {title}")
        lines.append(f"**Source:** {source}")
        if link:
            lines.append(f"**Link:** {link}")

        # Pull key points from the script
        script_key = f"story{i+1}"
        script_text = scripts.get(script_key, "")
        if script_text:
            # First 2-3 sentences as talking points
            sentences = [s.strip() for s in script_text.replace('\n\n', '. ').split('. ') if len(s.strip()) > 20][:4]
            lines.append("**Key points:**")
            for sent in sentences:
                clean = sent.strip().rstrip('.')
                lines.append(f"- {clean}")

            # Generate Q&A suggestions for Drake & Carter's session
            lines.append("")
            lines.append("**Suggested Q&A topics for Drake & Carter:**")
            qa = _generate_qa_topics(title, script_text)
            if qa:
                for q in qa:
                    lines.append(f"- {q}")
            else:
                # Fallback if Ollama fails
                lines.append(f"- What does this mean for everyday users?")
                lines.append(f"- Who benefits most from this development?")
                lines.append(f"- What should our community be doing about this?")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Production checklist
    lines.append("## Production Checklist")
    lines.append("")
    lines.append("- [ ] News collected and stories selected")
    lines.append("- [ ] All 5 scripts generated and reviewed")
    lines.append("- [ ] HeyGen opening rendered")
    lines.append("- [ ] HeyGen closing rendered")
    lines.append("- [ ] Pictory story 1 rendered")
    lines.append("- [ ] Pictory story 2 rendered")
    lines.append("- [ ] Pictory story 3 rendered")
    lines.append("- [ ] All segments stitched (30fps, 1080p)")
    lines.append("- [ ] Crypt Notes newsletter generated")
    lines.append("- [ ] Final review and publish")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by AI Views and News Show Runner — {date}*")

    return "\n".join(lines)


# ─── Bumper generation ────────────────────────────────────────────────────

OVERLAYS_DIR = PROJECT_ROOT / "overlays"
MUSIC_DIR = PROJECT_ROOT / "music"


def generate_intro_bumper(ep_dir: Path, episode_num: int, date: str):
    """Generate branded intro bumper with episode number and date."""
    output = ep_dir / "intro-bumper.mp4"
    bg = OVERLAYS_DIR / "bumper_frame.png"
    sting = MUSIC_DIR / "news_sting.wav"

    bg_input = ["-loop", "1", "-i", str(bg)] if bg.exists() else \
        ["-f", "lavfi", "-i", "color=c=0x0a0a14:s=1920x1080:d=5"]
    audio_input = ["-i", str(sting)] if sting.exists() else []
    audio_flags = ["-af", "afade=t=in:st=0:d=0.5,afade=t=out:st=4:d=1,apad"] if sting.exists() else ["-an"]

    # Format date nicely
    from datetime import datetime as dt
    try:
        d = dt.strptime(date, "%Y-%m-%d")
        date_display = d.strftime("%B %d, %Y")
    except Exception:
        date_display = date

    cmd = ["ffmpeg", "-y"] + bg_input + audio_input + [
        "-t", "5",
        "-vf", (
            f"scale=1920:1080,fps=30,"
            f"drawtext=text='AI VIEWS AND NEWS':fontsize=80:fontcolor=white:font=Helvetica Neue:"
            f"x=(w-text_w)/2:y=(h/2)-80:borderw=3:bordercolor=black,"
            f"drawtext=text='Episode {episode_num}':fontsize=40:fontcolor=0xaaaaaa:font=Helvetica Neue:"
            f"x=(w-text_w)/2:y=(h/2)+20:borderw=2:bordercolor=black,"
            f"drawtext=text='{date_display}':fontsize=30:fontcolor=0x888888:font=Helvetica Neue:"
            f"x=(w-text_w)/2:y=(h/2)+75:borderw=2:bordercolor=black,"
            f"drawtext=text='dmpgh.com':fontsize=24:fontcolor=0x0088ff:font=Helvetica Neue:"
            f"x=(w-text_w)/2:y=h-80:borderw=1:bordercolor=black,"
            f"fade=t=in:st=0:d=1,fade=t=out:st=4:d=1"
        ),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output)
    ] + audio_flags

    subprocess.run(cmd, capture_output=True, timeout=30)
    return output


def generate_credits_bumper(ep_dir: Path, episode_num: int, date: str):
    """Generate scrolling credits bumper with episode number and date."""
    output = ep_dir / "credits-bumper.mp4"
    bg = OVERLAYS_DIR / "bumper_frame.png"
    sting = MUSIC_DIR / "news_sting.wav"

    bg_input = ["-loop", "1", "-i", str(bg)] if bg.exists() else \
        ["-f", "lavfi", "-i", "color=c=0x0a0a14:s=1920x1080:d=12"]
    audio_input = ["-i", str(sting)] if sting.exists() else []
    audio_flags = ["-af", "afade=t=in:st=0:d=0.5,afade=t=out:st=10:d=2,apad"] if sting.exists() else ["-an"]

    from datetime import datetime as dt
    try:
        d = dt.strptime(date, "%Y-%m-%d")
        date_display = d.strftime("%B %d, %Y")
    except Exception:
        date_display = date

    # Scroll speed: credits travel (h + 800) pixels over 12 seconds
    s = "h-((h+800)*t/12)"

    vf = (
        f"scale=1920:1080,fps=30,"
        f"drawtext=text='AI VIEWS AND NEWS':fontsize=60:fontcolor=white:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+700:borderw=2:bordercolor=black,"
        f"drawtext=text='Episode {episode_num}  ·  {date_display}':fontsize=30:fontcolor=0x888888:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+770:borderw=1:bordercolor=black,"
        f"drawtext=text='─────────────────':fontsize=30:fontcolor=0x333333:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+830:borderw=1:bordercolor=black,"
        f"drawtext=text='Host':fontsize=24:fontcolor=0x888888:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+880:borderw=1:bordercolor=black,"
        f"drawtext=text='Doug Morse':fontsize=36:fontcolor=white:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+920:borderw=2:bordercolor=black,"
        f"drawtext=text='Produced with AI':fontsize=24:fontcolor=0x888888:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+990:borderw=1:bordercolor=black,"
        f"drawtext=text='Claude Code  ·  HeyGen  ·  Pictory  ·  Ollama':fontsize=30:fontcolor=0xaaaaaa:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1030:borderw=2:bordercolor=black,"
        f"drawtext=text='News Sources':fontsize=24:fontcolor=0x888888:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1100:borderw=1:bordercolor=black,"
        f"drawtext=text='The Verge  ·  TechCrunch  ·  Ars Technica  ·  MIT Tech Review':fontsize=26:fontcolor=0xaaaaaa:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1140:borderw=2:bordercolor=black,"
        f"drawtext=text='Music':fontsize=24:fontcolor=0x888888:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1210:borderw=1:bordercolor=black,"
        f"drawtext=text='Suno AI':fontsize=30:fontcolor=0xaaaaaa:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1250:borderw=2:bordercolor=black,"
        f"drawtext=text='─────────────────':fontsize=30:fontcolor=0x333333:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1320:borderw=1:bordercolor=black,"
        f"drawtext=text='dmpgh.com':fontsize=36:fontcolor=0x0088ff:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1380:borderw=2:bordercolor=black,"
        f"drawtext=text='© 2026 DMPGH':fontsize=20:fontcolor=0x555555:font=Helvetica Neue:"
        f"x=(w-text_w)/2:y={s}+1430:borderw=1:bordercolor=black,"
        f"fade=t=in:st=0:d=1,fade=t=out:st=10.5:d=1.5"
    )

    cmd = ["ffmpeg", "-y"] + bg_input + audio_input + [
        "-t", "12",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output)
    ] + audio_flags

    subprocess.run(cmd, capture_output=True, timeout=30)
    return output


@app.route("/api/generate-bumpers", methods=["POST"])
def api_generate_bumpers():
    """Generate intro and/or credits bumpers for an episode."""
    data = request.json
    episode_num = data.get("episode", 1)
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    ep_dir = SHOW_DIR / f"ep{episode_num}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    if data.get("intro", True):
        generate_intro_bumper(ep_dir, episode_num, date)
        results["intro"] = str(ep_dir / "intro-bumper.mp4")
    if data.get("credits", True):
        generate_credits_bumper(ep_dir, episode_num, date)
        results["credits"] = str(ep_dir / "credits-bumper.mp4")

    return jsonify({"success": True, "files": results})


if __name__ == "__main__":
    print(f"\n  AI Views and News — Show Runner")
    print(f"  http://localhost:5555\n")
    app.run(host="0.0.0.0", port=5555, debug=True)
