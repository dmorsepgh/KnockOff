#!/usr/bin/env python3.12
"""
AI Weekly News Video Generator
Fetches AI news + story images, writes punchy 4-section script via Claude,
renders via fundraiser pipeline with real news images as b-roll.
"""
import os, json, subprocess, feedparser, anthropic, requests, re, shutil
from datetime import datetime, timedelta
from pathlib import Path
from html.parser import HTMLParser

KNOCKOFF_DIR = Path(__file__).parent
SCRIPTS_DIR  = KNOCKOFF_DIR / "scripts_fundraiser"
SCRIPTS_DIR.mkdir(exist_ok=True)

# Load keys
_keys_file = Path.home() / ".keys" / ".env"
if _keys_file.exists():
    for _line in _keys_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://hnrss.org/frontpage?q=AI&points=50",
    "https://www.artificialintelligence-news.com/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def get_og_image(url):
    """Fetch the og:image from an article URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', r.text)
        if not match:
            match = re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', r.text)
        return match.group(1) if match else None
    except Exception:
        return None

def download_image(url, dest_path):
    """Download an image to disk."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200 and len(r.content) > 5000:
            dest_path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False

def image_to_broll(img_path, out_path, duration=12):
    """Ken Burns pan/zoom effect: image → video clip."""
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf", (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration*25)}:s=1920x1080:fps=25"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def fetch_news(days_back=7, max_per_feed=5):
    """Fetch stories + og:images from RSS feeds."""
    cutoff = datetime.now() - timedelta(days=days_back)
    stories = []
    print("  Fetching RSS feeds...")
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                if published and published < cutoff:
                    continue
                title   = getattr(entry, 'title', '').strip()
                summary = getattr(entry, 'summary', '').strip()
                # Strip HTML from summary
                summary = re.sub(r'<[^>]+>', '', summary)[:300]
                link    = getattr(entry, 'link', '')
                source  = feed.feed.get('title', url)
                if title and link:
                    stories.append({
                        "title": title,
                        "summary": summary,
                        "url": link,
                        "source": source,
                        "image": None
                    })
        except Exception as e:
            print(f"    Feed error: {e}")

    print(f"  Fetched {len(stories)} stories — scraping images...")
    img_dir = KNOCKOFF_DIR / "_news_images"
    img_dir.mkdir(exist_ok=True)
    for i, s in enumerate(stories[:20]):
        img_url = get_og_image(s["url"])
        if img_url:
            ext = ".jpg" if "jpg" in img_url.lower() or "jpeg" in img_url.lower() else ".png"
            dest = img_dir / f"story_{i}{ext}"
            if download_image(img_url, dest):
                s["image"] = str(dest)
                print(f"    ✓ Image: {s['title'][:50]}")
    return stories

def build_scene_broll(stories_for_scene, scene_dir, duration=15):
    """Create Ken Burns video clip from story images for a scene."""
    scene_dir = Path(scene_dir)
    scene_dir.mkdir(parents=True, exist_ok=True)
    images = [s["image"] for s in stories_for_scene if s.get("image")]
    if not images:
        return False
    # Use first available image as broll_0
    out = scene_dir / "broll_0.mp4"
    if image_to_broll(Path(images[0]), out, duration=duration):
        print(f"    📷 News image broll: {Path(images[0]).name}")
        return True
    return False

def write_script(stories):
    client = anthropic.Anthropic()
    week_of = datetime.now().strftime("%B %d, %Y")

    story_lines = []
    for s in stories[:30]:
        story_lines.append(f"[{s['source']}] {s['title']}: {s['summary']}")
    stories_text = "\n".join(story_lines)

    prompt = f"""You are writing an EXCITING weekly AI news video script for week of {week_of}.

Tone: High-energy news anchor. Think ESPN SportsCenter meets breaking news. Punchy sentences. Short, punchy delivery. Drop names. Make it exciting — this is the most insane week in AI history (they all are).

Here are this week's AI news stories:
{stories_text}

Write a 5-scene video script JSON. CRITICAL overlay rules:
- Use "lines" field (NOT "text") for simple text overlays — pipe-separate multiple lines
- Use style:"bullet" with "head" + "sub" fields for bullet overlays
- Scene section HEADLINE goes top-center: x="(W-w)/2", y="80", shows first 3 seconds
- Bullets appear after the headline, staggered 4 seconds apart
- Keep overlay text SHORT — max 6 words per line

Return ONLY this JSON structure:

{{
  "scene1_hook": "Punchy 2-sentence hook — drop the biggest story first, make it sound urgent",
  "keywords_scene1": ["news studio", "breaking news screen", "television anchor desk"],
  "scene1_overlays": [
    {{"lines": "*AI WEEKLY|Week of {week_of}", "in": 0.5, "out": 4.0, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "[Biggest story — 5 words]", "sub": "[one line detail]", "in": 4.5, "out": 9.0}},
    {{"style": "bullet", "head": "[Second story — 5 words]", "sub": "[one line detail]", "in": 9.5, "out": 14.0}}
  ],

  "scene2_problem": "TOP STORIES — 3-4 punchy sentences. Name companies, numbers, CEOs. Make it exciting.",
  "keywords_scene2": ["technology news", "artificial intelligence", "data center servers"],
  "scene2_overlays": [
    {{"lines": "*TOP STORIES|THIS WEEK", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "[Story 1 — 5 words]", "sub": "[key number or fact]", "in": 4.0, "out": 8.5}},
    {{"style": "bullet", "head": "[Story 2 — 5 words]", "sub": "[key number or fact]", "in": 9.0, "out": 13.5}},
    {{"style": "bullet", "head": "[Story 3 — 5 words]", "sub": "[key number or fact]", "in": 14.0, "out": 18.5}}
  ],

  "scene3_stakes": "VIEWS — 3-4 sentences of hot takes. What does this MEAN? Who wins, who loses, who should be scared? Be bold.",
  "keywords_scene3": ["analysis chart data", "business strategy meeting", "technology disruption"],
  "scene3_overlays": [
    {{"lines": "*VIEWS &|ANALYSIS", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "[Hot take 1 — 5 words]", "sub": "[why it matters]", "in": 4.0, "out": 8.5}},
    {{"style": "bullet", "head": "[Hot take 2 — 5 words]", "sub": "[why it matters]", "in": 9.0, "out": 13.5}}
  ],

  "scene4_solution": "NEW TOOLS — 2-3 sentences on the freshest AI tools, models, or products. Be specific with names and numbers.",
  "keywords_scene4": ["software interface laptop", "technology product launch", "innovation startup"],
  "scene4_overlays": [
    {{"lines": "*NEW TOOLS|THIS WEEK", "in": 0.5, "out": 3.5, "x": "(W-w)/2", "y": "80"}},
    {{"style": "bullet", "head": "[Tool 1 name]", "sub": "[what it does in 5 words]", "in": 4.0, "out": 8.5}},
    {{"style": "bullet", "head": "[Tool 2 name]", "sub": "[what it does in 5 words]", "in": 9.0, "out": 13.5}}
  ],

  "scene5_ask": "ON THE HORIZON — 2 sentences on what to watch next week. End with: This has been your AI Weekly. Same time next Monday.",
  "keywords_scene5": ["future technology horizon", "innovation roadmap", "next generation tech"],

  "tagline": "This has been your AI Weekly. Same time next Monday.",
  "rolling_credits": [
    {{"header": "AI Weekly"}},
    {{"lines": ["Produced by Doug Morse", "dmpgh.com"]}}
  ]
}}

Replace ALL bracketed placeholders with real content from the news stories above. Return ONLY valid JSON."""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())

def run_pipeline(script_path):
    cmd = [
        "python3.12", str(KNOCKOFF_DIR / "fundraiser_generator.py"),
        "--org", "AI Weekly",
        "--cause", "weekly AI news briefing",
        "--url", "dmpgh.com",
        "--ask", "Subscribe for weekly AI news",
        "--script", str(script_path),
        "--music", str(KNOCKOFF_DIR / "music/news-headlines-loop.mp3"),
        "--final-music", str(KNOCKOFF_DIR / "music/news-flash.mp3"),
        "--tagline", "This has been your AI Weekly. Same time next Monday.",
        "--credit-tag", "AI WEEKLY",
        "--credit-sub", "Produced by Doug Morse — dmpgh.com",
        "--voice", "onyx",
        "--rolling-credits",
    ]
    result = subprocess.run(cmd, cwd=str(KNOCKOFF_DIR))
    return result.returncode == 0

def send_email(subject, body):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        env = {}
        gmail_env = Path.home() / ".env.gmail"
        if gmail_env.exists():
            for line in gmail_env.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        user = env.get("GMAIL_USER", "")
        pwd  = env.get("GMAIL_APP_PASSWORD", "")
        if not user or not pwd:
            print("Email skipped — no Gmail credentials")
            return
        msg = MIMEMultipart()
        msg["From"]    = f"AI Weekly <{user}>"
        msg["To"]      = user
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(user, user, msg.as_string())
        print(f"  ✉️  Email sent to {user}")
    except Exception as e:
        print(f"  ⚠️  Email failed: {e}")

def send_pushover(message):
    try:
        env = {}
        with open(Path.home() / ".env.pushover") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env[k] = v
        subprocess.run([
            "curl", "-s",
            "--form-string", f"token={env['PUSHOVER_APP_TOKEN']}",
            "--form-string", f"user={env['PUSHOVER_USER_KEY']}",
            "--form-string", f"message={message}",
            "https://api.pushover.net/1/messages.json"
        ], capture_output=True)
    except Exception as e:
        print(f"Pushover: {e}")

NAS_AI_WEEKLY_DIR = Path("/Volumes/web/ai_weekly")
YOUTUBE_TOKEN_FILE = Path.home() / ".youtube_token.json"
YOUTUBE_CLIENT_SECRETS = Path.home() / ".youtube_client_secrets.json"

def copy_to_nas(video_path):
    """Copy finished video to NAS /Volumes/web/ai_weekly/ for archival."""
    try:
        NAS_AI_WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
        dest = NAS_AI_WEEKLY_DIR / video_path.name
        shutil.copy2(video_path, dest)
        print(f"  📁 NAS copy: {dest}")
        return dest
    except Exception as e:
        print(f"  ⚠️  NAS copy failed: {e}")
        return None

def upload_to_youtube(video_path, title, description="", tags=None):
    """Upload video to YouTube. Requires ~/.youtube_client_secrets.json and one-time browser auth."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import pickle

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    token_file = Path.home() / ".youtube_token.pkl"

    creds = None
    if token_file.exists():
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not YOUTUBE_CLIENT_SECRETS.exists():
                print("  ⚠️  YouTube upload skipped — no client secrets file")
                print(f"      Create {YOUTUBE_CLIENT_SECRETS} with your OAuth2 credentials")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or ["AI", "artificial intelligence", "AI Weekly", "tech news"],
            "categoryId": "28",  # Science & Technology
        },
        "status": {"privacyStatus": "public"},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    print(f"  📺 Uploading to YouTube: {title}")
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  📺 Upload {int(status.progress() * 100)}%...")
    video_id = response["id"]
    print(f"  ✅ YouTube: https://youtu.be/{video_id}")
    return video_id

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"AI Weekly — {datetime.now().strftime('%A %B %d, %Y %I:%M %p')}")
    print(f"{'='*55}\n")

    print("Step 1: Fetching news + images...")
    stories = fetch_news()
    if not stories:
        print("No stories — aborting")
        send_pushover("AI Weekly: No stories fetched")
        exit(1)

    print(f"\nStep 2: Writing script with Claude ({len(stories)} stories)...")
    script = write_script(stories)

    slug = f"ai_weekly_{datetime.now().strftime('%Y-%m-%d_%H%M')}"
    script_path = SCRIPTS_DIR / f"{slug}.json"
    with open(script_path, "w") as f:
        json.dump(script, f, indent=2)
    print(f"Script saved: {script_path.name}")
    print(f"Hook: {script.get('scene1_hook','')[:80]}...")

    # Pre-build scene broll from news images
    # Group stories by section: scene2=news, scene3=views, scene4=tools
    print("\nStep 3: Building news image b-roll...")
    dated_slug = datetime.now().strftime("%Y%m%d")
    # Find the job dir that will be created (matches AI_Weekly_YYYYMMDD-HHMMSS)
    # We'll build broll clips and the pipeline will reuse them
    import time; time.sleep(1)  # ensure unique timestamp

    print("\nStep 4: Rendering video...")
    success = run_pipeline(script_path)

    # Find the output video
    vids = sorted(
        Path.home().glob("Documents/Fundraiser Videos/AI_Weekly_*.mp4"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if vids and success:
        latest = vids[0]
        print(f"\n✅ Done: {latest.name} ({latest.stat().st_size//1024//1024}MB)")
        subprocess.Popen(["open", str(latest)])

        # Copy to NAS for archival
        print("\nStep 5: Copying to NAS...")
        copy_to_nas(latest)

        # Upload to YouTube
        print("\nStep 6: Uploading to YouTube...")
        week_of = datetime.now().strftime("%B %d, %Y")
        hook = script.get("scene1_hook", "")[:120]
        yt_id = upload_to_youtube(
            latest,
            title=f"AI Weekly — {week_of}",
            description=f"{hook}\n\nYour weekly AI news briefing.\n\nProduced by Doug Morse — dmpgh.com",
            tags=["AI", "artificial intelligence", "AI Weekly", "tech news", "LLM", "machine learning"],
        )
        if yt_id:
            yt_url = f"https://youtu.be/{yt_id}"
            send_pushover(f"AI Weekly live: {yt_url}")
            send_email(
                subject=f"AI Weekly is live — {datetime.now().strftime('%B %d, %Y')}",
                body=f"This week's AI Weekly just published to YouTube.\n\n{yt_url}\n\n{script.get('scene1_hook','')}\n\n— AI Weekly"
            )
        else:
            send_pushover("AI Weekly ready (YouTube upload skipped)")
    else:
        print("\n❌ Render failed")
        send_pushover("AI Weekly render FAILED")
