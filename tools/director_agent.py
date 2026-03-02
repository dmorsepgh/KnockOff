#!/usr/bin/env python3
"""
Director Agent - Plans video production with optimal 60-second structure.

Takes a script and creates a production plan:
- [0-20s] Avatar intro (lip sync chunk 1)
- [20-40s] B-roll middle (continuous voiceover, no lip sync)
- [40-60s] Avatar outro (lip sync chunk 2)

Continuous audio runs underneath entire 60 seconds.
Only 40s of lip syncing needed (avoids chunk boundary issues).
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BROLL_DIR = PROJECT_ROOT / "broll"
OVERLAY_DIR = PROJECT_ROOT / "overlays"

# Speech rate for timing calculations
WORDS_PER_MINUTE = 150  # Average conversational pace
WORDS_PER_SECOND = WORDS_PER_MINUTE / 60

# Target structure
INTRO_DURATION = 20.0  # seconds
MIDDLE_DURATION = 20.0  # seconds
OUTRO_DURATION = 20.0  # seconds
TOTAL_DURATION = 60.0  # seconds

class ProductionPlan:
    def __init__(self):
        self.intro_text = ""
        self.middle_text = ""
        self.outro_text = ""
        self.intro_duration = 0.0
        self.middle_duration = 0.0
        self.outro_duration = 0.0
        self.broll_needed = []
        self.overlays_needed = []
        self.warnings = []

def estimate_speech_duration(text: str) -> float:
    """Estimate how long text will take to speak."""
    words = len(text.split())
    return words / WORDS_PER_SECOND

def split_script_into_segments(script_text: str, auto_trim: bool = False) -> Tuple[str, str, str]:
    """
    Split script into intro, middle, outro segments.

    Strategy:
    - First ~20s worth of words → intro (avatar)
    - Middle ~20s worth of words → middle (B-roll)
    - Last ~20s worth of words → outro (avatar)

    If auto_trim is True and script is long, trim to fit 60s format.
    """

    # Clean script - remove markers and metadata
    lines = script_text.split('\n')
    clean_lines = []

    skip_section = False
    for line in lines:
        # Skip metadata sections
        if line.startswith('**') or line.startswith('#') or line.startswith('---'):
            skip_section = True
            continue

        if skip_section and line.strip() == '':
            skip_section = False
            continue

        if skip_section:
            continue

        # Skip markers
        if re.match(r'\[(?:BROLL|OVERLAY|CTA|MUSIC):', line.strip(), re.IGNORECASE):
            continue

        # Keep actual script text
        if line.strip():
            clean_lines.append(line.strip())

    full_text = ' '.join(clean_lines)
    words = full_text.split()
    total_words = len(words)

    # Calculate word splits for 20s segments
    words_per_segment = int(WORDS_PER_SECOND * 20)
    target_total_words = int(WORDS_PER_SECOND * 60)  # ~150 words for 60s

    # If script is too long and auto_trim is enabled, trim it
    if auto_trim and total_words > target_total_words:
        words = words[:target_total_words]

    # Distribute words evenly across three segments
    segment_size = len(words) // 3

    intro_words = words[:segment_size]
    middle_words = words[segment_size:segment_size*2]
    outro_words = words[segment_size*2:]

    intro_text = ' '.join(intro_words)
    middle_text = ' '.join(middle_words)
    outro_text = ' '.join(outro_words)

    return intro_text, middle_text, outro_text

def analyze_script(script_path: Path, auto_trim: bool = False) -> ProductionPlan:
    """Analyze script and create production plan."""

    plan = ProductionPlan()

    if not script_path.exists():
        plan.warnings.append(f"Script file not found: {script_path}")
        return plan

    script_text = script_path.read_text()

    # Split into segments
    intro_text, middle_text, outro_text = split_script_into_segments(script_text, auto_trim=auto_trim)

    plan.intro_text = intro_text
    plan.middle_text = middle_text
    plan.outro_text = outro_text

    # Calculate durations
    plan.intro_duration = estimate_speech_duration(intro_text)
    plan.middle_duration = estimate_speech_duration(middle_text)
    plan.outro_duration = estimate_speech_duration(outro_text)

    # Check if timing is reasonable
    total_duration = plan.intro_duration + plan.middle_duration + plan.outro_duration

    if total_duration < 50:
        plan.warnings.append(f"Script is short ({total_duration:.1f}s) - consider adding more content")
    elif total_duration > 70:
        plan.warnings.append(f"Script is long ({total_duration:.1f}s) - may need to trim")

    # Extract B-roll and overlay needs from original script
    broll_pattern = r'\[BROLL:\s*([^\|\]]+)'
    overlay_pattern = r'\[OVERLAY:\s*([^\|\]]+)'

    for match in re.finditer(broll_pattern, script_text, re.IGNORECASE):
        filename = match.group(1).strip()
        plan.broll_needed.append(filename)

    for match in re.finditer(overlay_pattern, script_text, re.IGNORECASE):
        filename = match.group(1).strip()
        plan.overlays_needed.append(filename)

    return plan

def generate_production_script(plan: ProductionPlan, original_script_path: Path) -> str:
    """Generate production-ready script with timing markers."""

    script = f"""# Production Plan - {original_script_path.stem}

**Generated:** {datetime.now().strftime('%Y-%m-%d %I:%M %p')}
**Total Duration:** ~60 seconds
**Structure:** Avatar Intro (20s) → B-roll Middle (20s) → Avatar Outro (20s)

---

## Timing Breakdown

- **Intro:** {plan.intro_duration:.1f}s (Target: 20s) - Avatar with lip sync
- **Middle:** {plan.middle_duration:.1f}s (Target: 20s) - B-roll with voiceover
- **Outro:** {plan.outro_duration:.1f}s (Target: 20s) - Avatar with lip sync
- **Total:** {plan.intro_duration + plan.middle_duration + plan.outro_duration:.1f}s

---

## Production Structure

### [0-20s] INTRO - Avatar (Lip Sync Chunk 1)

{plan.intro_text}

**Shot:** Avatar talking directly to camera
**Audio:** Lip-synced to avatar video

---

### [20-40s] MIDDLE - B-roll (Continuous Voiceover)

{plan.middle_text}

**Shot:** B-roll footage, screen recordings, or text overlays
**Audio:** Continuous voiceover (NO lip sync needed)

**B-roll Needed:**
"""

    if plan.broll_needed:
        for broll in plan.broll_needed:
            script += f"- [ ] {broll}\n"
    else:
        script += f"- [ ] Screen recording or demo → `broll/demo-{datetime.now().strftime('%Y%m%d')}.mp4`\n"
        script += f"- [ ] Text overlay with key points → `overlays/text-{datetime.now().strftime('%Y%m%d')}.png`\n"

    script += """
---

### [40-60s] OUTRO - Avatar (Lip Sync Chunk 2)

"""

    script += plan.outro_text

    script += """

**Shot:** Avatar talking directly to camera
**Audio:** Lip-synced to avatar video

[CTA: Follow for more | Daily AI tips at dmpgh.com]

---

## Audio Production Notes

**IMPORTANT:** Generate ONE continuous 60-second audio file with TTS.
- Audio runs continuously underneath entire video
- Intro section [0-20s] → lip sync to avatar
- Middle section [20-40s] → play over B-roll (no lip sync)
- Outro section [40-60s] → lip sync to avatar

Only the intro and outro portions need lip syncing (40s total).
Middle 20s is pure voiceover - much faster to process!

---

## Pre-Production Checklist

- [ ] Avatar base video recorded (5-10s minimum) → `avatars/[name].mp4`
"""

    if plan.broll_needed:
        for broll in plan.broll_needed:
            script += f"- [ ] B-roll captured → `broll/{broll}`\n"
    else:
        script += "- [ ] B-roll footage captured\n"

    if plan.overlays_needed:
        for overlay in plan.overlays_needed:
            script += f"- [ ] Overlay created → `overlays/{overlay}`\n"

    script += """
---

## Generation Commands

**1. Pre-flight Check:**
```bash
python tools/preflight_check.py -s scripts/[script-name].md -a [avatar-name]
```

**2. Generate Video:**
```bash
python tools/generate_avatar_video.py -s scripts/[script-name].md -a [avatar-name] -f portrait
```

---

## Warnings
"""

    if plan.warnings:
        for warning in plan.warnings:
            script += f"- ⚠️  {warning}\n"
    else:
        script += "- ✅ No warnings - script timing looks good\n"

    return script

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Director Agent - Plan video production")
    parser.add_argument("--script", "-s", type=Path, required=True, help="Path to script file")
    parser.add_argument("--output", "-o", type=Path, help="Output path for production plan")
    parser.add_argument("--auto-trim", "-t", action="store_true", help="Automatically trim long scripts to 60s")

    args = parser.parse_args()

    print("=" * 80)
    print("DIRECTOR AGENT - PRODUCTION PLANNING")
    print("=" * 80)

    print(f"\n📄 Analyzing script: {args.script.name}")

    if args.auto_trim:
        print("   Auto-trim enabled: Will trim long scripts to 60s")

    # Analyze script
    plan = analyze_script(args.script, auto_trim=args.auto_trim)

    # Show timing breakdown
    print(f"\n⏱️  Timing Analysis:")
    print(f"   Intro:  {plan.intro_duration:.1f}s (Target: 20s)")
    print(f"   Middle: {plan.middle_duration:.1f}s (Target: 20s)")
    print(f"   Outro:  {plan.outro_duration:.1f}s (Target: 20s)")
    print(f"   Total:  {plan.intro_duration + plan.middle_duration + plan.outro_duration:.1f}s")

    # Show warnings
    if plan.warnings:
        print(f"\n⚠️  Warnings:")
        for warning in plan.warnings:
            print(f"   - {warning}")

    # Generate production script
    production_script = generate_production_script(plan, args.script)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = args.script.parent / f"{args.script.stem}-PRODUCTION.md"

    # Save production plan
    output_path.write_text(production_script)

    print(f"\n✅ Production plan saved: {output_path}")

    # Show next steps
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("\n1. Review production plan and timing")
    print("2. Capture any needed B-roll footage")
    print("3. Run pre-flight check:")
    print(f"   python tools/preflight_check.py -s {output_path} -a [avatar-name]")
    print("4. Generate video:")
    print(f"   python tools/generate_avatar_video.py -s {output_path} -a [avatar-name] -f portrait")
    print()

if __name__ == "__main__":
    main()
