#!/usr/bin/env python3
"""
AI News Collector — Pulls daily AI headlines from RSS feeds,
summarizes them via Ollama, and saves to a curated list.

Usage:
    python3 tools/news_collector.py              # Collect today's news
    python3 tools/news_collector.py --list       # Show collected stories
    python3 tools/news_collector.py --week       # Show this week's stories
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

NEWS_DIR = Path(__file__).parent.parent / "news"
NEWS_DIR.mkdir(exist_ok=True)

RSS_FEEDS = {
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Ars Technica AI": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
}

OLLAMA_URL = "http://localhost:11434/api/generate"


def fetch_feed(name, url):
    """Fetch and parse an RSS feed."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        root = ET.fromstring(data)

        articles = []
        # Handle both RSS and Atom formats
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            desc = item.findtext("description", "").strip()[:500]
            if title:
                articles.append({
                    "source": name,
                    "title": title,
                    "link": link,
                    "date": pub_date,
                    "description": desc
                })

        # Atom format
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub_date = entry.findtext("atom:published", "", ns).strip()
            desc = entry.findtext("atom:summary", "", ns).strip()[:500]
            if title:
                articles.append({
                    "source": name,
                    "title": title,
                    "link": link,
                    "date": pub_date,
                    "description": desc
                })

        return articles[:10]  # Top 10 per source
    except Exception as e:
        print(f"  Error fetching {name}: {e}")
        return []


def summarize_with_ollama(article):
    """Use Ollama to create a brief summary for show use."""
    prompt = f"""Summarize this AI news article in 2-3 sentences for a news show segment.
Keep it conversational and interesting.

Title: {article['title']}
Source: {article['source']}
Description: {article['description']}

Summary:"""

    try:
        data = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False
        }).encode()

        req = urllib.request.Request(
            OLLAMA_URL,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result.get("response", "").strip()
    except Exception as e:
        return f"Summary unavailable: {e}"


def filter_ai_articles(articles):
    """Filter articles that are actually about AI."""
    ai_keywords = [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "chatgpt", "claude", "openai", "anthropic", "google ai", "gemini",
        "llm", "language model", "neural", "gpt", "copilot", "midjourney",
        "stable diffusion", "generative", "transformer", "nvidia", "gpu",
        "robot", "automation", "deepfake", "synthetic"
    ]
    filtered = []
    for a in articles:
        text = (a["title"] + " " + a["description"]).lower()
        if any(kw in text for kw in ai_keywords):
            filtered.append(a)
    return filtered


def collect_news():
    """Main collection routine."""
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = NEWS_DIR / f"news-{today}.json"

    print(f"Collecting AI news for {today}...")
    all_articles = []

    for name, url in RSS_FEEDS.items():
        print(f"  Fetching {name}...")
        articles = fetch_feed(name, url)
        print(f"    Found {len(articles)} articles")
        all_articles.extend(articles)

    # Filter for AI-relevant
    ai_articles = filter_ai_articles(all_articles)
    print(f"\n{len(ai_articles)} AI-relevant articles from {len(all_articles)} total")

    # Remove duplicates by title
    seen = set()
    unique = []
    for a in ai_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    ai_articles = unique
    print(f"{len(ai_articles)} unique articles")

    # Summarize top stories with Ollama
    print("\nSummarizing with Ollama...")
    for i, article in enumerate(ai_articles[:15]):  # Top 15
        print(f"  [{i+1}/{min(len(ai_articles), 15)}] {article['title'][:60]}...")
        article["summary"] = summarize_with_ollama(article)
        article["collected"] = today

    # Save
    with open(output_file, "w") as f:
        json.dump(ai_articles[:15], f, indent=2)

    print(f"\nSaved {len(ai_articles[:15])} stories to {output_file}")
    return ai_articles[:15]


def list_stories(days=1):
    """List collected stories."""
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        filepath = NEWS_DIR / f"news-{date}.json"
        if filepath.exists():
            with open(filepath) as f:
                stories = json.load(f)
            print(f"\n{'='*60}")
            print(f"  {date} — {len(stories)} stories")
            print(f"{'='*60}")
            for j, s in enumerate(stories, 1):
                print(f"\n  #{j} [{s['source']}]")
                print(f"  {s['title']}")
                if s.get("summary"):
                    print(f"  Summary: {s['summary']}")
                print(f"  Link: {s['link']}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_stories(1)
    elif "--week" in sys.argv:
        list_stories(7)
    else:
        collect_news()
