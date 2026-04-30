#!/usr/bin/env python3
"""
ai_news_daily.py — Yesterday in AI News
Runs every morning: fetches AI news → writes script → renders video → posts to YouTube → Pushover.

Usage:
    python3.12 ai_news_daily.py
    python3.12 ai_news_daily.py --dry-run   # script only, no render
"""

import json, os, sys, subprocess, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# ---------- config ----------

KNOCKOFF_DIR = Path(__file__).parent
SCRIPTS_DIR  = KNOCKOFF_DIR / "scripts_fundraiser"
VIDEOS_DIR   = Path("/Users/douglasmorse/Documents/Fundraiser Videos")
LOG_DIR      = KNOCKOFF_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

MUSIC        = "music/fundraiser/news-broadcast.mp3"
FINAL_MUSIC  = "music/fundraiser/dramatic-violin-final.mp3"
HERO         = "brand_assets/nmss-hero-sunrise.jpg"

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

_keys     = _load_env("~/.keys/.env")
_pushover = _load_env("~/.env.pushover")

ANTHROPIC_API_KEY  = _keys.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
PUSHOVER_TOKEN     = _pushover.get("PUSHOVER_APP_TOKEN", "")
PUSHOVER_USER      = _pushover.get("PUSHOVER_USER_KEY", "")


# ---------- Pushover ----------

def push(msg, title="Yesterday in AI News"):
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        print(f"[pushover] {msg}")
        return
    try:
        data = urllib.parse.urlencode({
            "token": PUSHOVER_TOKEN, "user": PUSHOVER_USER,
            "title": title, "message": msg
        }).encode()
        urllib.request.urlopen(
            urllib.request.Request("https://api.pushover.net/1/messages.json", data=data),
            timeout=10
        )
    except Exception as e:
        print(f"[pushover error] {e}")


# ---------- fetch AI news via Google News RSS ----------

def fetch_ai_news():
    """Pull top AI headlines from Google News RSS — past 24 hours."""
    url = (
        "https://news.google.com/rss/search?"
        "q=artificial+intelligence+AI&hl=en-US&gl=US&ceid=US:en"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ai-news-daily/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read()
    except Exception as e:
        print(f"[news] RSS fetch failed: {e}")
        return []

    root = ET.fromstring(xml_data)
    cutoff = datetime.utcnow() - timedelta(hours=30)

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc  = (item.findtext("description") or "").strip()
        pub   = item.findtext("pubDate") or ""
        link  = item.findtext("link") or ""
        # try to parse date
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub).replace(tzinfo=None)
            if dt < cutoff:
                continue
        except Exception:
            pass
        if title:
            items.append({"title": title, "desc": desc[:300], "link": link})
        if len(items) >= 20:
            break

    print(f"[news] Found {len(items)} headlines in past 24h")
    return items


# ---------- Claude: pick top stories + write script ----------

def write_script(headlines, date_str):
    """Ask Claude to pick top 3 AI stories and write a KnockOff 5-scene script."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    headlines_text = "\n".join(
        f"{i+1}. {h['title']} — {h['desc'][:150]}"
        for i, h in enumerate(headlines[:20])
    )

    prompt = f"""You are writing a daily 3-minute video script called "Yesterday in AI News" for {date_str}.

Here are today's AI headlines from the past 24 hours:
{headlines_text}

Pick the 3 most significant, interesting stories. Write a tight 5-scene KnockOff video script as a JSON object.

Rules:
- Scene narration should be punchy, plain-spoken, under 100 words per scene
- No jargon. Write for someone who is not a tech person.
- End each scene with a clear "so what" — why this matters to a regular person
- Scene 5 is always the sign-off: "That is Yesterday in AI News. Every weekday morning. Follow for tomorrow's."
- Keywords should be 2-3 Pexels search phrases that match the story visually

Return ONLY valid JSON in exactly this format:
{{
  "scene1_hook": "...",
  "keywords_scene1": ["phrase 1", "phrase 2", "phrase 3"],
  "scene1_overlays": [
    {{"lines": "*HEADLINE|SUBHEAD", "in": 0.5, "out": 4.0, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "Key point", "sub": "Why it matters", "in": 4.5, "out": 10.0}},
    {{"style": "bullet", "head": "Key point 2", "sub": "The detail", "in": 10.5, "out": 16.0}}
  ],
  "scene2_problem": "...",
  "keywords_scene2": ["phrase 1", "phrase 2", "phrase 3"],
  "scene2_overlays": [
    {{"lines": "*HEADLINE|SUBHEAD", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "Key point", "sub": "Why it matters", "in": 4.0, "out": 9.5}},
    {{"style": "bullet", "head": "Key point 2", "sub": "The detail", "in": 10.0, "out": 15.5}}
  ],
  "scene3_stakes": "...",
  "keywords_scene3": ["phrase 1", "phrase 2", "phrase 3"],
  "scene3_overlays": [
    {{"lines": "*HEADLINE|SUBHEAD", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "Key point", "sub": "Why it matters", "in": 4.0, "out": 9.5}},
    {{"style": "bullet", "head": "Key point 2", "sub": "The detail", "in": 10.0, "out": 15.5}}
  ],
  "scene4_solution": "...",
  "keywords_scene4": ["phrase 1", "phrase 2", "phrase 3"],
  "scene4_overlays": [
    {{"lines": "*WHAT THIS|MEANS FOR YOU", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "Key point", "sub": "Why it matters", "in": 4.0, "out": 9.5}},
    {{"style": "bullet", "head": "Key point 2", "sub": "The detail", "in": 10.0, "out": 15.5}}
  ],
  "scene5_ask": "That is Yesterday in AI News. Every weekday morning. If this landed, share it. See you tomorrow.",
  "keywords_scene5": ["morning news anchor professional", "news broadcast studio", "person watching news phone"],
  "tagline": "Yesterday in AI News — {date_str}",
  "rolling_credits": {{
    "header": "YESTERDAY IN AI NEWS",
    "lines": [
      "AI news. Every weekday morning.",
      "Sources: Google News, public reporting",
      "Not financial or medical advice",
      "Produced by Song Juicer — dmpgh.com"
    ]
  }}
}}"""

    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip().rstrip("```").strip()
    return json.loads(raw)


# ---------- render ----------

def run(cmd, label=""):
    print(f"\n{'='*50}")
    if label:
        print(f"▶ {label}")
    print(f"  {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=False, text=True, cwd=str(KNOCKOFF_DIR))
    return result.returncode == 0


def find_latest_job(date_str):
    """Find the most recently created job dir for today."""
    slug = f"AI_News_{date_str.replace('-', '')}"
    candidates = sorted(
        [d for d in (KNOCKOFF_DIR / "fundraisers").iterdir()
         if d.is_dir() and slug in d.name],
        key=lambda d: d.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def find_output_video(job_dir):
    """Find highest-version fundraiser video in job dir."""
    vids = sorted(job_dir.glob("fundraiser_v*.mp4"), reverse=True)
    return vids[0] if vids else None


# ---------- main ----------

def main():
    dry_run = "--dry-run" in sys.argv
    today   = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime("%B %d, %Y")
    date_slug = today.strftime("%Y-%m-%d")
    yt_title  = f"Yesterday in AI News — {yesterday}"
    script_path = SCRIPTS_DIR / f"ai_news_{date_slug}.json"

    log_path = LOG_DIR / f"ai_news_{date_slug}.log"
    sys.stdout = sys.stderr = open(log_path, "w", buffering=1)

    print(f"🗞  Yesterday in AI News — {yesterday}")
    push(f"Starting daily render for {yesterday}...")

    # 1. fetch news
    print("\n[1/6] Fetching headlines...")
    headlines = fetch_ai_news()
    if not headlines:
        push("❌ No headlines found — aborting", "AI News Daily")
        sys.exit(1)

    # 2. write script
    print("\n[2/6] Writing script via Claude...")
    try:
        script = write_script(headlines, yesterday)
    except Exception as e:
        push(f"❌ Script generation failed: {e}", "AI News Daily")
        sys.exit(1)

    # flatten rolling_credits if Claude returned it as dict
    if isinstance(script.get("rolling_credits"), dict):
        rc = script["rolling_credits"]
        script["rolling_credits"] = [{"header": rc.get("header", "YESTERDAY IN AI NEWS")},
                                      {"lines": rc.get("lines", [])}]

    with open(script_path, "w") as f:
        json.dump(script, f, indent=2)
    print(f"  ✅ Script saved: {script_path}")
    push(f"✅ Script written. Top story: {headlines[0]['title'][:80]}")

    if dry_run:
        print("\n[dry-run] Stopping before render.")
        sys.exit(0)

    # 3. render
    print("\n[3/6] Rendering...")
    ok = run([
        "python3.12", "fundraiser_generator.py",
        "--org", "Yesterday in AI News",
        "--cause", "AI news",
        "--url", "dmpgh.com",
        "--qr-url", "paypal.me/dmpgh/25",
        "--ask", "Follow for tomorrow",
        "--script", str(script_path),
        "--music", MUSIC,
        "--final-music", FINAL_MUSIC,
        "--hero-image", HERO,
        "--tagline", f"AI news. Every weekday morning.",
        "--credit-tag", "AI VOCAL ARTIST",
        "--credit-sub", "content video production",
        "--rolling-credits", "--bumper",
    ], "KnockOff render")
    if not ok:
        push("❌ Render failed", "AI News Daily")
        sys.exit(1)

    job_dir = find_latest_job(date_slug.replace("-",""))
    if not job_dir:
        # fallback — find any job created in last 10 min
        all_jobs = sorted(
            (KNOCKOFF_DIR / "fundraisers").iterdir(),
            key=lambda d: d.stat().st_mtime, reverse=True
        )
        job_dir = all_jobs[0] if all_jobs else None

    if not job_dir:
        push("❌ Could not find job dir after render", "AI News Daily")
        sys.exit(1)

    print(f"  Job dir: {job_dir}")

    # 4. enrich b-roll
    print("\n[4/6] Enriching b-roll...")
    run([
        "python3.12", "broll_enricher.py",
        "--job", str(job_dir),
        "--script", str(script_path),
    ], "B-roll enricher")

    # 5. re-render with enriched b-roll
    print("\n[5/6] Re-rendering with enriched b-roll...")
    run([
        "python3.12", "fundraiser_generator.py",
        "--reuse", str(job_dir),
        "--org", "Yesterday in AI News",
        "--cause", "AI news",
        "--url", "dmpgh.com",
        "--qr-url", "paypal.me/dmpgh/25",
        "--ask", "Follow for tomorrow",
        "--script", str(script_path),
        "--music", MUSIC,
        "--final-music", FINAL_MUSIC,
        "--hero-image", HERO,
        "--tagline", "AI news. Every weekday morning.",
        "--credit-tag", "AI VOCAL ARTIST",
        "--credit-sub", "content video production",
        "--rolling-credits", "--bumper",
    ], "Re-render")

    output_video = find_output_video(job_dir)
    if not output_video:
        push("❌ No output video found after render", "AI News Daily")
        sys.exit(1)

    # find the copied version in Documents
    docs_glob = sorted(
        VIDEOS_DIR.glob(f"AI_News_{date_slug.replace('-','')}*v*.mp4"),
        reverse=True
    )
    final_video = docs_glob[0] if docs_glob else output_video

    size_mb = final_video.stat().st_size / 1024 / 1024
    push(f"✅ Rendered: {final_video.name} ({size_mb:.1f} MB). Uploading to YouTube...")

    # 6. post to YouTube
    print("\n[6/6] Posting to YouTube...")
    description = f"""Yesterday in AI News — {yesterday}

Your daily 3-minute briefing on what happened in AI in the past 24 hours. No jargon. Just what it means for real people.

Produced by Song Juicer — dmpgh.com

#AI #ArtificialIntelligence #AINews #TechNews #DailyNews"""

    tags = "AI,artificial intelligence,AI news,daily AI,tech news,ChatGPT,machine learning,2026"

    yt_result = subprocess.run([
        "python3.12", str(KNOCKOFF_DIR / "youtube_upload.py"),
        str(final_video),
        "--title", yt_title,
        "--description", description,
        "--tags", tags,
        "--privacy", "public",
    ], capture_output=True, text=True, cwd=str(KNOCKOFF_DIR))

    print(yt_result.stdout)
    print(yt_result.stderr)

    yt_url = ""
    for line in yt_result.stdout.splitlines():
        if "youtu.be" in line or "youtube.com" in line:
            yt_url = line.strip()
            break

    if yt_url:
        push(f"🎬 Live on YouTube: {yt_url}", "Yesterday in AI News")
        print(f"\n✅ DONE — {yt_url}")
    else:
        push(f"⚠️  Render done but YouTube upload may have failed. Check log.", "AI News Daily")
        print("\n⚠️  YouTube upload did not return a URL — check token expiry")


if __name__ == "__main__":
    main()
