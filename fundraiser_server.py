#!/usr/bin/env python3
"""
Self-Service Fundraiser Video Generator
Runs on port 8091. Takes form input, writes a script via Ollama, runs the pipeline.

Start: python3.12 fundraiser_server.py
"""
import json, os, re, subprocess, sys, threading, time, urllib.request, urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file

PROJECT_ROOT = Path(__file__).parent
FUNDRAISER_DIR = PROJECT_ROOT / "fundraisers"
MUSIC_DIR = PROJECT_ROOT / "music"
BRAND_DIR = PROJECT_ROOT / "brand_assets"
SCRIPTS_DIR = PROJECT_ROOT / "scripts_fundraiser"
STATIC_DIR = PROJECT_ROOT / "fundraiser_web"
OUTPUT_DIR = Path.home() / "Documents" / "Fundraiser Videos"

SCRIPTS_DIR.mkdir(exist_ok=True)
FUNDRAISER_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
PUSHOVER_ENV = Path.home() / ".env.pushover"
GENERATOR = str(PROJECT_ROOT / "fundraiser_generator.py")

# Music style → (bed_file, final_music_file)
MUSIC_STYLES = {
    "emotional-piano": {
        "label": "Emotional Piano",
        "bed":   str(MUSIC_DIR / "fundraiser" / "emotional-piano.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "dramatic": {
        "label": "Dramatic",
        "bed":   str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "uplifting": {
        "label": "Uplifting",
        "bed":   str(MUSIC_DIR / "upbeat.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "classical-love": {
        "label": "Classical / Love",
        "bed":   str(MUSIC_DIR / "fundraiser" / "classical-love.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "cinematic-dramatic": {
        "label": "Cinematic Dramatic",
        "bed":   str(MUSIC_DIR / "fundraiser" / "cinematic-dramatic.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "cinematic-dramatic.mp3"),
    },
    "epic-violin": {
        "label": "Epic Violin",
        "bed":   str(MUSIC_DIR / "fundraiser" / "epic-violin.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "epic-violin.mp3"),
    },
    "acoustic-guitar": {
        "label": "Acoustic Guitar",
        "bed":   str(MUSIC_DIR / "fundraiser" / "acoustic-guitar.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "somber-emotional": {
        "label": "Somber / Emotional",
        "bed":   str(MUSIC_DIR / "fundraiser" / "somber-emotional.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "tender-hopeful": {
        "label": "Tender / Hopeful",
        "bed":   str(MUSIC_DIR / "fundraiser" / "tender-hopeful.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "love-cinematic": {
        "label": "Love / Cinematic",
        "bed":   str(MUSIC_DIR / "fundraiser" / "love-cinematic.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "love-cinematic.mp3"),
    },
    "banjo-americana": {
        "label": "Banjo / Americana",
        "bed":   str(MUSIC_DIR / "fundraiser" / "banjo-americana.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-violin-final.mp3"),
    },
    "dramatic-piano-violin": {
        "label": "Dramatic Piano + Violin",
        "bed":   str(MUSIC_DIR / "fundraiser" / "dramatic-piano-violin.mp3"),
        "final": str(MUSIC_DIR / "fundraiser" / "dramatic-piano-violin.mp3"),
    },
}

# Voice gender → OpenAI TTS voice name
VOICES = {
    "female": "nova",
    "male":   "onyx",
}

# Jobs in-memory: job_id → status dict
jobs = {}

app = Flask(__name__, static_folder=str(STATIC_DIR))


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_env(path):
    env = {}
    if not Path(path).exists():
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def pushover(title, msg):
    try:
        env = load_env(PUSHOVER_ENV)
        data = urllib.parse.urlencode({
            "token": env["PUSHOVER_APP_TOKEN"],
            "user":  env["PUSHOVER_USER_KEY"],
            "title": title, "message": msg[:1024],
        }).encode()
        urllib.request.urlopen(
            urllib.request.Request("https://api.pushover.net/1/messages.json", data=data),
            timeout=10,
        ).read()
    except Exception as e:
        print(f"Pushover error: {e}")

def word_count_for_length(length_s):
    """Target word count for Ollama script given desired video length in seconds.
    Rule of thumb: ~2.5 words/second for a natural narrator pace."""
    return int(length_s * 2.5)

def write_script_via_ollama(org, cause, url, length_s, ask_amount="", frequency="one-time"):
    """Ask Ollama to write a 5-scene fundraiser script JSON."""
    words = word_count_for_length(length_s)
    scene_words = words // 5  # rough per-scene budget

    ask_line = ""
    if ask_amount:
        freq_label = "per month" if frequency == "monthly" else "one-time"
        ask_line = f"Donation ask: {ask_amount} {freq_label} — use this specific amount in the CTA scene."

    prompt = f"""You are a professional fundraiser video scriptwriter.
Write a 5-scene direct-response fundraiser video script for: {org}
Cause: {cause}
Donate/CTA URL: {url}
{ask_line}
Target video length: {length_s} seconds (~{words} total words, ~{scene_words} words per scene)

OUTPUT ONLY VALID JSON. No markdown, no explanation, no code fences. Just the JSON object.

CRITICAL: scene1_hook through scene5_ask must be PLAIN STRINGS — spoken narration only.
Do NOT use nested objects, dicts, or include stage directions like "narration:" or "b-roll:".
Just the words the narrator will say out loud.

The JSON must have exactly these keys:
- scene1_hook: string — opening hook spoken narration (grab attention in the first 2 seconds)
- scene2_problem: string — problem narration (stats or vivid reality)
- scene3_stakes: string — emotional stakes narration (what's lost if we don't act)
- scene4_solution: string — solution narration (what the org does / what donation enables)
- scene5_ask: string — CTA narration (specific ask amount or action, include the URL)
- keywords_scene1: array of 3-5 Pexels search terms (strings) for scene 1 b-roll
- keywords_scene2: array of 3-5 Pexels search terms for scene 2 b-roll
- keywords_scene3: array of 3-5 Pexels search terms for scene 3 b-roll
- keywords_scene4: array of 3-5 Pexels search terms for scene 4 b-roll
- keywords_scene5: array of 3-5 Pexels search terms for scene 5 b-roll
- tagline: short emotional tagline (under 50 chars) for the final card
- rolling_credits: array of objects with "header" and "lines" (array of strings)

Keep each scene narration to ~{scene_words} words. Be specific, emotional, and direct.
For rolling_credits include: org name, produced by Doug Morse, AI Vocal Artist, dmpgh.com.
"""
    data = json.dumps({
        "model": "llama3.1:8b",
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 3000},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            result = json.loads(r.read())
        raw = result.get("response", "")
        # Strip any accidental markdown fences
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
        data = json.loads(raw)
        # Normalize scene fields — Ollama sometimes returns dicts like
        # {"narration": "...", "b_roll": [...]} instead of plain strings
        scene_keys = ["scene1_hook","scene2_problem","scene3_stakes","scene4_solution","scene5_ask"]
        for i, key in enumerate(scene_keys, start=1):
            if key not in data:
                continue
            val = data[key]
            if isinstance(val, dict):
                # Extract narration text; also use b_roll as fallback keywords
                narration = val.get("narration") or val.get("text") or val.get("script") or ""
                b_roll = val.get("b_roll") or val.get("broll") or []
                data[key] = str(narration)
                # If keywords not already set, use b_roll list
                kkey = f"keywords_scene{i}"
                if kkey not in data and b_roll:
                    data[kkey] = [str(k) for k in b_roll[:5]]
            elif not isinstance(val, str):
                data[key] = str(val)
        # Normalize tagline
        if "tagline" in data and not isinstance(data["tagline"], str):
            data["tagline"] = str(data["tagline"])
        # Normalize keywords to list of strings
        for i in range(1, 6):
            kkey = f"keywords_scene{i}"
            if kkey in data:
                kw = data[kkey]
                if isinstance(kw, str):
                    data[kkey] = [kw]
                elif isinstance(kw, list):
                    data[kkey] = [str(k) for k in kw]
        return data
    except Exception as e:
        print(f"Ollama error: {e}")
        return None


PITCH_URL = "dmpgh.com"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT      = "/System/Library/Fonts/Supplemental/Arial.ttf"

GMAIL_ENV = Path.home() / ".env.gmail"
SIZE_LIMIT_MB = 20  # attach directly under this size; otherwise send download link

def deliver_video(to_email, org, video_files, download_base_url="http://localhost:8091", srt_path=None):
    """Email the finished video(s) to the requester."""
    env = load_env(GMAIL_ENV)
    gmail_user = env.get("GMAIL_USER", "")
    gmail_pass = env.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        print("No Gmail creds — skipping delivery email")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"Look Mom No Hands Productions <{gmail_user}>"
    msg["To"] = to_email
    msg["Subject"] = f"Your Fundraiser Video is Ready — {org}"

    attached = []
    links = []

    # Attach SRT caption file if provided
    if srt_path and Path(srt_path).exists():
        with open(srt_path, "rb") as f:
            srt_part = MIMEApplication(f.read(), Name=Path(srt_path).name)
        srt_part["Content-Disposition"] = f'attachment; filename="{Path(srt_path).name}"'
        msg.attach(srt_part)

    for label, fname in video_files.items():
        fpath = OUTPUT_DIR / fname
        if not fpath.exists():
            continue
        size_mb = fpath.stat().st_size / 1024 / 1024
        if size_mb <= SIZE_LIMIT_MB:
            with open(fpath, "rb") as f:
                part = MIMEApplication(f.read(), Name=fname)
            part["Content-Disposition"] = f'attachment; filename="{fname}"'
            msg.attach(part)
            attached.append(label)
        else:
            links.append(f"{label.capitalize()}: {download_base_url}/download/{fname}")

    body = f"""Hi,

Your fundraiser video for {org} is ready!

"""
    if attached:
        body += f"The video{'s are' if len(attached) > 1 else ' is'} attached to this email.\n\n"
    if links:
        body += "Download link(s):\n" + "\n".join(links) + "\n\n"
    body += """This video was produced with Look Mom No Hands Productions — AI-powered fundraiser videos at zero per-video cost.

Want to remove the watermark or use your own branding? Reply to this email or visit dmpgh.com.

— Doug Morse
Look Mom No Hands Productions
dmpgh.com
"""
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo(); server.starttls()
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
        print(f"Video delivered to {to_email}")
        return True
    except Exception as e:
        print(f"Delivery email error: {e}")
        return False


def burn_captions(video_path, srt_path):
    """Burn SRT captions into video — white text, black outline, hardcoded."""
    if not Path(srt_path).exists():
        print(f"SRT not found: {srt_path}")
        return video_path
    out_path = video_path.with_name(video_path.stem + "_cc.mp4")
    # Escape path for ffmpeg subtitles filter
    safe_srt = str(srt_path).replace("'", "\\'").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", (
            f"subtitles='{safe_srt}':force_style='"
            "Fontname=Arial,Fontsize=22,Bold=1,"
            "PrimaryColour=&H00FFFFFF,"   # white
            "OutlineColour=&H00000000,"   # black outline
            "Outline=2,Shadow=0,"
            "MarginV=60"                  # lift above banner
            "'"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if r.returncode != 0:
        print(f"Caption burn failed: {r.stderr[-300:]}")
        return video_path
    video_path.unlink(missing_ok=True)
    out_path.rename(video_path)
    return video_path


def apply_watermark(video_path, watermark_text="dmpgh.com"):
    """Burn a semi-transparent watermark into the video."""
    out_path = video_path.with_name(video_path.stem + "_wm.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", (
            f"drawtext=fontfile='{FONT_BOLD}':"
            f"text='{watermark_text}':"
            f"fontcolor=white@0.25:"
            f"fontsize=28:"
            f"x=w-text_w-24:y=h-text_h-24"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"Watermark failed: {r.stderr[-200:]}")
        return video_path  # return original if watermark fails
    video_path.unlink(missing_ok=True)
    out_path.rename(video_path)
    return video_path


def append_pitch_card(video_path, duration=7, phone=""):
    """Generate a branded pitch card and stitch it onto the end of the video."""
    tmp_dir = video_path.parent / "_pitch_tmp"
    tmp_dir.mkdir(exist_ok=True)
    card_path = tmp_dir / "pitch_card.mp4"
    final_path = OUTPUT_DIR / video_path.name.replace("_v1.mp4", "_v1_final.mp4")
    concat_txt = tmp_dir / "concat.txt"

    # Build pitch card with ffmpeg drawtext on dark background
    fade_d = 0.4

    # Phone line shifts layout up slightly to make room
    phone_filter = ""
    url_y = 620
    if phone:
        safe_phone = phone.replace("'", "")
        url_y = 580
        phone_filter = (
            f",drawtext=fontfile='{FONT_BOLD}':text='{safe_phone}':"
            f"fontcolor=white:fontsize=44:x=(w-text_w)/2:y=650:"
            f"alpha='if(lt(t,{fade_d*2}),t/{fade_d*2},1)'"
        )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0f0f1a:s=1920x1080:d={duration}:r=30",
        "-vf", (
            # Orange accent bar top
            f"drawbox=x=0:y=0:w=1920:h=6:color=0xe05a00@1:t=fill,"
            # Orange accent bar bottom
            f"drawbox=x=0:y=1074:w=1920:h=6:color=0xe05a00@1:t=fill,"
            # Main title
            f"drawtext=fontfile='{FONT_BOLD}':text='LOOK MOM NO HANDS PRODUCTIONS':"
            f"fontcolor=0xe05a00:fontsize=64:x=(w-text_w)/2:y=300:"
            f"alpha='if(lt(t,{fade_d}),t/{fade_d},1)',"
            # Subtitle
            f"drawtext=fontfile='{FONT}':text='AI-Powered Fundraiser Videos':"
            f"fontcolor=white:fontsize=42:x=(w-text_w)/2:y=400:"
            f"alpha='if(lt(t,{fade_d}),t/{fade_d},1)',"
            # Tagline
            f"drawtext=fontfile='{FONT}':text='Fast. Local. Zero Per-Video Cost.':"
            f"fontcolor=0xaaaaaa:fontsize=32:x=(w-text_w)/2:y=475:"
            f"alpha='if(lt(t,{fade_d*2}),t/{fade_d*2},1)',"
            # URL
            f"drawtext=fontfile='{FONT_BOLD}':text='{PITCH_URL}':"
            f"fontcolor=0xe05a00:fontsize=52:x=(w-text_w)/2:y={url_y}:"
            f"alpha='if(lt(t,{fade_d*2}),t/{fade_d*2},1)'"
            + phone_filter
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an",
        str(card_path),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    if r.returncode != 0:
        print(f"Pitch card render failed: {r.stderr[-200:]}")
        return None

    # Concat original + pitch card
    with open(concat_txt, "w") as f:
        f.write(f"file '{video_path}'\n")
        f.write(f"file '{card_path}'\n")

    cmd2 = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(final_path),
    ]
    r2 = subprocess.run(cmd2, capture_output=True, timeout=120)
    import shutil as _sh
    _sh.rmtree(tmp_dir, ignore_errors=True)
    if r2.returncode != 0:
        print(f"Pitch concat failed: {r2.stderr[-200:]}")
        return None

    # Replace original with final
    video_path.unlink(missing_ok=True)
    final_path.rename(video_path)
    return video_path


def run_pipeline(job_id, org, cause, url, length_s, voice, music_style, orientation="landscape", burn_cc=False, srt_captions=False, phone="", ask_amount="", frequency="one-time"):
    """Background worker: write script → run generator → notify."""
    jobs[job_id]["status"] = "writing_script"
    jobs[job_id]["message"] = "Writing script with AI..."

    script_data = write_script_via_ollama(org, cause, url, length_s, ask_amount, frequency)
    if not script_data:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = "Script generation failed — Ollama error"
        return

    # Inject standard rolling credits if Ollama skipped them
    if "rolling_credits" not in script_data:
        script_data["rolling_credits"] = [
            {"header": "LOOK MOM NO HANDS PRODUCTIONS", "lines": ["presents", ""]},
            {"header": "", "lines": [org.upper(), cause]},
            {"header": "PRODUCED BY", "lines": ["Douglas Morse", "AI Vocal Artist"]},
            {"header": "WRITTEN BY", "lines": ["AI Claude (Anthropic)"]},
            {"header": "VOICE", "lines": [f"OpenAI TTS — '{VOICES.get(voice, 'nova')}'"]},
            {"header": "CONTACT", "lines": ["dmpgh.com", "aiva@dmpgh.com"]},
            {"header": "", "lines": ["", "© 2026 Look Mom No Hands Productions"]},
        ]

    # Save script JSON
    safe_slug = re.sub(r"[^a-z0-9_]", "_", org.lower())[:40]
    script_path = SCRIPTS_DIR / f"{safe_slug}_{job_id[:8]}.json"
    with open(script_path, "w") as f:
        json.dump(script_data, f, indent=2)

    jobs[job_id]["status"] = "rendering"
    jobs[job_id]["message"] = "Rendering video (this takes 2-4 minutes)..."

    music = MUSIC_STYLES.get(music_style, MUSIC_STYLES["emotional-piano"])
    tagline = script_data.get("tagline", "")

    # Patch TTS voice in the generator env
    env = os.environ.copy()
    env["FUNDRAISER_VOICE"] = VOICES.get(voice, "nova")

    # Build ask text for script narration and on-screen stamp
    if ask_amount:
        freq_label = "a month" if frequency == "monthly" else "today"
        ask_text  = f"{ask_amount} {freq_label}"                    # e.g. "$25 a month"
        stamp_text = ask_amount.replace(" ", "") + ("/MO" if frequency == "monthly" else "")  # e.g. "$25/MO"
    else:
        ask_text   = "donate today"
        stamp_text = ""

    cmd = [
        sys.executable, GENERATOR,
        "--org", org,
        "--cause", cause,
        "--url", url,
        "--ask", ask_text,
        "--script", str(script_path),
        "--music", music["bed"],
        "--final-music", music["final"],
        "--hero-image", str(BRAND_DIR / "nmss-hero-sunrise.jpg"),
        "--tagline", tagline,
        "--credit-tag", "AI VOCAL ARTIST",
        "--credit-sub", "fundraiser video production",
        "--rolling-credits",
        "--bumper",
    ]
    if phone:
        cmd.extend(["--phone", phone])
    if stamp_text:
        cmd.extend(["--ask-stamp", stamp_text])
    if orientation == "portrait":
        cmd.append("--only-vertical")
    elif orientation == "both":
        cmd.append("--vertical")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=600, env=env,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["message"] = f"Pipeline error:\n{result.stderr[-500:]}"
            pushover(f"Fundraiser FAILED: {org}", result.stderr[-200:])
            return
    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = "Pipeline timed out (>10 min)"
        return

    # Find output files (landscape + optional vertical)
    all_mp4 = sorted(OUTPUT_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
    # Pick the two most recent (vertical and landscape may both be new)
    recent = all_mp4[:4]
    landscape_file = next((f for f in recent if "vertical" not in f.name), None)
    vertical_file  = next((f for f in recent if "vertical" in f.name), None)

    if not landscape_file and not vertical_file:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = "Video not found after render"
        return

    watermark = jobs[job_id].get("watermark", "dmpgh.com")
    video_filenames = {}

    # Find the SRT generated by the pipeline (in the job dir)
    job_dirs = sorted(FUNDRAISER_DIR.iterdir(), key=os.path.getmtime, reverse=True)
    srt_path = None
    for jd in job_dirs[:3]:
        srts = list(jd.glob("*.srt"))
        if srts:
            srt_path = srts[0]
            break

    for label, vf in [("landscape", landscape_file), ("vertical", vertical_file)]:
        if not vf:
            continue
        if burn_cc and srt_path:
            jobs[job_id]["message"] = f"Burning captions ({label})..."
            vf = burn_captions(vf, srt_path)
        if watermark:
            jobs[job_id]["message"] = f"Applying watermark ({label})..."
            vf = apply_watermark(vf, watermark)
        jobs[job_id]["message"] = f"Adding pitch card ({label})..."
        pitched = append_pitch_card(vf, phone=phone)
        if pitched:
            vf = pitched
        video_filenames[label] = vf.name

    jobs[job_id]["status"] = "done"
    jobs[job_id]["message"] = "Done!"
    jobs[job_id]["video_filename"] = video_filenames.get("landscape") or video_filenames.get("vertical")
    jobs[job_id]["video_filenames"] = video_filenames  # both if available
    jobs[job_id]["script_preview"] = {
        "hook":     script_data.get("scene1_hook", "")[:120],
        "ask":      script_data.get("scene5_ask", "")[:120],
        "tagline":  tagline,
    }

    # Email delivery
    to_email = jobs[job_id].get("recipient_email", "")
    if to_email and video_filenames:
        jobs[job_id]["message"] = "Delivering video by email..."
        deliver_video(to_email, org, video_filenames, srt_path=srt_path)
        jobs[job_id]["message"] = "Done! Video emailed to " + to_email

    primary_video = jobs[job_id].get("video_filename", "")
    pushover(
        f"Fundraiser ready: {org}",
        f"Video: {primary_video}\nTagline: {tagline}" + (f"\nEmailed: {to_email}" if to_email else ""),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")

@app.route("/music-styles")
def music_styles():
    return jsonify({k: v["label"] for k, v in MUSIC_STYLES.items()})

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True) or {}

    org         = data.get("org", "").strip()
    cause       = data.get("cause", "").strip()
    url         = data.get("url", "").strip() or "dmpgh.com"
    length_s    = int(data.get("length", 90))
    voice       = data.get("voice", "female")
    music       = data.get("music", "emotional-piano")
    orientation = data.get("orientation", "landscape")  # landscape | portrait | both
    burn_cc     = bool(data.get("captions", False))
    srt_captions = bool(data.get("srt_captions", False))
    recipient_email = data.get("email", "").strip()
    phone       = data.get("phone", "").strip()
    ask_amount  = data.get("ask_amount", "").strip()   # e.g. "$25"
    frequency   = data.get("frequency", "one-time")    # "one-time" | "monthly"

    if not org or not cause:
        return jsonify({"error": "Fundraiser name and cause are required"}), 400

    if length_s not in (60, 90, 120):
        length_s = 90

    job_id = datetime.now().strftime("%Y%m%d%H%M%S")
    jobs[job_id] = {
        "status": "queued",
        "message": "Queued...",
        "org": org,
        "started": datetime.now().isoformat(),
        "recipient_email": recipient_email,
        "phone": phone,
        "ask_amount": ask_amount,
        "frequency": frequency,
    }

    t = threading.Thread(
        target=run_pipeline,
        args=(job_id, org, cause, url, length_s, voice, music, orientation, burn_cc, srt_captions, phone, ask_amount, frequency),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route("/download/<filename>")
def download(filename):
    safe = Path(filename).name  # strip any path traversal
    target = OUTPUT_DIR / safe
    if not target.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(target), as_attachment=True)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "Fundraiser Generator", "jobs": len(jobs)})

@app.route("/ai-news", methods=["POST"])
def trigger_ai_news():
    """Trigger the AI Weekly news video pipeline. Called by n8n on Monday mornings."""
    job_id = "ainews_" + datetime.now().strftime("%Y%m%d%H%M%S")
    jobs[job_id] = {"status": "running", "message": "AI Weekly starting...", "started": datetime.now().isoformat()}

    def run():
        try:
            result = subprocess.run(
                ["python3.12", str(PROJECT_ROOT / "ai_news_generator.py")],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=1800
            )
            if result.returncode == 0:
                jobs[job_id].update({"status": "done", "message": "AI Weekly complete"})
            else:
                jobs[job_id].update({"status": "error", "message": result.stderr[-500:]})
        except Exception as e:
            jobs[job_id].update({"status": "error", "message": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"})


if __name__ == "__main__":
    print("Fundraiser Generator starting on port 8091...")
    print(f"Music styles: {list(MUSIC_STYLES.keys())}")
    print(f"Output: {OUTPUT_DIR}")
    app.run(host="0.0.0.0", port=8091, debug=False)
