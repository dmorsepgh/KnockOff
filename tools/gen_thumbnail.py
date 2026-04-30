#!/usr/bin/env python3
"""
YouTube Thumbnail Generator — follows proven CTR formulas.

Rules:
- Big face on the right (1/3 of frame)
- 2-3 words max, huge bold text on the left
- High contrast: bright text on dark background
- Curiosity gap — intrigue, don't answer
- 1280x720 output (YouTube standard)

Usage:
    python tools/gen_thumbnail.py "CLAUDE LEAKED"
    python tools/gen_thumbnail.py "AI KILLED ART" --face avatars/doug-photo.jpg
    python tools/gen_thumbnail.py "CLAUDE LEAKED" --color red
    python tools/gen_thumbnail.py "CLAUDE LEAKED" --episode 4
"""

import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_FACE = PROJECT_ROOT / "avatars" / "doug-photo.jpg"
OUTPUT_DIR = PROJECT_ROOT / "thumbnails"
OUTPUT_DIR.mkdir(exist_ok=True)

# YouTube thumbnail size
WIDTH = 1280
HEIGHT = 720

# Font
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

# Color presets — all high contrast, attention-grabbing
COLORS = {
    "red":    {"bg": (15, 15, 15), "text": (255, 50, 50),  "stroke": (0, 0, 0), "accent": (255, 80, 80)},
    "yellow": {"bg": (15, 15, 15), "text": (255, 230, 0),  "stroke": (0, 0, 0), "accent": (255, 200, 0)},
    "cyan":   {"bg": (15, 15, 15), "text": (0, 212, 255),  "stroke": (0, 0, 0), "accent": (0, 180, 220)},
    "orange": {"bg": (15, 15, 15), "text": (255, 160, 0),  "stroke": (0, 0, 0), "accent": (255, 130, 0)},
    "green":  {"bg": (15, 15, 15), "text": (0, 255, 100),  "stroke": (0, 0, 0), "accent": (0, 220, 80)},
    "white":  {"bg": (15, 15, 15), "text": (255, 255, 255),"stroke": (0, 0, 0), "accent": (200, 200, 200)},
}


def remove_background(img):
    """Simple background removal — makes edges blend better on dark bg."""
    try:
        from rembg import remove
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        result = remove(buf.read())
        return Image.open(io.BytesIO(result)).convert("RGBA")
    except ImportError:
        return img.convert("RGBA")


def draw_text_with_stroke(draw, position, text, font, fill, stroke_fill, stroke_width=4):
    """Draw text with thick outline for readability."""
    x, y = position
    # Draw stroke
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    # Draw main text
    draw.text(position, text, font=font, fill=fill)


def generate_thumbnail(hook_text, face_path=None, color_name="yellow", output_path=None, subtitle=None):
    """Generate a YouTube thumbnail following CTR best practices."""

    if face_path is None:
        face_path = DEFAULT_FACE
    face_path = Path(face_path)

    colors = COLORS.get(color_name, COLORS["yellow"])

    # Create dark background with subtle gradient
    img = Image.new("RGB", (WIDTH, HEIGHT), colors["bg"])
    draw = ImageDraw.Draw(img)

    # Add subtle radial gradient (darker edges, slightly lighter center-left)
    for x in range(WIDTH):
        for y in range(0, HEIGHT, 4):  # Skip rows for speed
            dist = ((x - WIDTH * 0.3) ** 2 + (y - HEIGHT * 0.5) ** 2) ** 0.5
            factor = max(0, min(1, 1 - dist / (WIDTH * 0.8)))
            brightness = int(15 + factor * 20)
            for dy in range(min(4, HEIGHT - y)):
                img.putpixel((x, y + dy), (brightness, brightness, brightness + 5))

    draw = ImageDraw.Draw(img)

    # Add accent bar on the left edge
    accent_width = 8
    for y in range(HEIGHT):
        for x in range(accent_width):
            img.putpixel((x, y), colors["accent"])

    # Load and place face on the right side
    if face_path.exists():
        face = Image.open(face_path)

        # Remove background for cleaner composite
        face = remove_background(face)

        # Scale face to fill right 40% of frame, full height
        face_width = int(WIDTH * 0.4)
        face_height = HEIGHT
        face_ratio = face.width / face.height
        target_ratio = face_width / face_height

        if face_ratio > target_ratio:
            new_h = face_height
            new_w = int(new_h * face_ratio)
        else:
            new_w = face_width
            new_h = int(new_w / face_ratio)

        face = face.resize((new_w, new_h), Image.LANCZOS)

        # Crop to target area
        left = (new_w - face_width) // 2
        top = (new_h - face_height) // 2
        face = face.crop((left, top, left + face_width, top + face_height))

        # Paste on right side
        face_x = WIDTH - face_width
        if face.mode == "RGBA":
            img.paste(face, (face_x, 0), face)
        else:
            img.paste(face, (face_x, 0))

        draw = ImageDraw.Draw(img)

    # Draw the hook text — BIG, left side
    words = hook_text.upper().split()

    # Calculate font size — fill the left 55% of the frame
    text_area_width = int(WIDTH * 0.55)
    text_area_height = int(HEIGHT * 0.7)

    # Find the right font size
    font_size = 120
    while font_size > 40:
        font = ImageFont.truetype(FONT_PATH, font_size)
        # Wrap text to fit
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > text_area_width:
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        # Check total height
        line_height = font_size * 1.15
        total_height = line_height * len(lines)
        if total_height <= text_area_height:
            break
        font_size -= 5

    font = ImageFont.truetype(FONT_PATH, font_size)
    line_height = font_size * 1.15

    # Center text vertically on the left side
    total_text_height = line_height * len(lines)
    start_y = (HEIGHT - total_text_height) / 2

    for i, line in enumerate(lines):
        x = 30  # Left margin
        y = start_y + i * line_height
        draw_text_with_stroke(draw, (x, y), line, font, colors["text"], colors["stroke"], stroke_width=5)

    # Subtitle (smaller text below main hook)
    if subtitle:
        sub_font = ImageFont.truetype(FONT_PATH, 32)
        sub_y = start_y + total_text_height + 20
        draw_text_with_stroke(draw, (30, sub_y), subtitle.upper(), sub_font,
                              colors["accent"], colors["stroke"], stroke_width=3)

    # Save
    if output_path is None:
        safe_name = hook_text.lower().replace(" ", "-").replace("'", "")[:30]
        output_path = OUTPUT_DIR / f"thumb-{safe_name}.jpg"

    img = img.convert("RGB")
    img.save(str(output_path), "JPEG", quality=95)
    print(f"Thumbnail saved: {output_path}")
    print(f"  Size: {WIDTH}x{HEIGHT}")
    print(f"  Hook: {hook_text.upper()}")
    print(f"  Color: {color_name}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail")
    parser.add_argument("hook", help="2-3 word hook text (e.g., 'CLAUDE LEAKED')")
    parser.add_argument("--face", default=str(DEFAULT_FACE), help="Path to face photo")
    parser.add_argument("--color", default="yellow", choices=COLORS.keys(), help="Color scheme")
    parser.add_argument("--subtitle", help="Optional smaller subtitle text")
    parser.add_argument("--output", "-o", help="Output path")
    parser.add_argument("--episode", "-e", type=int, help="Episode number (auto-names output)")
    parser.add_argument("--variants", action="store_true", help="Generate all color variants for A/B testing")

    args = parser.parse_args()

    if args.episode:
        output = OUTPUT_DIR / f"ep{args.episode}-thumbnail.jpg"
    else:
        output = Path(args.output) if args.output else None

    if args.variants:
        # Generate one in each color for A/B testing
        print("Generating all color variants for A/B testing:\n")
        for color in COLORS:
            variant_output = OUTPUT_DIR / f"thumb-{color}-{args.hook.lower().replace(' ', '-')[:20]}.jpg"
            generate_thumbnail(args.hook, args.face, color, variant_output, args.subtitle)
        print(f"\n{len(COLORS)} variants saved to {OUTPUT_DIR}/")
    else:
        generate_thumbnail(args.hook, args.face, args.color, output, args.subtitle)


if __name__ == "__main__":
    main()
