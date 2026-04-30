#!/usr/bin/env python3
"""
Quick Video Generator - One command, full video.

Pick a host, pick a guest, describe a funny scenario, get a video.

Usage:
    python tools/quick_video.py --host rachel-maddow --guest sean-hannity \
        --scenario "The White House has banned all coffee and Congress is losing its mind"

    python tools/quick_video.py --list-cast

    # Interactive mode
    python tools/quick_video.py
"""

import argparse
import json
import subprocess
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
OUTPUT_DIR = PROJECT_ROOT / "output" / "keepers" / "newsdesk"

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"quick_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Full cast roster
CAST = {
    "anderson-cooper":   {"name": "Anderson Cooper",   "network": "CNN",        "voice": "cooper", "style": "calm, dry wit, tries to maintain order"},
    "jake-tapper":       {"name": "Jake Tapper",       "network": "CNN",        "voice": "kusal",  "style": "sardonic, asks pointed questions"},
    "rachel-maddow":     {"name": "Rachel Maddow",     "network": "MSNBC",      "voice": "lessac", "style": "long-winded explainer, loves historical context, goes on tangents"},
    "mika-brzezinski":   {"name": "Mika Brzezinski",   "network": "MSNBC",      "voice": "amy",    "style": "disapproving, exasperated, says people's names in a scolding tone"},
    "joe-scarborough":   {"name": "Joe Scarborough",   "network": "MSNBC",      "voice": "ryan",   "style": "folksy, starts stories with 'back when I was in Congress'"},
    "lawrence-odonnell": {"name": "Lawrence O'Donnell", "network": "MSNBC",      "voice": "arctic", "style": "intense, dramatic pauses, treats everything as gravely serious"},
    "jonathan-capehart": {"name": "Jonathan Capehart",  "network": "MSNBC",      "voice": "danny",  "style": "polished DC insider, deadpan delivery"},
    "eugene-daniels":    {"name": "Eugene Daniels",     "network": "MSNBC",      "voice": "ryan",   "style": "young field correspondent energy, slightly bewildered"},
    "sean-hannity":      {"name": "Sean Hannity",       "network": "Fox News",   "voice": "joe",    "style": "outraged, defensive, conspiracy-minded, demands his lawyer"},
    "tucker-carlson":    {"name": "Tucker Carlson",     "network": "Fox News",   "voice": "arctic", "style": "asks rhetorical questions, contrarian, 'I'm just asking questions'"},
    "laura-ingraham":    {"name": "Laura Ingraham",     "network": "Fox News",   "voice": "amy",    "style": "sharp, dismissive, quick comebacks"},
    "bill-oreilly":      {"name": "Bill O'Reilly",      "network": "Fox News",   "voice": "ryan",   "style": "bombastic, 'the spin stops here', old-school bluster"},
    "lester-holt":       {"name": "Lester Holt",        "network": "NBC",        "voice": "joe",    "style": "gravitas, maintains dignity, dry humor"},
    "stephen-a-smith":   {"name": "Stephen A. Smith",   "network": "ESPN",       "voice": "danny",  "style": "loud, emphatic, confused about why he's covering news, sports metaphors"},
    "leland-vittert":    {"name": "Leland Vittert",     "network": "NewsNation", "voice": "kusal",  "style": "straight man, nobody has strong opinions about him"},
    "chris-cuomo":       {"name": "Chris Cuomo",        "network": "NewsNation", "voice": "ryan",   "style": "combative, 'let me tell you something', references his past career"},
}


def list_cast():
    """Print available cast members."""
    print("\nKNOCKOFF NEWS — Available Cast\n")
    print(f"{'Avatar':<22} {'Name':<22} {'Network':<12} {'Voice':<8} {'Style'}")
    print("-" * 100)
    for avatar, info in CAST.items():
        print(f"{avatar:<22} {info['name']:<22} {info['network']:<12} {info['voice']:<8} {info['style'][:40]}")
    print()


def generate_script(host_id: str, guest_id: str, scenario: str) -> str:
    """Use local LLM (ollama) to generate a comedy script."""
    host = CAST[host_id]
    guest = CAST[guest_id]

    prompt = f"""Write a satirical news segment script for KNOCKOFF NEWS, a comedy show that parodies cable news.

FORMAT RULES (follow exactly):
- Two speakers: HOST and GUEST
- First two lines MUST be the header declarations exactly like this:
HOST (avatar: {host_id}, voice: {host['voice']}):
GUEST (avatar: {guest_id}, voice: {guest['voice']}):
- After headers, alternate between HOST: and GUEST: with dialogue
- Each speaker's dialogue is plain text, 1-3 sentences per turn
- Aim for 12-18 exchanges total (about 2-3 minutes when spoken)
- NO stage directions, NO parentheticals, NO action descriptions
- Just the speaker label and their words

CHARACTERS:
- HOST is {host['name']} ({host['network']}). Style: {host['style']}
- GUEST is {guest['name']} ({guest['network']}). Style: {guest['style']}

COMEDY RULES:
- Deadpan delivery — absurd content stated as serious news
- Each character stays in their personality
- Humor escalates through the segment
- Include callback jokes and running gags
- End with a strong punchline or absurd button
- Both characters should be funny, not just one

THE SCENARIO:
{scenario}

Write the complete script now. Start with the two header lines, then the dialogue."""

    logger.info("Generating script with ollama (llama3.1:8b)...")
    start = time.time()

    result = subprocess.run(
        ["ollama", "run", "llama3.1:8b"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        logger.error(f"Ollama failed: {result.stderr}")
        raise RuntimeError("Script generation failed")

    raw = result.stdout.strip()
    elapsed = time.time() - start
    logger.info(f"Script generated in {elapsed:.1f}s")

    # Clean up: ensure proper header format
    script = clean_script(raw, host_id, guest_id, host, guest)
    return script


def clean_script(raw: str, host_id: str, guest_id: str, host: dict, guest: dict) -> str:
    """Clean up LLM output to ensure valid news_desk format."""
    lines = raw.strip().split('\n')
    cleaned = []

    # Ensure headers are first
    header1 = f"HOST (avatar: {host_id}, voice: {host['voice']}):"
    header2 = f"GUEST (avatar: {guest_id}, voice: {guest['voice']}):"

    cleaned.append(header1)
    cleaned.append(header2)
    cleaned.append("")

    in_dialogue = False
    for line in lines:
        stripped = line.strip()
        # Skip any LLM-generated headers (we added our own)
        if stripped.startswith("HOST (avatar:") or stripped.startswith("GUEST (avatar:"):
            in_dialogue = True
            continue
        # Skip markdown formatting
        if stripped.startswith("```") or stripped.startswith("#"):
            continue
        # Pass through dialogue lines
        if stripped.startswith("HOST:") or stripped.startswith("GUEST:"):
            in_dialogue = True
            cleaned.append("")
            cleaned.append(stripped)
            continue
        # Pass through continuation text
        if in_dialogue and stripped:
            cleaned.append(stripped)
        elif not stripped:
            cleaned.append("")

    return "\n".join(cleaned)


def run_interactive():
    """Interactive mode — prompt user for inputs."""
    print("\n" + "=" * 50)
    print("  KNOCKOFF NEWS — Quick Video Generator")
    print("=" * 50)

    list_cast()

    host_id = input("Host avatar (e.g. anderson-cooper): ").strip()
    if host_id not in CAST:
        print(f"Unknown cast member: {host_id}")
        return

    guest_id = input("Guest avatar (e.g. sean-hannity): ").strip()
    if guest_id not in CAST:
        print(f"Unknown cast member: {guest_id}")
        return

    print("\nDescribe the funny scenario (a paragraph):")
    scenario = input("> ").strip()
    if not scenario:
        print("No scenario provided.")
        return

    generate_video(host_id, guest_id, scenario)


def generate_video(host_id: str, guest_id: str, scenario: str):
    """Full pipeline: scenario → script → video."""
    total_start = time.time()

    host = CAST[host_id]
    guest = CAST[guest_id]

    logger.info(f"{'=' * 60}")
    logger.info(f"KNOCKOFF NEWS — Quick Video")
    logger.info(f"Host:     {host['name']} ({host_id})")
    logger.info(f"Guest:    {guest['name']} ({guest_id})")
    logger.info(f"Scenario: {scenario[:80]}...")
    logger.info(f"{'=' * 60}")

    # Step 1: Generate script
    script = generate_script(host_id, guest_id, scenario)

    # Save script
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_scenario = "".join(c if c.isalnum() or c in " -_" else "" for c in scenario[:40]).strip().replace(" ", "_")
    script_path = SCRIPTS_DIR / f"quick_{safe_scenario}_{timestamp}.md"
    script_path.write_text(script)
    logger.info(f"Script saved: {script_path.name}")
    logger.info(f"Script preview:\n{script[:500]}")

    # Step 2: Render video
    logger.info("Rendering video...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"quick_{safe_scenario}_{timestamp}.mp4"

    cmd = [
        sys.executable, str(PROJECT_ROOT / "tools" / "news_desk.py"),
        "--script", str(script_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error(f"Render failed: {result.stderr[-500:]}")
        logger.error(f"stdout: {result.stdout[-500:]}")
        print(f"\nRender failed. Script saved at: {script_path}")
        print("You can fix the script and render manually with:")
        print(f"  python tools/news_desk.py --script {script_path}")
        return

    # Find the output file (news_desk saves to .tmp)
    import glob
    outputs = sorted(
        glob.glob(str(PROJECT_ROOT / ".tmp" / "avatar" / "output" / "newsdesk_*.mp4")),
        key=lambda x: Path(x).stat().st_mtime,
        reverse=True
    )
    if outputs:
        latest = Path(outputs[0])
        import shutil
        shutil.copy2(str(latest), str(output_path))
        logger.info(f"Video saved: {output_path}")

        # Open it
        subprocess.run(["open", str(output_path)])

    total_elapsed = time.time() - total_start

    logger.info(f"\n{'=' * 60}")
    logger.info(f"COMPLETE")
    logger.info(f"Script:   {script_path.name}")
    logger.info(f"Video:    {output_path.name}")
    logger.info(f"Total:    {total_elapsed / 60:.1f} minutes")
    logger.info(f"{'=' * 60}")

    print(f"\nScript: {script_path}")
    print(f"Video:  {output_path}")
    print(f"Total:  {total_elapsed / 60:.1f} minutes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KnockOff News Quick Video Generator")
    parser.add_argument("--host", help="Host avatar name (e.g. anderson-cooper)")
    parser.add_argument("--guest", help="Guest avatar name (e.g. sean-hannity)")
    parser.add_argument("--scenario", help="Funny scenario description (a paragraph)")
    parser.add_argument("--list-cast", action="store_true", help="Show available cast members")
    args = parser.parse_args()

    if args.list_cast:
        list_cast()
    elif args.host and args.guest and args.scenario:
        if args.host not in CAST:
            print(f"Unknown host: {args.host}. Use --list-cast to see options.")
            sys.exit(1)
        if args.guest not in CAST:
            print(f"Unknown guest: {args.guest}. Use --list-cast to see options.")
            sys.exit(1)
        generate_video(args.host, args.guest, args.scenario)
    else:
        run_interactive()
