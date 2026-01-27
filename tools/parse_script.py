#!/usr/bin/env python3
"""
Script Parser - Parse markdown scripts with B-roll and overlay markers.

Supports:
- Plain text for speech segments
- [BROLL: filename.mp4 | duration] - Full cut to video
- [OVERLAY: filename.png | duration] - Image/video over avatar (corner PIP)
- [CTA: Main Text | Subtext] - Text overlay on avatar
- [MUSIC: filename.mp3 | volume] - Background music track
- Markdown formatting is stripped from speech text

Example script:
    Welcome to today's video.

    [OVERLAY: product-screens.png | 10s]

    As you can see, the interface is clean.

    [BROLL: demo.mp4 | 5s]

    Thanks for watching!

    [CTA: Subscribe | Links in description]
    [MUSIC: upbeat.mp3 | -12db]
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Segment:
    """Represents a segment in the script."""
    type: str  # "speech", "broll", "overlay", "cta"
    content: str  # Text for speech, filename for broll/overlay, main text for cta
    duration: Optional[float] = None  # Duration in seconds (for broll/overlay)
    options: dict = field(default_factory=dict)  # Extra options (subtext, volume, etc)

    def __repr__(self):
        if self.type == "speech":
            preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
            return f"Speech({preview!r})"
        elif self.type == "broll":
            dur = f", {self.duration}s" if self.duration else ""
            return f"BRoll({self.content!r}{dur})"
        elif self.type == "overlay":
            dur = f", {self.duration}s" if self.duration else ""
            return f"Overlay({self.content!r}{dur})"
        elif self.type == "cta":
            sub = self.options.get("subtext", "")
            return f"CTA({self.content!r}, {sub!r})"
        return f"Segment({self.type}, {self.content!r})"


@dataclass
class MusicTrack:
    """Background music configuration."""
    filename: str
    volume: str = "-12dB"  # Default volume


# Regex patterns for markers
BROLL_PATTERN = re.compile(
    r'\[B-?ROLL:\s*([^\]|]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)
OVERLAY_PATTERN = re.compile(
    r'\[OVERLAY:\s*([^\]|]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)
CTA_PATTERN = re.compile(
    r'\[CTA:\s*([^\]|]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)
MUSIC_PATTERN = re.compile(
    r'\[MUSIC:\s*([^\]|]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)

# Combined pattern for splitting (all marker types)
ALL_MARKERS_PATTERN = re.compile(
    r'(\[(?:B-?ROLL|OVERLAY|CTA|MUSIC):[^\]]+\])',
    re.IGNORECASE
)


def parse_duration(duration_str: Optional[str]) -> Optional[float]:
    """Parse duration string like '5s', '10s', '2.5s' into seconds."""
    if not duration_str:
        return None
    duration_str = duration_str.strip().lower()
    if duration_str.endswith('s'):
        try:
            return float(duration_str[:-1])
        except ValueError:
            return None
    try:
        return float(duration_str)
    except ValueError:
        return None


def parse_volume(volume_str: Optional[str]) -> str:
    """Parse volume string, default to -12dB."""
    if not volume_str:
        return "-12dB"
    volume_str = volume_str.strip()
    # Remove existing dB suffix (case insensitive) and re-add properly
    if volume_str.lower().endswith('db'):
        volume_str = volume_str[:-2]
    # Ensure it has proper dB suffix (uppercase B for ffmpeg)
    return f"{volume_str}dB"


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text, keeping plain speech."""
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
    # Remove links, keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove code blocks
    text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove bullet points
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove numbered lists
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_script(script_text: str) -> tuple[list[Segment], Optional[MusicTrack]]:
    """
    Parse a script with B-roll, overlay, and CTA markers into segments.

    Args:
        script_text: Raw script content (may include markdown)

    Returns:
        Tuple of (list of Segment objects in order, optional MusicTrack)
    """
    segments = []
    music_track = None

    # First, extract music marker (global, not a segment)
    music_match = MUSIC_PATTERN.search(script_text)
    if music_match:
        filename = music_match.group(1).strip()
        volume = parse_volume(music_match.group(2))
        music_track = MusicTrack(filename=filename, volume=volume)
        # Remove music marker from script
        script_text = MUSIC_PATTERN.sub('', script_text)

    # Split by all markers while keeping the markers
    parts = ALL_MARKERS_PATTERN.split(script_text)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check if this part is a marker
        broll_match = BROLL_PATTERN.match(part)
        overlay_match = OVERLAY_PATTERN.match(part)
        cta_match = CTA_PATTERN.match(part)

        if broll_match:
            filename = broll_match.group(1).strip()
            duration = parse_duration(broll_match.group(2))
            segments.append(Segment(
                type="broll",
                content=filename,
                duration=duration
            ))
        elif overlay_match:
            filename = overlay_match.group(1).strip()
            duration = parse_duration(overlay_match.group(2))
            segments.append(Segment(
                type="overlay",
                content=filename,
                duration=duration
            ))
        elif cta_match:
            main_text = cta_match.group(1).strip()
            subtext = cta_match.group(2).strip() if cta_match.group(2) else ""
            segments.append(Segment(
                type="cta",
                content=main_text,
                options={"subtext": subtext}
            ))
        else:
            # Regular text (speech segment)
            text = strip_markdown(part).strip()
            if text:
                segments.append(Segment(type="speech", content=text))

    return segments, music_track


def get_full_speech_text(segments: list[Segment]) -> str:
    """Extract all speech text concatenated for TTS."""
    speech_parts = [s.content for s in segments if s.type == "speech"]
    return " ".join(speech_parts)


def parse_script_file(path: Path) -> tuple[list[Segment], Optional[MusicTrack]]:
    """Parse a script file."""
    return parse_script(path.read_text())


def has_visual_markers(script_text: str) -> bool:
    """Check if script has any visual markers (BROLL, OVERLAY, CTA)."""
    upper = script_text.upper()
    return any(marker in upper for marker in ["[B-ROLL:", "[BROLL:", "[OVERLAY:", "[CTA:"])


if __name__ == "__main__":
    # Test with sample script including new markers
    sample = """
# Welcome Video

Hello and welcome to today's video about our new product.

[OVERLAY: product-screens.png | 10s]

As you can see on screen, the interface is **clean** and simple.
Let me walk you through the key features.

[BROLL: demo-footage.mp4 | 5s]

The dashboard gives you a complete overview of your data.

[CTA: Subscribe Now | Links in description]

Thanks for watching! Head to dmpgh.com for more.

[MUSIC: upbeat.mp3 | -10dB]
"""

    print("Parsing sample script...\n")
    segments, music = parse_script(sample)

    for i, seg in enumerate(segments):
        print(f"{i+1}. {seg}")

    if music:
        print(f"\nMusic: {music.filename} at {music.volume}")

    print(f"\nFull speech text:\n{get_full_speech_text(segments)}")
