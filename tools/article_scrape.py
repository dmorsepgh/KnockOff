#!/usr/bin/env python3
"""
Article metadata scraper — pulls visual + text info for a news URL.

For each article URL, fetches:
  - og:image   (the hero image — most important)
  - og:video   (if there's a video)
  - og:description
  - og:site_name (source name, clean)
  - published_time (if available)
  - word_count (rough)

Used by the story ranker to boost stories that have media.

Usage:
    python3 tools/article_scrape.py --url https://www.example.com/article
    python3 tools/article_scrape.py --urls-file urls.txt
    python3 tools/article_scrape.py --episode 35   # scrapes metadata for all stories in an episode

Caching: results cached to show/epN/media/metadata.json so repeated runs don't re-fetch.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).parent.parent
SHOW_DIR = PROJECT_ROOT / "show"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve(base_url, rel):
    """Resolve a possibly-relative image URL against the page URL."""
    if not rel:
        return ""
    if rel.startswith("http"):
        return rel
    if rel.startswith("//"):
        return "https:" + rel
    parsed = urlparse(base_url)
    if rel.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{rel}"
    return f"{parsed.scheme}://{parsed.netloc}/{rel}"


def _meta(soup, name=None, prop=None):
    """Read a meta tag value."""
    if prop:
        t = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
    else:
        t = soup.find("meta", {"name": name})
    return (t.get("content") if t else "") or ""


def scrape_article(url, timeout=15):
    """Return metadata dict for a single article URL."""
    out = {
        "url": url,
        "title": "",
        "description": "",
        "image": "",
        "video": "",
        "site_name": "",
        "published": "",
        "word_count": 0,
        "has_image": False,
        "has_video": False,
        "fetch_ok": False,
        "fetch_error": "",
    }

    # Skip Google News aggregation redirects that won't give us the real URL easily
    # (they still have og:image via /articles/CBMi... but let's try anyway)
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        out["url"] = resp.url  # may have redirected
    except Exception as e:
        out["fetch_error"] = str(e)[:200]
        return out

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        soup = BeautifulSoup(resp.text, "html.parser")

    # Open Graph first (most reliable)
    og_title = _meta(soup, prop="og:title")
    og_desc = _meta(soup, prop="og:description")
    og_image = _meta(soup, prop="og:image:secure_url") or _meta(soup, prop="og:image")
    og_video = _meta(soup, prop="og:video:secure_url") or _meta(soup, prop="og:video")
    og_site = _meta(soup, prop="og:site_name")
    og_published = (
        _meta(soup, prop="article:published_time")
        or _meta(soup, prop="og:updated_time")
    )

    # Twitter Card fallbacks
    if not og_image:
        og_image = _meta(soup, name="twitter:image")
    if not og_title:
        og_title = _meta(soup, name="twitter:title")
    if not og_desc:
        og_desc = _meta(soup, name="twitter:description")

    # HTML <title> fallback
    if not og_title:
        t = soup.find("title")
        og_title = t.get_text().strip() if t else ""

    # Meta description fallback
    if not og_desc:
        og_desc = _meta(soup, name="description")

    # Largest <img> fallback if no og:image
    if not og_image:
        imgs = soup.find_all("img")
        candidates = []
        for img in imgs:
            src = img.get("src") or img.get("data-src") or ""
            if not src or src.startswith("data:"):
                continue
            w = img.get("width", "")
            h = img.get("height", "")
            try:
                area = int(w) * int(h) if w and h else 0
            except (ValueError, TypeError):
                area = 0
            candidates.append((area, src))
        if candidates:
            candidates.sort(reverse=True)
            og_image = candidates[0][1]

    # Word count of article body (for "substance" ranking)
    article_body = soup.find("article") or soup.find("main") or soup
    text = article_body.get_text(" ", strip=True) if article_body else ""
    word_count = len(text.split())

    out["title"] = og_title.strip()
    out["description"] = og_desc.strip()[:300]
    out["image"] = _resolve(out["url"], og_image.strip()) if og_image else ""
    out["video"] = _resolve(out["url"], og_video.strip()) if og_video else ""
    out["site_name"] = og_site.strip()
    out["published"] = og_published.strip()
    out["word_count"] = word_count
    out["has_image"] = bool(out["image"])
    out["has_video"] = bool(out["video"])
    out["fetch_ok"] = True

    return out


def download_image(url, out_path, timeout=15):
    """Download an image URL to a local file."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, stream=True)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ⚠ image download failed: {e}")
        return False


def score_story(meta, rank_bonus=0):
    """
    Media-availability score (higher = better).

    - 40 pts: has og:image
    - 20 pts: has og:video (extra)
    - 10 pts: has description
    - up to 20 pts: substantial article body (word_count / 50, capped)
    - rank_bonus: arbitrary offset (e.g. Ollama's content-interest score)
    """
    score = 0
    if meta.get("has_image"):
        score += 40
    if meta.get("has_video"):
        score += 20
    if meta.get("description"):
        score += 10
    words = meta.get("word_count", 0) or 0
    score += min(words // 50, 20)
    return score + rank_bonus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="Single URL to scrape")
    ap.add_argument("--urls-file", help="File with one URL per line")
    ap.add_argument("--episode", "-e", type=int, help="Episode number — scrape all its stories")
    ap.add_argument("--download-images", action="store_true",
                    help="Also download the og:images locally")
    args = ap.parse_args()

    urls = []
    ep_dir = None
    ep_data = None

    if args.url:
        urls = [args.url]
    elif args.urls_file:
        urls = [u.strip() for u in Path(args.urls_file).read_text().splitlines() if u.strip()]
    elif args.episode is not None:
        ep_dir = SHOW_DIR / f"ep{args.episode}"
        ep_json = ep_dir / "episode.json"
        if not ep_json.exists():
            print(f"Episode not found: {ep_json}")
            sys.exit(1)
        ep_data = json.loads(ep_json.read_text())
        urls = [s["link"] for s in ep_data.get("stories", []) if s.get("link")]
        if not urls:
            print(f"No story URLs in {ep_json}")
            sys.exit(1)
    else:
        ap.print_help()
        sys.exit(1)

    results = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url[:80]}")
        meta = scrape_article(url)
        meta["score"] = score_story(meta)
        flags = []
        if meta["has_image"]:
            flags.append("📷")
        if meta["has_video"]:
            flags.append("🎬")
        if not meta["fetch_ok"]:
            flags.append("❌")
        print(f"    {''.join(flags) or '(no media)'} score={meta['score']}  {meta['title'][:80]}")
        if meta["has_image"]:
            print(f"    image: {meta['image'][:100]}")
        results.append(meta)
        time.sleep(0.5)

    # Save to episode folder if we're scraping an episode
    if ep_dir:
        media_dir = ep_dir / "media"
        media_dir.mkdir(exist_ok=True)
        (media_dir / "metadata.json").write_text(json.dumps(results, indent=2))
        print(f"\n💾 Saved metadata → {media_dir}/metadata.json")

        if args.download_images:
            for i, meta in enumerate(results, 1):
                if meta.get("has_image"):
                    ext = ".jpg"  # will work for most; ffmpeg handles anyway
                    img_url = meta["image"].lower()
                    for e in (".jpg", ".jpeg", ".png", ".webp"):
                        if e in img_url:
                            ext = e if e != ".jpeg" else ".jpg"
                            break
                    out = media_dir / f"story{i}{ext}"
                    if download_image(meta["image"], out):
                        print(f"   ⬇ story{i}{ext}")
                        meta["local_image"] = str(out)
            # Re-save with local paths
            (media_dir / "metadata.json").write_text(json.dumps(results, indent=2))
    else:
        # Print as JSON for CLI use
        print("\n" + json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
