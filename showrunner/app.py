#!/usr/bin/env python3
"""
KnockOff Show Runner — AI-Powered Variety Show Producer

Web dashboard for producing half-hour variety shows with AI-generated scripts and videos.
"""

import json
import subprocess
import sys
import threading
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

PROJECT_ROOT = Path(__file__).parent.parent
SHOWS_DIR = Path(__file__).parent / "shows"
TOOLS_DIR = PROJECT_ROOT / "tools"
OUTPUT_DIR = PROJECT_ROOT / "output" / "keepers"
STATIC_DIR = Path(__file__).parent / "static"
OVERLAYS_DIR = PROJECT_ROOT / "overlays"

sys.path.insert(0, str(TOOLS_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(STATIC_DIR))

# ─── Cast Roster ───────────────────────────────────────────────────────────

CAST = {
    "anderson-cooper":   {"name": "Anderson Cooper",   "network": "CNN",        "voice": "cooper-clone"},
    "jake-tapper":       {"name": "Jake Tapper",       "network": "CNN",        "voice": "kusal"},
    "rachel-maddow":     {"name": "Rachel Maddow",     "network": "MSNBC",      "voice": "maddow-clone"},
    "mika-brzezinski":   {"name": "Mika Brzezinski",   "network": "MSNBC",      "voice": "amy"},
    "joe-scarborough":   {"name": "Joe Scarborough",   "network": "MSNBC",      "voice": "ryan"},
    "lawrence-odonnell": {"name": "Lawrence O'Donnell", "network": "MSNBC",      "voice": "arctic"},
    "jonathan-capehart": {"name": "Jonathan Capehart",  "network": "MSNBC",      "voice": "danny"},
    "eugene-daniels":    {"name": "Eugene Daniels",     "network": "MSNBC",      "voice": "ryan"},
    "sean-hannity":      {"name": "Sean Hannity",       "network": "Fox News",   "voice": "hannity-clone"},
    "tucker-carlson":    {"name": "Tucker Carlson",     "network": "Fox News",   "voice": "tucker-clone"},
    "laura-ingraham":    {"name": "Laura Ingraham",     "network": "Fox News",   "voice": "amy"},
    "bill-oreilly":      {"name": "Bill O'Reilly",      "network": "Fox News",   "voice": "ryan"},
    "lester-holt":       {"name": "Lester Holt",        "network": "NBC",        "voice": "joe"},
    "stephen-a-smith":   {"name": "Stephen A. Smith",   "network": "ESPN",       "voice": "danny"},
    "leland-vittert":    {"name": "Leland Vittert",     "network": "NewsNation", "voice": "kusal"},
    "chris-cuomo":       {"name": "Chris Cuomo",        "network": "NewsNation", "voice": "ryan"},
    "symone-sanders":    {"name": "Symone Sanders",     "network": "MSNBC",      "voice": "amy"},
}

FORMATS = {
    "news_desk":   {"name": "News Desk",      "description": "Split-screen 2-3 speakers", "min_cast": 2, "max_cast": 3, "tool": "news_desk.py"},
    "zoom_call":   {"name": "Zoom Call",       "description": "Grid layout 4-6 speakers",  "min_cast": 4, "max_cast": 6, "tool": "zoom_call.py"},
    "solo":        {"name": "Solo",            "description": "Single speaker full screen", "min_cast": 1, "max_cast": 1, "tool": "generate_avatar_video.py"},
    "commercial":  {"name": "Commercial",      "description": "Single avatar fake ad pitch", "min_cast": 1, "max_cast": 1, "tool": "news_desk.py"},
    "real_ad":     {"name": "Ad Slot",         "description": "Placeholder for real sponsor ad", "min_cast": 0, "max_cast": 0, "tool": None},
    "title_card":  {"name": "Title Card",      "description": "Branded card (intro/outro)", "min_cast": 0, "max_cast": 0, "tool": None},
}

BLOCK_LABELS = ["COLD OPEN", "A", "B", "C", "D", "E", "F", "G", "H", "CLOSER"]

# ─── In-memory job tracker ─────────────────────────────────────────────────

active_jobs = {}  # block_id -> {status, progress, percent, ...}


# ─── Show persistence ──────────────────────────────────────────────────────

def load_show(show_id: str) -> dict:
    path = SHOWS_DIR / f"{show_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_show(show: dict):
    SHOWS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOWS_DIR / f"{show['id']}.json"
    path.write_text(json.dumps(show, indent=2, default=str))


def list_shows() -> list:
    SHOWS_DIR.mkdir(parents=True, exist_ok=True)
    shows = []
    for f in sorted(SHOWS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            shows.append({"id": data["id"], "title": data["title"], "updated": data.get("updated", "")})
        except Exception:
            continue
    return shows


def new_show(title: str) -> dict:
    show = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "target_duration": 1800,  # 30 minutes in seconds
        "blocks": [
            {
                "id": str(uuid.uuid4())[:8],
                "label": "COLD OPEN",
                "format": "news_desk",
                "cast": [],
                "idea": "",
                "script": "",
                "video_path": "",
                "duration": 0,
                "status": "empty",  # empty, scripted, rendering, done, error
            }
        ]
    }
    save_show(show)
    return show


# ─── Script Generation ─────────────────────────────────────────────────────

CHARACTER_STYLES = {
    "anderson-cooper": "calm, dry wit, tries to maintain order",
    "jake-tapper": "sardonic, asks pointed questions",
    "rachel-maddow": "long-winded explainer, loves historical context, tangents",
    "mika-brzezinski": "disapproving, exasperated, scolds people by name",
    "joe-scarborough": "folksy outrage, 'back when I was in Congress'",
    "lawrence-odonnell": "intense, dramatic pauses, gravely serious",
    "jonathan-capehart": "polished DC insider, deadpan delivery",
    "eugene-daniels": "young field correspondent energy, slightly bewildered",
    "sean-hannity": "outraged, defensive, conspiracy-minded, demands his lawyer",
    "tucker-carlson": "rhetorical questions, contrarian, 'just asking questions'",
    "laura-ingraham": "sharp, dismissive, quick comebacks",
    "bill-oreilly": "bombastic, 'the spin stops here', old-school bluster",
    "lester-holt": "gravitas, maintains dignity, dry humor",
    "stephen-a-smith": "loud, emphatic, confused about covering news, sports metaphors",
    "leland-vittert": "straight man, nobody has strong opinions about him",
    "chris-cuomo": "combative, 'let me tell you something', references past career",
    "symone-sanders": "confident, direct, political strategist perspective, 'let me be clear', no-nonsense but warm",
}


def generate_script(block: dict) -> str:
    """Use ollama to generate a comedy script from the block config."""
    cast = block["cast"]
    idea = block["idea"]
    fmt = block["format"]

    # Commercial format: single avatar infomercial pitch
    if fmt == "commercial":
        avatar_id = cast[0] if cast else "sean-hannity"
        info = CAST.get(avatar_id, {"name": avatar_id, "voice": "joe"})
        style = CHARACTER_STYLES.get(avatar_id, "professional news anchor")
        header = f"HOST (avatar: {avatar_id}, voice: {info['voice']}):"

        prompt = f"""Write a fake infomercial/commercial script for KNOCKOFF NEWS, a comedy show.

FORMAT RULES (follow exactly):
- ONE speaker only: HOST
- First line MUST be: {header}
- All dialogue is HOST speaking directly to camera
- 6-10 lines of pitch, about 30-60 seconds when spoken
- Each line is 1-2 sentences
- NO stage directions, NO parentheticals, NO action descriptions
- Between each line, write "HOST:" on its own line

THE PITCHMAN: {info['name']} ({info.get('network', '')}). Style: {style}

COMEDY RULES:
- Parody of late-night infomercials and QVC
- Product starts semi-plausible, gets increasingly absurd
- Include a fake price ("Only $19.99!"), a "but wait there's more" moment
- End with ridiculous fine print or callback
- Deadpan delivery — sell it like it's real

THE PRODUCT/SCENARIO:
{idea}

Write the complete script now. Start with the header line, then the pitch."""

        result = subprocess.run(
            ["ollama", "run", "llama3.1:8b"],
            input=prompt, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Script generation failed: {result.stderr}")

        raw = result.stdout.strip()
        lines = raw.split('\n')
        cleaned = [header, "", ""]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("HOST (avatar:"):
                continue
            if stripped.startswith("```") or stripped.startswith("#"):
                continue
            if stripped.startswith("HOST:"):
                cleaned.append("")
                cleaned.append(stripped)
                continue
            if stripped:
                cleaned.append(stripped)
            elif not stripped:
                cleaned.append("")
        return "\n".join(cleaned)

    # Standard multi-speaker format
    if fmt == "news_desk" and len(cast) == 2:
        role_names = ["HOST", "GUEST"]
    elif fmt == "news_desk" and len(cast) == 3:
        role_names = ["HOST", "GUEST1", "GUEST2"]
    elif fmt == "zoom_call":
        role_names = [c.split("-")[0].upper() for c in cast]
    else:
        role_names = ["HOST"] + [f"GUEST{i}" for i in range(1, len(cast))]

    # Build character descriptions
    char_desc = []
    headers = []
    for i, avatar_id in enumerate(cast):
        info = CAST[avatar_id]
        style = CHARACTER_STYLES.get(avatar_id, "professional news anchor")
        role = role_names[i] if i < len(role_names) else f"SPEAKER{i}"
        char_desc.append(f"- {role} is {info['name']} ({info['network']}). Style: {style}")
        headers.append(f"{role} (avatar: {avatar_id}, voice: {info['voice']}):")

    prompt = f"""Write a satirical news segment script for KNOCKOFF NEWS, a comedy show that parodies cable news.

FORMAT RULES (follow exactly):
- Speakers: {', '.join(role_names)}
- First lines MUST be the header declarations exactly like this:
{chr(10).join(headers)}
- After headers, alternate between speakers with dialogue
- Each speaker's dialogue is plain text, 1-3 sentences per turn
- Aim for 12-18 exchanges total (about 2-3 minutes when spoken)
- NO stage directions, NO parentheticals, NO action descriptions

CHARACTERS:
{chr(10).join(char_desc)}

COMEDY RULES:
- Deadpan delivery — absurd content stated as serious news
- Each character stays in their personality
- Humor escalates through the segment
- Include callback jokes and running gags
- End with a strong punchline

THE SCENARIO:
{idea}

Write the complete script now. Start with the header lines, then dialogue."""

    result = subprocess.run(
        ["ollama", "run", "llama3.1:8b"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Script generation failed: {result.stderr}")

    raw = result.stdout.strip()

    # Clean up: ensure proper headers
    lines = raw.split('\n')
    cleaned = headers + ["", ""]

    in_dialogue = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(f"{r} (avatar:") for r in role_names):
            in_dialogue = True
            continue
        if stripped.startswith("```") or stripped.startswith("#"):
            continue
        if any(stripped.startswith(f"{r}:") for r in role_names):
            in_dialogue = True
            cleaned.append("")
            cleaned.append(stripped)
            continue
        if in_dialogue and stripped:
            cleaned.append(stripped)
        elif not stripped:
            cleaned.append("")

    return "\n".join(cleaned)


# ─── Render Pipeline ───────────────────────────────────────────────────────

def render_block(show_id: str, block_id: str):
    """Render a single block in a background thread."""
    show = load_show(show_id)
    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return

    active_jobs[block_id] = {"status": "rendering", "progress": "Starting...", "percent": 5}

    try:
        # Save script to temp file
        script_path = PROJECT_ROOT / "scripts" / f"show_{show_id}_{block_id}.md"
        script_path.write_text(block["script"])

        fmt = block["format"]
        tool = FORMATS[fmt]["tool"]
        if not tool:
            # real_ad and title_card don't render — video_path set manually or skipped
            active_jobs[block_id] = {"status": "done", "progress": "No render needed", "percent": 100}
            block["status"] = "done"
            save_show(show)
            return

        active_jobs[block_id]["progress"] = "Rendering video..."
        active_jobs[block_id]["percent"] = 10

        if fmt == "zoom_call":
            cmd = [sys.executable, str(TOOLS_DIR / "zoom_call.py"), "--script", str(script_path)]
        else:
            cmd = [sys.executable, str(TOOLS_DIR / "news_desk.py"), "--script", str(script_path)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        if result.returncode != 0:
            active_jobs[block_id] = {"status": "error", "progress": result.stderr[-200:], "percent": 0}
            block["status"] = "error"
            save_show(show)
            return

        # Find the output file
        import glob
        if fmt == "zoom_call":
            pattern = str(OUTPUT_DIR / "zoom_*.mp4")
        else:
            pattern = str(PROJECT_ROOT / ".tmp" / "avatar" / "output" / "newsdesk_*.mp4")

        outputs = sorted(glob.glob(pattern), key=lambda x: Path(x).stat().st_mtime, reverse=True)
        if outputs:
            video_path = outputs[0]
            # Copy to show output
            show_output = OUTPUT_DIR / "shows" / show_id
            show_output.mkdir(parents=True, exist_ok=True)
            dest = show_output / f"{block['label'].lower().replace(' ', '_')}_{block_id}.mp4"
            import shutil
            shutil.copy2(video_path, str(dest))
            block["video_path"] = str(dest)

            # Get duration
            dur_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(dest)],
                capture_output=True, text=True
            )
            block["duration"] = float(dur_result.stdout.strip())

        block["status"] = "done"
        show["updated"] = datetime.now().isoformat()
        save_show(show)
        active_jobs[block_id] = {"status": "done", "progress": "Complete", "percent": 100}

    except Exception as e:
        logger.error(f"Render failed: {e}")
        active_jobs[block_id] = {"status": "error", "progress": str(e)[:200], "percent": 0}
        block["status"] = "error"
        save_show(show)


# ─── Title Card Generator ─────────────────────────────────────────────────

def generate_title_card(label: str, output_path: Path, duration: float = 3.0):
    """Generate a segment title card using ffmpeg drawtext on a branded background."""
    # Use bumper_frame.png as background if it exists, otherwise black
    bg = OVERLAYS_DIR / "bumper_frame.png"
    if bg.exists():
        input_args = ["-loop", "1", "-i", str(bg)]
    else:
        input_args = ["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1920x1080:d={duration}"]

    # Clean up label for display (e.g. "A — MAIN SEGMENT" -> two lines)
    if " — " in label:
        parts = label.split(" — ", 1)
        title_top = parts[0].strip()
        title_bottom = parts[1].strip()
    elif label in ("COLD OPEN", "CLOSER"):
        title_top = ""
        title_bottom = label
    elif label.startswith("COMMERCIAL"):
        title_top = ""
        title_bottom = label
    else:
        title_top = ""
        title_bottom = label

    # Build drawtext filters
    filters = []
    if title_top:
        filters.append(
            f"drawtext=text='{title_top}':fontsize=120:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-80:font=Helvetica Neue:"
            f"borderw=3:bordercolor=black"
        )
        filters.append(
            f"drawtext=text='{title_bottom}':fontsize=60:fontcolor=0xcccccc:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+60:font=Helvetica Neue:"
            f"borderw=2:bordercolor=black"
        )
    else:
        filters.append(
            f"drawtext=text='{title_bottom}':fontsize=100:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:font=Helvetica Neue:"
            f"borderw=3:bordercolor=black"
        )

    # Add KNOCKOFF NEWS branding at bottom
    filters.append(
        f"drawtext=text='KNOCKOFF NEWS':fontsize=30:fontcolor=0xff3333:"
        f"x=(w-text_w)/2:y=h-80:font=Helvetica Neue:borderw=2:bordercolor=black"
    )

    # Add fade in/out
    filters.append(f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - 0.5}:d=0.5")

    vf = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
    ] + input_args + [
        "-t", str(duration),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,{vf}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-r", "30", "-an",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Title card failed: {result.stderr[-300:]}")
        raise RuntimeError(f"Title card generation failed for '{label}'")

    return output_path


def generate_ad_placeholder(output_path: Path, duration: float = 15.0):
    """Generate a 'buy this ad space' placeholder card."""
    bg = OVERLAYS_DIR / "bumper_frame.png"
    if bg.exists():
        input_args = ["-loop", "1", "-i", str(bg)]
    else:
        input_args = ["-f", "lavfi", "-i", f"color=c=0x0a0a1e:s=1920x1080:d={duration}"]

    filters = [
        "drawtext=text='YOUR AD HERE':fontsize=90:fontcolor=0xffcc00:"
        "x=(w-text_w)/2:y=(h-text_h)/2-60:font=Helvetica Neue:"
        "borderw=3:bordercolor=black",
        "drawtext=text='Buy this commercial space':fontsize=50:fontcolor=white:"
        "x=(w-text_w)/2:y=(h-text_h)/2+50:font=Helvetica Neue:"
        "borderw=2:bordercolor=black",
        "drawtext=text='It\\\'s much cheaper than you think. Get in early.':fontsize=35:fontcolor=0xaaaaaa:"
        "x=(w-text_w)/2:y=(h-text_h)/2+120:font=Helvetica Neue:"
        "borderw=1:bordercolor=black",
        "drawtext=text='knockoffnews.com/advertise':fontsize=30:fontcolor=0xff3333:"
        "x=(w-text_w)/2:y=h-80:font=Helvetica Neue:borderw=2:bordercolor=black",
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - 0.5}:d=0.5",
    ]

    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
    ] + input_args + [
        "-t", str(duration),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,{vf}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-r", "30", "-an",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


# ─── Show Assembly ────────────────────────────────────────────────────────

def assemble_show(show: dict, output_path: Path = None) -> Path:
    """Stitch all rendered blocks into a final show MP4 with title cards and stings."""
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="knockoff_assemble_"))

    # Pre-normalize the segment sting (1.5s bumper tail) if it exists
    segment_sting = OVERLAYS_DIR / "segment_sting.mp4"
    sting_norm = None
    if segment_sting.exists():
        sting_norm = tmpdir / "sting_norm.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(segment_sting),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-r", "30",
            str(sting_norm)
        ], capture_output=True, check=True)

    # Collect all segments in order: title card + rendered block + sting
    concat_segments = []
    segment_idx = 0
    rendered_blocks = [b for b in show["blocks"] if b.get("video_path") and Path(b["video_path"]).exists()]

    for i, block in enumerate(rendered_blocks):
        is_commercial = block["label"].startswith("COMMERCIAL")
        is_real_ad = block.get("format") == "real_ad"

        # Skip title cards for commercials and real ad slots — they go straight in
        if not is_commercial and not is_real_ad:
            # Generate title card for this segment
            card_path = tmpdir / f"title_{segment_idx:02d}.mp4"
            generate_title_card(block["label"], card_path, duration=3.0)

            # Title cards need silent audio to match the rendered blocks
            card_with_audio = tmpdir / f"title_audio_{segment_idx:02d}.mp4"
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(card_path),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                str(card_with_audio)
            ], capture_output=True, check=True)
            concat_segments.append(card_with_audio)

        # Normalize the rendered block to ensure consistent format for concat
        norm_path = tmpdir / f"norm_{segment_idx:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(block["video_path"]),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-r", "30",
            str(norm_path)
        ], capture_output=True, check=True)
        concat_segments.append(norm_path)

        # After spoof commercials, insert "buy this ad space" placeholder
        # (only if the next block is a real_ad slot with no video, or there's no ad slot)
        if is_commercial:
            # Check if there's a real ad slot right after this one
            next_in_show = None
            block_idx_in_show = show["blocks"].index(block)
            if block_idx_in_show + 1 < len(show["blocks"]):
                next_in_show = show["blocks"][block_idx_in_show + 1]

            if next_in_show and next_in_show.get("format") == "real_ad":
                if not next_in_show.get("video_path") or not Path(next_in_show["video_path"]).exists():
                    # No real ad uploaded — show placeholder
                    placeholder = tmpdir / f"ad_placeholder_{segment_idx}.mp4"
                    generate_ad_placeholder(placeholder, duration=15.0)
                    placeholder_audio = tmpdir / f"ad_placeholder_audio_{segment_idx}.mp4"
                    subprocess.run([
                        "ffmpeg", "-y",
                        "-i", str(placeholder),
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-c:v", "copy", "-c:a", "aac", "-shortest",
                        str(placeholder_audio)
                    ], capture_output=True, check=True)
                    concat_segments.append(placeholder_audio)

        # Add segment sting after non-commercial blocks (not after the very last block)
        next_rendered = rendered_blocks[i + 1] if i + 1 < len(rendered_blocks) else None
        if sting_norm and not is_commercial and not is_real_ad:
            # Add sting unless next block is the closer
            if next_rendered and next_rendered["label"] != "CLOSER":
                concat_segments.append(sting_norm)

        segment_idx += 1

    if not concat_segments:
        raise RuntimeError("No rendered blocks to assemble")

    # Add intro if it exists
    intro = OVERLAYS_DIR / "intro_card.mp4"
    if intro.exists():
        intro_norm = tmpdir / "intro_norm.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(intro),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-r", "30",
            str(intro_norm)
        ], capture_output=True, check=True)
        concat_segments.insert(0, intro_norm)

    # Add outro if it exists
    outro = OVERLAYS_DIR / "outro_card.mp4"
    if outro.exists():
        outro_norm = tmpdir / "outro_norm.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(outro),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-r", "30",
            str(outro_norm)
        ], capture_output=True, check=True)
        concat_segments.append(outro_norm)

    # Write concat list
    concat_list = tmpdir / "concat.txt"
    with open(concat_list, "w") as f:
        for seg in concat_segments:
            f.write(f"file '{seg}'\n")

    # Final assembly
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_title = show["title"].lower().replace(" ", "_")[:30]
        output_path = OUTPUT_DIR / f"show_{safe_title}_{timestamp}.mp4"

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        str(output_path)
    ], capture_output=True, check=True)

    logger.info(f"Show assembled: {output_path}")
    return output_path


# ─── API Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(str(STATIC_DIR), 'index.html')


@app.route('/api/cast')
def api_cast():
    return jsonify(CAST)


@app.route('/api/formats')
def api_formats():
    return jsonify(FORMATS)


@app.route('/api/shows', methods=['GET'])
def api_list_shows():
    return jsonify(list_shows())


@app.route('/api/shows', methods=['POST'])
def api_create_show():
    data = request.json
    show = new_show(data.get("title", "Untitled Show"))
    return jsonify(show)


@app.route('/api/shows/<show_id>', methods=['GET'])
def api_get_show(show_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404
    return jsonify(show)


@app.route('/api/shows/<show_id>', methods=['PUT'])
def api_update_show(show_id):
    data = request.json
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    if "title" in data:
        show["title"] = data["title"]
    if "blocks" in data:
        show["blocks"] = data["blocks"]

    show["updated"] = datetime.now().isoformat()
    save_show(show)
    return jsonify(show)


@app.route('/api/shows/<show_id>/blocks', methods=['POST'])
def api_add_block(show_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    data = request.json or {}
    block_num = len(show["blocks"])
    label = BLOCK_LABELS[min(block_num, len(BLOCK_LABELS) - 1)]

    block = {
        "id": str(uuid.uuid4())[:8],
        "label": data.get("label", label),
        "format": data.get("format", "news_desk"),
        "cast": data.get("cast", []),
        "idea": data.get("idea", ""),
        "script": "",
        "video_path": "",
        "duration": 0,
        "status": "empty",
    }
    show["blocks"].append(block)
    show["updated"] = datetime.now().isoformat()
    save_show(show)
    return jsonify(block)


@app.route('/api/shows/<show_id>/blocks/<block_id>', methods=['PUT'])
def api_update_block(show_id, block_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    data = request.json
    for key in ["label", "format", "cast", "idea", "script", "status"]:
        if key in data:
            block[key] = data[key]

    show["updated"] = datetime.now().isoformat()
    save_show(show)
    return jsonify(block)


@app.route('/api/shows/<show_id>/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(show_id, block_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    show["blocks"] = [b for b in show["blocks"] if b["id"] != block_id]
    show["updated"] = datetime.now().isoformat()
    save_show(show)
    return jsonify({"ok": True})


@app.route('/api/shows/<show_id>/blocks/<block_id>/suggest-idea', methods=['POST'])
def api_suggest_idea(show_id, block_id):
    """AI suggests a funny scenario based on cast and format."""
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    # Build cast description
    cast_names = []
    for c in block.get("cast", []):
        info = CAST.get(c, {})
        style = CHARACTER_STYLES.get(c, "")
        cast_names.append(f"{info.get('name', c)} ({info.get('network', '')} — {style})")

    fmt = FORMATS.get(block["format"], {})

    # Get existing ideas from other blocks to avoid repeats
    existing = [b["idea"] for b in show["blocks"] if b["idea"] and b["id"] != block_id]
    avoid_text = ""
    if existing:
        avoid_text = f"\n\nDo NOT suggest anything similar to these ideas already in the show:\n" + "\n".join(f"- {e[:80]}" for e in existing)

    prompt = f"""You are a comedy writer for KNOCKOFF NEWS, a satirical show that parodies cable news.

Suggest ONE funny, absurd scenario for a {fmt.get('name', 'news')} segment.

The cast for this segment:
{chr(10).join(cast_names) if cast_names else 'Not yet selected — suggest something that would work for any pairing'}

Requirements:
- One paragraph, 2-4 sentences describing the scenario
- Should be absurd but stated as if it's real breaking news
- Play to the characters' personalities and create natural conflict between them
- Think current events but twisted into comedy
- The funnier and more specific the better{avoid_text}

Respond with ONLY the scenario paragraph. No preamble, no options, just the one idea."""

    try:
        result = subprocess.run(
            ["ollama", "run", "llama3.1:8b"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return jsonify({"error": "AI suggestion failed"}), 500

        idea = result.stdout.strip()
        # Clean up any quotes or markdown
        idea = idea.strip('"').strip("'").strip('*')
        return jsonify({"idea": idea})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/shows/<show_id>/blocks/<block_id>/generate-script', methods=['POST'])
def api_generate_script(show_id, block_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    if not block["idea"]:
        return jsonify({"error": "No idea provided"}), 400
    if not block["cast"]:
        return jsonify({"error": "No cast selected"}), 400

    try:
        script = generate_script(block)
        block["script"] = script
        block["status"] = "scripted"
        show["updated"] = datetime.now().isoformat()
        save_show(show)
        return jsonify({"script": script})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/shows/<show_id>/blocks/<block_id>/render', methods=['POST'])
def api_render_block(show_id, block_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    if not block["script"]:
        return jsonify({"error": "No script to render"}), 400

    block["status"] = "rendering"
    save_show(show)

    thread = threading.Thread(target=render_block, args=(show_id, block_id))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "rendering"})


@app.route('/api/shows/<show_id>/auto-produce', methods=['POST'])
def api_auto_produce(show_id):
    """AI produces an entire 30-minute show — picks cast, writes ideas, generates scripts."""
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    import random

    # Standard variety show template
    # 2 spoof commercials (AI-generated) + 2 real ad slots (placeholder for sponsors)
    SHOW_TEMPLATE = [
        {"label": "COLD OPEN", "format": "news_desk", "cast_size": 2, "duration_target": 150,
         "prompt": "a quick punchy cold open about a breaking absurd news story"},
        {"label": "A — MAIN SEGMENT", "format": "news_desk", "cast_size": 2, "duration_target": 210,
         "prompt": "a longer deep-dive news segment with back and forth debate on an absurd topic"},
        {"label": "COMMERCIAL", "format": "commercial", "cast_size": 1, "duration_target": 60,
         "prompt": "a fake infomercial for a ridiculous product pitched by a news anchor — think QVC meets late night, absurd product with a straight-faced pitch"},
        {"label": "AD SLOT 1", "format": "real_ad", "cast_size": 0, "duration_target": 30,
         "prompt": "placeholder for real sponsor advertisement"},
        {"label": "B — PANEL", "format": "zoom_call", "cast_size": 5, "duration_target": 240,
         "prompt": "a heated panel discussion where everyone disagrees about something trivial"},
        {"label": "C — WEEKEND UPDATE", "format": "news_desk", "cast_size": 2, "duration_target": 180,
         "prompt": "a Weekend Update style desk anchor to field correspondent report on an absurd situation"},
        {"label": "COMMERCIAL 2", "format": "commercial", "cast_size": 1, "duration_target": 60,
         "prompt": "a fake infomercial for KnockOff News merchandise or a parody product — the anchor sells it dead serious"},
        {"label": "AD SLOT 2", "format": "real_ad", "cast_size": 0, "duration_target": 30,
         "prompt": "placeholder for real sponsor advertisement"},
        {"label": "D — WILDCARD", "format": "zoom_call", "cast_size": 6, "duration_target": 240,
         "prompt": "a roast, talent show, game show, or other variety segment that's completely absurd"},
        {"label": "E — INTERVIEW", "format": "news_desk", "cast_size": 2, "duration_target": 180,
         "prompt": "a one-on-one interview where the guest reveals something increasingly ridiculous"},
        {"label": "CLOSER", "format": "news_desk", "cast_size": 2, "duration_target": 90,
         "prompt": "a short closing segment that wraps up the show with a callback to earlier segments"},
    ]

    all_cast = list(CAST.keys())

    # Generate the full show
    show["blocks"] = []
    used_cast_combos = []

    for template in SHOW_TEMPLATE:
        # Pick cast — avoid repeating exact same pairing
        available = all_cast.copy()
        random.shuffle(available)
        cast = available[:template["cast_size"]]

        # Try to avoid identical pairings
        attempts = 0
        while sorted(cast) in used_cast_combos and attempts < 10:
            random.shuffle(available)
            cast = available[:template["cast_size"]]
            attempts += 1
        used_cast_combos.append(sorted(cast))

        block = {
            "id": str(uuid.uuid4())[:8],
            "label": template["label"],
            "format": template["format"],
            "cast": cast,
            "idea": "",
            "script": "",
            "video_path": "",
            "duration": 0,
            "status": "empty",
        }
        show["blocks"].append(block)

    show["updated"] = datetime.now().isoformat()
    save_show(show)

    # Now generate ideas and scripts for each block in sequence
    def produce_all():
        for block in show["blocks"]:
            cast_names = [CAST[c]["name"] for c in block["cast"] if c in CAST]
            template_entry = next((t for t in SHOW_TEMPLATE if t["label"] == block["label"]), None)
            segment_prompt = template_entry["prompt"] if template_entry else "a funny news segment"

            # Generate idea
            idea_prompt = f"""You are a comedy writer for KNOCKOFF NEWS, a satirical show that parodies cable news.

Suggest ONE funny, absurd scenario for {segment_prompt}.

The cast: {', '.join(cast_names)}

Requirements:
- One paragraph, 2-4 sentences
- Absurd but stated as real breaking news
- Specific and funny
- Play to character personalities

Respond with ONLY the scenario paragraph."""

            try:
                result = subprocess.run(
                    ["ollama", "run", "llama3.1:8b"],
                    input=idea_prompt, capture_output=True, text=True, timeout=30
                )
                block["idea"] = result.stdout.strip().strip('"').strip("'").strip('*')
            except Exception:
                block["idea"] = f"Breaking: {cast_names[0] if cast_names else 'An anchor'} discovers something shocking."

            # Generate script
            try:
                script = generate_script(block)
                block["script"] = script
                block["status"] = "scripted"
            except Exception as e:
                block["status"] = "error"
                logger.error(f"Script gen failed for {block['label']}: {e}")

            show["updated"] = datetime.now().isoformat()
            save_show(show)

    thread = threading.Thread(target=produce_all)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "producing", "blocks": len(show["blocks"])})


@app.route('/api/shows/<show_id>/blocks/<block_id>/set-video', methods=['POST'])
def api_set_video(show_id, block_id):
    """Set a video path for ad slots or any block (e.g. sponsor ads)."""
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    data = request.json
    video_path = data.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video file not found"}), 400

    block["video_path"] = video_path
    block["status"] = "done"

    # Get duration
    dur_result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    if dur_result.stdout.strip():
        block["duration"] = float(dur_result.stdout.strip())

    show["updated"] = datetime.now().isoformat()
    save_show(show)
    return jsonify(block)


@app.route('/api/shows/<show_id>/assemble', methods=['POST'])
def api_assemble_show(show_id):
    """Assemble all rendered blocks into a final show with title cards."""
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    # Check that at least some blocks are rendered
    rendered = [b for b in show["blocks"] if b.get("video_path") and Path(b["video_path"]).exists()]
    if not rendered:
        return jsonify({"error": "No rendered blocks to assemble"}), 400

    active_jobs["assemble"] = {"status": "assembling", "progress": f"Stitching {len(rendered)} segments...", "percent": 10}

    def do_assemble():
        try:
            result = assemble_show(show)
            show["final_video"] = str(result)
            show["updated"] = datetime.now().isoformat()
            save_show(show)
            active_jobs["assemble"] = {"status": "done", "progress": "Complete", "percent": 100, "path": str(result)}
        except Exception as e:
            logger.error(f"Assembly failed: {e}")
            active_jobs["assemble"] = {"status": "error", "progress": str(e)[:200], "percent": 0}

    thread = threading.Thread(target=do_assemble)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "assembling", "rendered_blocks": len(rendered), "total_blocks": len(show["blocks"])})


@app.route('/api/shows/<show_id>/final')
def api_final_video(show_id):
    """Serve the assembled final show video."""
    show = load_show(show_id)
    if not show or not show.get("final_video"):
        return jsonify({"error": "No final video"}), 404

    video_path = Path(show["final_video"])
    if not video_path.exists():
        return jsonify({"error": "Final video file missing"}), 404

    return send_from_directory(str(video_path.parent), video_path.name)


@app.route('/api/jobs')
def api_jobs():
    return jsonify(active_jobs)


@app.route('/api/shows/<show_id>/blocks/<block_id>/preview')
def api_preview(show_id, block_id):
    show = load_show(show_id)
    if not show:
        return jsonify({"error": "Show not found"}), 404

    block = next((b for b in show["blocks"] if b["id"] == block_id), None)
    if not block or not block["video_path"]:
        return jsonify({"error": "No video"}), 404

    video_path = Path(block["video_path"])
    if not video_path.exists():
        return jsonify({"error": "Video file missing"}), 404

    return send_from_directory(str(video_path.parent), video_path.name)


if __name__ == "__main__":
    import webbrowser

    print("\n" + "=" * 50)
    print("  KNOCKOFF NEWS — Show Runner")
    print("  http://localhost:5050")
    print("=" * 50 + "\n")

    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5050")).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
