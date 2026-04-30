#!/usr/bin/env python3.12
"""
Fundraiser Video Generator — Local pipeline, zero per-unit cost.

Pipeline:
  1. Ollama writes script using the proven nonprofit formula
  2. Pexels API pulls b-roll footage matching each scene
  3. Piper TTS narrates the script
  4. ffmpeg assembles slideshow + narration + music
  5. Output: ready-to-deliver fundraiser video

Usage:
  python3.12 fundraiser_generator.py --org "National MS Society" --cause "multiple sclerosis research" \\
    --url "nationalmssociety.org/donate" --ask "\\$19 a month"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/Users/douglasmorse/.keys/.env")
except ImportError:
    pass

import requests
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent
OUT_DIR = PROJECT_ROOT / "fundraisers"
OUT_DIR.mkdir(exist_ok=True)

# User-facing output folder (findable in Finder)
USER_OUT_DIR = Path.home() / "Documents" / "Fundraiser Videos"
USER_OUT_DIR.mkdir(parents=True, exist_ok=True)

PEXELS_KEY = os.environ.get("PEXELS_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
PIPER_VOICE = PROJECT_ROOT / "models" / "piper" / "en_US-ryan-medium.onnx"

def _load_env_key(path, key):
    try:
        for line in open(Path(path).expanduser()):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    except FileNotFoundError:
        pass
    return ""

ELEVENLABS_API_KEY = _load_env_key("~/.keys/.env", "ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "nPczCjzI2devNBz1zQrb"  # Brian — Deep, Resonant, American

# TTS selection: "elevenlabs" (best quality), "openai", or "piper" (free, robotic)
TTS_ENGINE = "openai"
OPENAI_VOICE = "nova"  # Warm female American voice — best for fundraiser emotional tone


def make_qr_badge(url, out_path, size=220):
    """Generate a circular QR code badge (white circle background + QR in the middle)."""
    # Step 1: generate raw QR as PNG
    raw_qr = out_path.with_suffix(".raw.png")
    subprocess.run(
        ["qrencode", "-o", str(raw_qr), "-s", "8", "-m", "2", "--type=PNG",
         "--background=FFFFFF", "--foreground=0F3460", url],
        capture_output=True, check=True,
    )
    # Step 2: use ffmpeg to build a circular badge:
    #   - white circle background with brand-color outer ring
    #   - QR code centered inside
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=white@1.0:s={size}x{size}:d=1",
        "-i", str(raw_qr),
        "-filter_complex",
        # Create circular mask on the background
        f"[0:v]format=rgba,geq='r=255:g=255:b=255:a=if(lte(hypot(X-{size/2},Y-{size/2}),{size/2-4}),255,0)'[bg];"
        f"[1:v]scale={int(size*0.75)}:{int(size*0.75)}[qr];"
        f"[bg][qr]overlay=(W-w)/2:(H-h)/2:format=auto",
        "-frames:v", "1",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"QR badge failed: {result.stderr[-300:]}")
    raw_qr.unlink()


# ---------- Graphics package: PIL-generated asset builders ----------
# These build the lower-third components once per job so ffmpeg can just overlay
# pre-baked PNGs — cleaner than trying to draw rounded rects / stacked text with
# drawbox/drawtext filters.

def _hex_to_rgb(hex_str):
    """Parse '0xRRGGBB' / '#RRGGBB' / 'RRGGBB' into (r,g,b)."""
    s = hex_str.lstrip("#")
    if s.lower().startswith("0x"):
        s = s[2:]
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _rounded_rect_image(size, radius, fill, border=None, border_w=0):
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill)
    if border and border_w:
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius,
                               outline=border, width=border_w)
    return img


def make_logo_plate(logo_path, out_path, brand_color_hex, target_logo_h=100):
    """Tight white rounded-corner plate with the sponsor logo inside + brand-orange border.
    Used on both the scene lower-third banner (right side) and the final card (top-left).

    The source logo is auto-cropped to its actual artwork bbox first — this is
    critical because Open Graph-sized logos (e.g. the NMS 1200x630 PNG) have a lot
    of built-in whitespace the designer added for social sharing margins, and
    scaling the raw image produces a fat plate with dead space around the mark.
    """
    from PIL import ImageChops
    logo = Image.open(logo_path).convert("RGBA")

    # Auto-crop the logo's whitespace. Diff against pure white (RGB space),
    # slightly amplify so near-white pixels are ignored, then use getbbox().
    rgb = logo.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg)
    diff_enh = ImageChops.add(diff, diff, 2.0, -5)
    bbox = diff_enh.getbbox()
    if bbox:
        logo = logo.crop(bbox)

    ratio = logo.width / logo.height
    lw = int(target_logo_h * ratio)
    logo_scaled = logo.resize((lw, target_logo_h), Image.LANCZOS)

    # Option A padding: moderate, approved 2026-04-11
    pad_x, pad_y = 8, 6
    plate_w = lw + pad_x * 2
    plate_h = target_logo_h + pad_y * 2
    br = _hex_to_rgb(brand_color_hex) + (255,)
    plate = _rounded_rect_image((plate_w, plate_h), radius=14,
                                fill=(255, 255, 255, 255),
                                border=br, border_w=4)
    plate.paste(logo_scaled, (pad_x, pad_y), logo_scaled)
    plate.save(out_path, "PNG")
    return out_path


def make_qr_card(url, out_path, brand_color_hex, size=140):
    """White rounded-corner card with an orange 'SCAN TO GIVE' header + QR code.
    Replaces the old circular make_qr_badge in the branded lower-third package.
    """
    tmp_qr = Path(out_path).with_suffix(".rawqr.png")
    subprocess.run(
        ["qrencode", "-o", str(tmp_qr), "-s", "8", "-m", "2", "--type=PNG",
         "--background=FFFFFF", "--foreground=141E32", url],
        capture_output=True, check=True,
    )
    raw = Image.open(tmp_qr).convert("RGBA")

    br = _hex_to_rgb(brand_color_hex) + (255,)
    card = _rounded_rect_image((size, size), radius=12,
                               fill=(255, 255, 255, 255),
                               border=br, border_w=3)
    draw = ImageDraw.Draw(card)

    # Orange "SCAN TO GIVE" header bar (30px tall)
    draw.rectangle((0, 0, size - 1, 30), fill=br)
    try:
        header_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 16)
    except Exception:
        header_font = ImageFont.load_default()
    header = "SCAN TO GIVE"
    hb = draw.textbbox((0, 0), header, font=header_font)
    hw = hb[2] - hb[0]
    draw.text(((size - hw) / 2 - hb[0], 5),
              header, font=header_font, fill=(255, 255, 255, 255))

    # QR pasted below the header, scaled to fit
    qr_area = size - 30 - 12  # header + 6px top+bottom padding
    qr_scaled = raw.resize((qr_area, qr_area), Image.LANCZOS)
    qr_x = (size - qr_area) // 2
    qr_y = 36
    card.paste(qr_scaled, (qr_x, qr_y), qr_scaled)

    card.save(out_path, "PNG")
    tmp_qr.unlink(missing_ok=True)
    return out_path


def make_banner_bg(out_path, brand_color_hex, width=1860, height=155, radius=22,
                   all_corners=True):
    """Transparent PNG of the lower-third banner background. Semi-transparent dark
    navy fill, brand-color accent stripe along the top edge. Rounded corners:
      all_corners=True  → true floating pill, all 4 corners rounded (default — banner
                          floats with clearance above the frame bottom)
      all_corners=False → top corners only, flat bottom edge (legacy — banner
                          flush to the frame bottom edge)
    """
    from PIL import ImageChops
    br = _hex_to_rgb(brand_color_hex) + (255,)
    fill = (20, 30, 50, 235)  # dark navy at 92%

    if all_corners:
        banner = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bd = ImageDraw.Draw(banner)
        bd.rounded_rectangle((0, 0, width - 1, height - 1),
                             radius=radius, fill=fill)
    else:
        # Top-only rounding: taller rounded rect, crop off the bottom rounding
        tall = Image.new("RGBA", (width, height + radius), (0, 0, 0, 0))
        td = ImageDraw.Draw(tall)
        td.rounded_rectangle((0, 0, width - 1, height + radius - 1),
                             radius=radius, fill=fill)
        banner = tall.crop((0, 0, width, height))

    # Accent stripe (4px) along the top, clipped to the banner's alpha shape
    stripe = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripe)
    sd.rectangle((0, 0, width - 1, 4), fill=br)
    banner_alpha = banner.split()[3]
    stripe_alpha = stripe.split()[3]
    combined = ImageChops.multiply(stripe_alpha, banner_alpha)
    stripe.putalpha(combined)
    banner = Image.alpha_composite(banner, stripe)

    banner.save(out_path, "PNG")
    return out_path


def make_scene_overlay(out_path, brand_color_hex, lines_spec):
    """Build a stacked two-tone text overlay PNG for in-frame dead-space callouts.

    lines_spec is a pipe-separated string where each segment is one line.
    A leading '*' on a segment means "render this line in brand color" instead
    of white. Font is Impact (bold broadcast display), drop-shadowed on all lines.

    Examples:
      "MULTIPLE|*SCLEROSIS"       → white "MULTIPLE" / orange "SCLEROSIS"
      "IT ATTACKS|*THE BRAIN"     → white "IT ATTACKS" / orange "THE BRAIN"
      "*3X MORE|LIKELY IN|WOMEN"  → orange "3X MORE" / white "LIKELY IN" / white "WOMEN"

    Per-line font size is auto-picked: brand-color lines get the bigger size
    (140pt) and white lines get 100pt, producing the pledge-drive feel from
    the reference commercials.
    """
    FONT = "/System/Library/Fonts/Supplemental/Impact.ttf"
    try:
        big_font = ImageFont.truetype(FONT, 140)
        med_font = ImageFont.truetype(FONT, 100)
    except Exception:
        big_font = med_font = ImageFont.load_default()

    br = _hex_to_rgb(brand_color_hex) + (255,)
    white = (255, 255, 255, 255)
    shadow = (0, 0, 0, 220)

    # Parse lines_spec — pipe separated, '*' prefix means brand color
    parts = []
    for seg in str(lines_spec).split("|"):
        seg = seg.strip()
        if not seg:
            continue
        if seg.startswith("*"):
            parts.append((seg[1:].strip(), big_font, br))
        else:
            parts.append((seg, med_font, white))

    if not parts:
        raise ValueError("Empty overlay lines_spec")

    # Measure each line
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    bboxes = [td.textbbox((0, 0), t, font=f) for (t, f, _) in parts]
    widths = [b[2] - b[0] for b in bboxes]
    heights = [b[3] - b[1] for b in bboxes]

    line_gap = 20
    canvas_w = max(widths) + 40
    canvas_h = sum(heights) + line_gap * (len(parts) - 1) + 40
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    y = 0
    for (text, font, color), bbox, h in zip(parts, bboxes, heights):
        x = 0 - bbox[0]
        # Drop shadow
        d.text((x + 4, y + 4 - bbox[1]), text, font=font, fill=shadow)
        # Main text
        d.text((x, y - bbox[1]), text, font=font, fill=color)
        y += h + line_gap

    img.save(out_path, "PNG")
    return out_path


def make_scene_bullet(out_path, brand_color_hex, head, sub=""):
    """Two-line bullet: big brand-orange Impact headline + smaller white Arial Bold subtitle.
    Used for cascading bullet lists (scene 4 "MORE MORNINGS / without symptoms" etc).
    Tighter/smaller than make_scene_overlay — designed to stack 3 in a column.
    Auto-scales head font down so canvas never exceeds 1840px (fits in 1920 frame).
    """
    MAX_TEXT_W = 1840
    sub_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 42)

    # Auto-scale head font until it fits within MAX_TEXT_W
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    head_size = 110
    while head_size >= 40:
        head_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", head_size)
        hb = td.textbbox((0, 0), str(head), font=head_font)
        if hb[2] - hb[0] <= MAX_TEXT_W:
            break
        head_size -= 5

    hb = td.textbbox((0, 0), str(head), font=head_font)
    hw, hh = hb[2] - hb[0], hb[3] - hb[1]

    br = _hex_to_rgb(brand_color_hex) + (255,)
    white = (255, 255, 255, 255)
    shadow = (0, 0, 0, 220)

    sw, sh = 0, 0
    sb = None
    if sub:
        sb = td.textbbox((0, 0), str(sub), font=sub_font)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]

    canvas_w = max(hw, sw) + 40
    canvas_h = hh + (10 + sh if sub else 0) + 40
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Shadow + main headline
    d.text((4 - hb[0], 4 - hb[1]), str(head), font=head_font, fill=shadow)
    d.text((0 - hb[0], 0 - hb[1]), str(head), font=head_font, fill=br)

    if sub:
        sy = hh + 10
        d.text((4 - sb[0], sy + 4 - sb[1]), str(sub), font=sub_font, fill=shadow)
        d.text((0 - sb[0], sy - sb[1]), str(sub), font=sub_font, fill=white)

    img.save(out_path, "PNG")
    return out_path


def make_bumper_png(out_path, brand_color_hex, width=1920, height=1080):
    """Generate the 'Look Mom, No Hands Productions' closing bumper PNG.
    Stick figure child with arms raised and legs splayed (triumph pose), bold
    two-line production title below. Near-black background.
    """
    br = _hex_to_rgb(brand_color_hex) + (255,)
    white = (255, 255, 255, 255)
    bg = (10, 10, 15, 255)
    shadow = (0, 0, 0, 255)

    img = Image.new("RGBA", (width, height), bg)
    d = ImageDraw.Draw(img)

    # --- Stick figure ---
    cx = width // 2
    fig_top = 260
    stroke = 14

    # Head: filled white circle
    head_r = 55
    head_cy = fig_top + head_r
    d.ellipse((cx - head_r, fig_top, cx + head_r, fig_top + head_r * 2), fill=white)

    # Body
    body_top = fig_top + head_r * 2 + 5
    body_bottom = body_top + 190
    d.line((cx, body_top, cx, body_bottom), fill=white, width=stroke)

    # Arms raised UP and OUT (V above head)
    shoulder_y = body_top + 15
    hand_offset_x = 160
    hand_y = fig_top - 80
    d.line((cx, shoulder_y, cx - hand_offset_x, hand_y), fill=white, width=stroke)
    d.line((cx, shoulder_y, cx + hand_offset_x, hand_y), fill=white, width=stroke)
    # Hand dots
    hand_r = 14
    d.ellipse((cx - hand_offset_x - hand_r, hand_y - hand_r,
               cx - hand_offset_x + hand_r, hand_y + hand_r), fill=white)
    d.ellipse((cx + hand_offset_x - hand_r, hand_y - hand_r,
               cx + hand_offset_x + hand_r, hand_y + hand_r), fill=white)

    # Legs splayed
    foot_offset_x = 120
    foot_y = body_bottom + 130
    d.line((cx, body_bottom, cx - foot_offset_x, foot_y), fill=white, width=stroke)
    d.line((cx, body_bottom, cx + foot_offset_x, foot_y), fill=white, width=stroke)

    # --- Text ---
    FONT_IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    tag_font = ImageFont.truetype(FONT_IMPACT, 130)
    sub_font = ImageFont.truetype(FONT_BOLD, 62)

    tag = "LOOK MOM, NO HANDS"
    tb = d.textbbox((0, 0), tag, font=tag_font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tag_y = 800
    tag_x = (width - tw) // 2 - tb[0]
    d.text((tag_x + 5, tag_y + 5 - tb[1]), tag, font=tag_font, fill=shadow)
    d.text((tag_x, tag_y - tb[1]), tag, font=tag_font, fill=br)

    sub = "PRODUCTIONS"
    sb = d.textbbox((0, 0), sub, font=sub_font)
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    sub_y = tag_y + th + 30
    sub_x = (width - sw) // 2 - sb[0]
    d.text((sub_x + 3, sub_y + 3 - sb[1]), sub, font=sub_font, fill=shadow)
    d.text((sub_x, sub_y - sb[1]), sub, font=sub_font, fill=white)

    img.save(out_path, "PNG")
    return out_path


def make_rolling_credits_png(out_path, brand_color_hex, sections,
                              width=1920, line_height=68, section_gap=60,
                              header_gap=14, top_pad=80, bottom_pad=80):
    """Generate a tall PNG with movie-style rolling credits.

    `sections` is a list of dicts:
       [{"header": "PRODUCED BY", "lines": ["Doug Morse"]},
        {"header": "SCRIPT & DIRECTION BY", "lines": ["AI Claude", "Anthropic"]},
        ...]

    Header renders in brand-orange 52pt Arial Bold, lines render in white 64pt
    Arial, centered horizontally. Returns the PNG path; total height is
    returned via probing the saved image.

    The resulting PNG is designed to be scrolled from bottom to top of a 1920x1080
    frame via ffmpeg overlay with a time-based y expression.
    """
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
    header_font = ImageFont.truetype(FONT_BOLD, 44)
    line_font = ImageFont.truetype(FONT, 56)

    br = _hex_to_rgb(brand_color_hex) + (255,)
    white = (255, 255, 255, 255)

    # First pass: measure total height
    tmp = Image.new("RGBA", (1, 1))
    td = ImageDraw.Draw(tmp)
    total_h = top_pad
    for sec in sections:
        if sec.get("header"):
            hb = td.textbbox((0, 0), sec["header"], font=header_font)
            total_h += (hb[3] - hb[1]) + header_gap
        for line in sec.get("lines", []):
            if line:
                lb = td.textbbox((0, 0), line, font=line_font)
                total_h += (lb[3] - lb[1]) + 12
            else:
                total_h += 36  # blank line spacer
        total_h += section_gap
    total_h += bottom_pad

    # Second pass: draw
    img = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = top_pad
    for sec in sections:
        if sec.get("header"):
            text = sec["header"]
            hb = d.textbbox((0, 0), text, font=header_font)
            tw = hb[2] - hb[0]
            x = (width - tw) // 2 - hb[0]
            d.text((x, y - hb[1]), text, font=header_font, fill=br)
            y += (hb[3] - hb[1]) + header_gap
        for line in sec.get("lines", []):
            if line:
                lb = d.textbbox((0, 0), line, font=line_font)
                tw = lb[2] - lb[0]
                x = (width - tw) // 2 - lb[0]
                d.text((x, y - lb[1]), line, font=line_font, fill=white)
                y += (lb[3] - lb[1]) + 12
            else:
                y += 36
        y += section_gap

    img.save(out_path, "PNG")
    return out_path, total_h


def make_ask_overlay(out_path, brand_color_hex, amount_text="$19",
                     top_text="JUST", bottom_text="A MONTH"):
    """Large three-line stacked two-tone ask overlay for scene 5.
       JUST      (white, Impact 90)
       $19       (brand orange, Impact 220 — massive)
       A MONTH   (white, Impact 90)
    Returned PNG has a transparent background and drop-shadow on each line.
    """
    FONT = "/System/Library/Fonts/Supplemental/Impact.ttf"
    try:
        top_font = ImageFont.truetype(FONT, 90)
        amount_font = ImageFont.truetype(FONT, 220)
        bot_font = ImageFont.truetype(FONT, 90)
    except Exception:
        top_font = amount_font = bot_font = ImageFont.load_default()

    br = _hex_to_rgb(brand_color_hex) + (255,)
    white = (255, 255, 255, 255)
    shadow = (0, 0, 0, 200)

    # Measure each line
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    tb = td.textbbox((0, 0), top_text, font=top_font)
    ab = td.textbbox((0, 0), amount_text, font=amount_font)
    bb = td.textbbox((0, 0), bottom_text, font=bot_font)

    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    aw, ah = ab[2] - ab[0], ab[3] - ab[1]
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]

    canvas_w = max(tw, aw, bw) + 40
    canvas_h = th + ah + bh + 50 + 20  # gaps between lines + shadow room
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def draw_shadowed(xy, text, font, color):
        x, y = xy
        d.text((x + 4, y + 4), text, font=font, fill=shadow)
        d.text((x, y), text, font=font, fill=color)

    y = 0
    # Line 1: "JUST" — left-aligned at x=0
    draw_shadowed((0 - tb[0], y - tb[1]), top_text, top_font, white)
    y += th + 10
    # Line 2: "$19" — left-aligned at x=0
    draw_shadowed((0 - ab[0], y - ab[1]), amount_text, amount_font, br)
    y += ah + 10
    # Line 3: "A MONTH" — left-aligned at x=0
    draw_shadowed((0 - bb[0], y - bb[1]), bottom_text, bot_font, white)

    img.save(out_path, "PNG")
    return out_path


# ---------- STEP 1: SCRIPT ----------

FORMULA_PROMPT = """You are writing a 60-second fundraising video script for {org}.
The cause is: {cause}.
The donation ask is: {ask}.
The donation URL is: {url}.

Follow this PROVEN 5-part structure EXACTLY:

SCENE 1 — HOOK (8 seconds, ~20 words):
Put the viewer in an emotional moment. Use conditional scene OR first-person vulnerability OR a stakes-declaring statement.
Examples: "What would you do if..." / "When I hear those three letters..." / "Every four seconds..."

SCENE 2 — THE PROBLEM (12 seconds, ~30 words):
State what's wrong. Include ONE specific statistic. Make it urgent and specific.

SCENE 3 — THE STAKES (15 seconds, ~38 words):
Who suffers and how. Use concrete imagery — describe a person, a moment, a fear. Not abstract.

SCENE 4 — THE SOLUTION (15 seconds, ~38 words):
What {org} does. Research. Support. Action. Direct and specific — no corporate-speak.

SCENE 5 — THE ASK (10 seconds, ~25 words):
Direct call to action. Specific amount. Specific URL. Emotional closer.
Format: "Become a [Partner/Champion/Member] for as little as {ask}. Visit {url}. [One-sentence emotional close]."

RULES:
- Short sentences. Fragments are OK.
- Use "you" directly. Use "they" for those affected.
- Emotional trigger words: hope, alone, help, save, fear, together, right now
- NO corporate language. NO "our foundation" or "our mission statement."
- Every sentence should be something a human would say out loud naturally.

Return your response as VALID JSON with this exact structure (and nothing else):
{{
  "scene1_hook": "...",
  "scene2_problem": "...",
  "scene3_stakes": "...",
  "scene4_solution": "...",
  "scene5_ask": "...",
  "keywords_scene1": ["word1", "word2"],
  "keywords_scene2": ["word1", "word2"],
  "keywords_scene3": ["word1", "word2"],
  "keywords_scene4": ["word1", "word2"],
  "keywords_scene5": ["word1", "word2"]
}}

The keywords should be 2-3 words per scene that describe visual imagery for stock footage search (e.g. "hospital research", "family hope", "person wheelchair").
"""


def write_script(org, cause, ask, url):
    print("📝 Writing script with Ollama...")
    prompt = FORMULA_PROMPT.format(org=org, cause=cause, ask=ask, url=url)
    result = subprocess.run(
        ["ollama", "run", "mistral-small"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    raw = result.stdout.strip()
    # Extract JSON from response
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        raise RuntimeError(f"No JSON in Ollama response:\n{raw[:500]}")
    return json.loads(m.group(0))


# ---------- STEP 2: B-ROLL ----------

BROLL_FALLBACKS = [
    "people helping community",
    "hope sunrise nature",
    "hands together teamwork",
    "city street people walking",
    "volunteers working together",
]

def fetch_broll(keywords, scene_dir, count=2):
    """Pull vertical or landscape b-roll from Pexels. Falls back to generic terms if needed."""
    queries_to_try = [" ".join(keywords)] + BROLL_FALLBACKS
    url = f"https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_KEY}

    videos = []
    for query in queries_to_try:
        print(f"  🎬 Pexels search: '{query}'")
        params = {"query": query, "per_page": count, "orientation": "landscape", "size": "medium"}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"    ⚠️  Pexels {resp.status_code}")
            continue
        videos = resp.json().get("videos", [])
        if videos:
            break
        print(f"    ⚠️  No results — trying fallback...")
    paths = []
    for i, video in enumerate(videos):
        # Find a reasonable quality link
        files = video.get("video_files", [])
        hd = [f for f in files if f.get("quality") == "hd" and f.get("width", 0) <= 1920]
        sd = [f for f in files if f.get("quality") == "sd"]
        pick = hd[0] if hd else (sd[0] if sd else (files[0] if files else None))
        if not pick:
            continue
        link = pick.get("link")
        if not link:
            continue
        out = scene_dir / f"broll_{i}.mp4"
        print(f"    ⬇  downloading {link[:60]}...")
        for attempt in range(3):
            try:
                r = requests.get(link, stream=True, timeout=60)
                with open(out, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                paths.append(out)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"    ⚠️  download error (retry {attempt+1}): {e}")
                else:
                    print(f"    ⚠️  download failed after 3 attempts, skipping clip")
    return paths


def prebuild_broll(broll_files, duration, out_path, clip_max=5.0):
    """Concatenate multiple b-roll clips (each capped at clip_max seconds) into a
    single video long enough to cover `duration`. Cycles through clips if needed.
    Returns out_path on success, or None on failure (caller falls back to stream_loop)."""
    if not broll_files:
        return None

    import math

    # Probe each clip's actual duration
    clip_durations = []
    for f in broll_files:
        d = probe_duration(f)
        clip_durations.append(min(d, clip_max) if d and d > 0 else clip_max)

    # How many clip slots do we need to fill `duration`?
    total_available = sum(clip_durations)
    if total_available <= 0:
        return None

    # Build the ordered list of (file, trim_duration) — cycle if needed
    slots = []
    accumulated = 0.0
    idx = 0
    n = len(broll_files)
    while accumulated < duration + 0.5:
        f = broll_files[idx % n]
        d = clip_durations[idx % n]
        slots.append((f, d))
        accumulated += d
        idx += 1
        if idx > n * 10:  # safety cap — never more than 10x through the list
            break

    if len(slots) == 1:
        # Only one clip needed — just trim it, no concat required
        cmd = [
            "ffmpeg", "-y",
            "-t", str(slots[0][1]),
            "-i", str(slots[0][0]),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-an",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        return out_path if result.returncode == 0 else None

    # Multiple clips — trim each to a temp file, then concat
    tmp_dir = out_path.parent / "_broll_tmp"
    tmp_dir.mkdir(exist_ok=True)
    trimmed = []
    for i, (f, d) in enumerate(slots):
        tmp = tmp_dir / f"clip_{i}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-t", str(d),
            "-i", str(f),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-an",
            str(tmp),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode == 0:
            trimmed.append(tmp)

    if not trimmed:
        return None

    # Write concat list
    concat_txt = tmp_dir / "concat.txt"
    with open(concat_txt, "w") as fh:
        for t in trimmed:
            fh.write(f"file '{t.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c:v", "libx264", "-preset", "fast", "-an",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    # Clean up tmp clips
    import shutil as _shutil
    _shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_path if result.returncode == 0 else None


# ---------- STEP 3: VOICEOVER ----------

def narrate_scene(text, out_path):
    """Generate narration. Uses ElevenLabs, OpenAI TTS, or Piper."""
    if TTS_ENGINE == "elevenlabs" and ELEVENLABS_API_KEY:
        import urllib.request as _ur
        data = json.dumps({
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }).encode()
        req = _ur.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            data=data,
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        )
        with _ur.urlopen(req, timeout=60) as r:
            mp3_bytes = r.read()
        mp3_path = out_path.with_suffix(".mp3")
        mp3_path.write_bytes(mp3_bytes)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "48000", "-ac", "1", str(out_path)],
            capture_output=True, check=True,
        )
        return

    if TTS_ENGINE == "openai" and OPENAI_KEY:
        # OpenAI TTS — much more natural than Piper
        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1-hd",
                "voice": OPENAI_VOICE,
                "input": text,
                "response_format": "mp3",
                "speed": 0.95,  # Slightly slower for emotional delivery
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI TTS failed: {resp.status_code} {resp.text[:200]}")
        # Save as mp3, then convert to wav for consistent downstream handling
        mp3_path = out_path.with_suffix(".mp3")
        mp3_path.write_bytes(resp.content)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "48000", "-ac", "1", str(out_path)],
            capture_output=True, check=True,
        )
        return

    # Fallback: Piper (free, robotic)
    if not PIPER_VOICE.exists():
        raise FileNotFoundError(f"Piper voice not found: {PIPER_VOICE}")
    proc = subprocess.run(
        ["piper", "--model", str(PIPER_VOICE), "--output_file", str(out_path)],
        input=text,
        capture_output=True,
        text=True,
    )
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError(f"Piper TTS failed:\n{proc.stderr}")


# ---------- STEP 4: ASSEMBLE ----------

def assemble_scene_vertical(broll_files, narration_wav, out_path, duration,
                            banner_line1="", banner_line2="", banner_line3="",
                            banner_bg_v_path=None, logo_plate_v_path=None,
                            qr_card_v_path=None, brand_color="0xe94560",
                            ask_overlay_path=None, ask_stamp_at=2.5,
                            scene_overlays=None):
    """Build a single scene for VERTICAL 1080x1920 format — TikTok/Reels/Shorts.

    Path B portrait port of the branded package: 1020-wide all-corners-rounded
    floating banner lifted 25px from the frame bottom, smaller logo plate on the
    left, narrower QR card on the right, center-stacked contact text. Simpler
    than landscape — NO scene-specific overlays, NO scene-5 ask overlay —
    because short-form viewers don't read heavy text while scrolling.
    """
    if not broll_files:
        filter_in = ["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1080x1920:d={duration}:r=30"]
    else:
        filter_in = ["-stream_loop", "-1", "-i", str(broll_files[0])]

    FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

    # Vertical banner geometry:
    #   1020px × 200px (taller to accommodate 3 stacked text lines),
    #   30px side margins, 25px lift from frame bottom.
    BANNER_W = 1020
    BANNER_H = 200
    BANNER_LIFT = 25
    BANNER_X = 30
    BANNER_Y = 1920 - BANNER_H - BANNER_LIFT  # 1695

    inputs = list(filter_in)
    inputs.extend(["-i", str(narration_wav)])

    next_idx = 2
    banner_idx = None
    plate_idx = None
    qr_idx = None

    if banner_bg_v_path and Path(banner_bg_v_path).exists():
        inputs.extend(["-i", str(banner_bg_v_path)])
        banner_idx = next_idx
        next_idx += 1
    if logo_plate_v_path and Path(logo_plate_v_path).exists():
        inputs.extend(["-i", str(logo_plate_v_path)])
        plate_idx = next_idx
        next_idx += 1
    if qr_card_v_path and Path(qr_card_v_path).exists():
        inputs.extend(["-i", str(qr_card_v_path)])
        qr_idx = next_idx
        next_idx += 1

    # Ask overlay (scene 5) and timed scene overlays — both fade in/out with alpha
    ask_idx_v = None
    if ask_overlay_path and Path(ask_overlay_path).exists():
        inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(ask_overlay_path)])
        ask_idx_v = next_idx
        next_idx += 1

    scene_overlay_inputs_v = []
    if scene_overlays:
        for ov in scene_overlays:
            ov_path = ov.get("path")
            if ov_path and Path(ov_path).exists():
                inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(ov_path)])
                scene_overlay_inputs_v.append((next_idx, ov))
                next_idx += 1

    # B-roll scale+crop+grade
    main_chain = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30,"
        "eq=saturation=0.85:contrast=1.08"
    )

    chain_parts = [f"[0:v]{main_chain}[base0]"]
    current = "[base0]"
    label_n = 0

    def next_label():
        nonlocal label_n
        label_n += 1
        return f"[vv{label_n}]"

    # 1. Banner background PNG
    if banner_idx is not None:
        new = next_label()
        chain_parts.append(f"{current}[{banner_idx}:v]overlay=x={BANNER_X}:y={BANNER_Y}{new}")
        current = new

    # 2. Contact text — 3 stacked lines: org name / URL / phone
    # Logo plate (55px tall) renders ~280px wide. Text starts at BANNER_X+320.
    text_x = BANNER_X + 320 if plate_idx is not None else BANNER_X + 30
    drawtext_parts = []
    # Line 1: ORG NAME (34pt bold white) at banner_y + 42
    if banner_line1:
        safe1 = banner_line1.replace("'", "").replace(":", "").replace("\\", "")
        drawtext_parts.append(
            f"drawtext=fontfile='{FONT_BOLD}':text='{safe1}':fontcolor=white:fontsize=34:"
            f"x={text_x}:y={BANNER_Y + 42}"
        )
    # Line 2: URL (24pt regular light gray) at banner_y + 94
    if banner_line2:
        safe2 = banner_line2.replace("'", "").replace(":", "").replace("\\", "")
        drawtext_parts.append(
            f"drawtext=fontfile='{FONT}':text='{safe2}':fontcolor=0xdcdcdc:fontsize=24:"
            f"x={text_x}:y={BANNER_Y + 94}"
        )
    # Line 3: Phone (24pt regular light gray) at banner_y + 138
    if banner_line3:
        safe3 = banner_line3.replace("'", "").replace(":", "").replace("\\", "")
        drawtext_parts.append(
            f"drawtext=fontfile='{FONT}':text='{safe3}':fontcolor=0xdcdcdc:fontsize=24:"
            f"x={text_x}:y={BANNER_Y + 138}"
        )
    if drawtext_parts:
        new = next_label()
        chain_parts.append(f"{current}" + ",".join(drawtext_parts) + new)
        current = new

    # 3. Logo plate on left (55px logo + padding → ~67 tall, centered in 200px banner)
    if plate_idx is not None:
        plate_x = BANNER_X + 15
        plate_y = BANNER_Y + (BANNER_H - 67) // 2 + 2
        new = next_label()
        chain_parts.append(
            f"{current}[{plate_idx}:v]overlay=x={plate_x}:y={plate_y}{new}"
        )
        current = new

    # 4. QR card on right (140x140 in the taller 200px banner gives more breathing room)
    if qr_idx is not None:
        qr_size = 140
        qr_x = BANNER_X + BANNER_W - qr_size - 15
        qr_y = BANNER_Y + (BANNER_H - qr_size) // 2 + 2
        scale_label = f"[qrvscale]"
        chain_parts.append(f"[{qr_idx}:v]scale={qr_size}:{qr_size}{scale_label}")
        new = next_label()
        chain_parts.append(f"{current}{scale_label}overlay=x={qr_x}:y={qr_y}{new}")
        current = new

    # 5. Scene-5-only ask overlay (vertical): center horizontally, upper-middle
    # The PNG is ~900x500 — too wide for 1080 frame. Scale it to 900 wide max.
    if ask_idx_v is not None:
        chain_parts.append(
            f"[{ask_idx_v}:v]format=rgba,"
            f"scale='min(900,iw)':-1,"
            f"fade=t=in:st={ask_stamp_at}:d=1.0:alpha=1[askfadev]"
        )
        new = next_label()
        # Center horizontally, position in upper-middle of frame (y=400)
        chain_parts.append(
            f"{current}[askfadev]overlay=x=(W-w)/2:y=400:eof_action=pass{new}"
        )
        current = new

    # 6. Timed scene overlays (vertical): center-stacked over the top of the frame.
    # IGNORE the landscape x/y in the spec — override to center horizontally with
    # auto-stacked y coordinates. First overlay goes at y=300, each subsequent
    # one is 250px further down (or stacks based on the spec's original y order).
    for stack_idx, (ov_idx, ov) in enumerate(scene_overlay_inputs_v):
        in_t = float(ov.get("in", 0.0))
        out_t = float(ov.get("out", duration))
        fade_d = 0.5
        if out_t - in_t < fade_d * 2:
            out_t = in_t + fade_d * 2 + 0.1
        fade_out_start = out_t - fade_d

        label_a = f"[ovv{ov_idx}a]"
        # Scale overlay down to fit vertical width (900 max), keep aspect
        chain_parts.append(
            f"[{ov_idx}:v]format=rgba,"
            f"scale='min(900,iw)':-1,"
            f"fade=t=in:st={in_t}:d={fade_d}:alpha=1,"
            f"fade=t=out:st={fade_out_start}:d={fade_d}:alpha=1{label_a}"
        )

        # Vertical positioning: center horizontally via (W-w)/2.
        # For y: if the spec has multiple overlays (cascading bullets), stack them
        # down the top portion of the frame. Use stack_idx * 260 + 280 starting y.
        # For single-slot rotating overlays (scene 2 style), they overlap at the
        # same y which is fine since only one is visible at a time.
        # Use a heuristic: if this overlay's in-time is within 2s of the previous
        # one, treat as cascading (stack); otherwise treat as rotating (same y).
        if scene_overlay_inputs_v and len(scene_overlay_inputs_v) > 1:
            # Detect cascading: overlays that all hold until the scene end are
            # "stacking" (each appears and stays). Rotating overlays have out
            # times that are close to their in times.
            is_cascading = (out_t >= duration - 1.0)
            if is_cascading:
                base_y = 280 + stack_idx * 260
            else:
                base_y = 380  # single rotating position in upper-middle
        else:
            base_y = 400

        new = next_label()
        chain_parts.append(
            f"{current}{label_a}overlay=x=(W-w)/2:y={base_y}:eof_action=pass{new}"
        )
        current = new

    chain_parts.append(f"{current}null[vout]")
    filter_complex = ";".join(chain_parts)
    maps = ["-map", "[vout]", "-map", "1:a"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *maps,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"vertical scene stderr: {result.stderr[-800:]}")
        raise RuntimeError("Vertical scene failed")


def assemble_scene(broll_files, narration_wav, out_path, duration,
                   banner_line1="", banner_line2="",
                   banner_bg_path=None, logo_plate_path=None, qr_card_path=None,
                   brand_color="0xe94560",
                   ask_overlay_path=None, ask_stamp_at=2.5,
                   scene_overlays=None):
    """Build a single scene: b-roll + narration + branded lower-third package
    (pre-baked banner PNG + logo plate + QR card + contact text drawn on top)
    + optional scene-5 ask overlay that fades up at ask_stamp_at and holds.

    The banner PNG is 1920x155 with top-rounded corners, flush to the frame bottom.
    It already contains the fill color and accent stripe — we just overlay it.
    The logo plate and QR card are separately positioned relative to the banner.
    Contact text (org name + phone + URL) is drawn with ffmpeg drawtext on top.
    """
    if not broll_files:
        filter_in = ["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1920x1080:d={duration}:r=30"]
    else:
        filter_in = ["-stream_loop", "-1", "-i", str(broll_files[0])]

    FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

    # Banner geometry (must match make_banner_bg output).
    # The banner is a floating pill — lifted 25px above the frame bottom and
    # inset 30px from each horizontal edge — so a strip of b-roll is visible
    # around it. All 4 corners rounded.
    BANNER_H = 155
    BANNER_W = 1860
    BANNER_LIFT = 25
    BANNER_SIDE = 30
    BANNER_X = BANNER_SIDE  # 30
    BANNER_Y = 1080 - BANNER_H - BANNER_LIFT  # 900

    # Inputs: [0] b-roll, [1] narration, then optional overlays
    inputs = list(filter_in)
    inputs.extend(["-i", str(narration_wav)])

    next_idx = 2
    banner_idx = None
    plate_idx = None
    qr_idx = None
    ask_idx = None

    if banner_bg_path and Path(banner_bg_path).exists():
        inputs.extend(["-i", str(banner_bg_path)])
        banner_idx = next_idx
        next_idx += 1
    if logo_plate_path and Path(logo_plate_path).exists():
        inputs.extend(["-i", str(logo_plate_path)])
        plate_idx = next_idx
        next_idx += 1
    if qr_card_path and Path(qr_card_path).exists():
        inputs.extend(["-i", str(qr_card_path)])
        qr_idx = next_idx
        next_idx += 1
    if ask_overlay_path and Path(ask_overlay_path).exists():
        inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(ask_overlay_path)])
        ask_idx = next_idx
        next_idx += 1

    # Timed scene overlays (e.g. scene 2's rotating MS callouts)
    # Each entry: dict with keys 'path', 'in', 'out', 'pos'
    scene_overlay_inputs = []  # list of (idx, overlay_dict)
    if scene_overlays:
        for ov in scene_overlays:
            ov_path = ov.get("path")
            if ov_path and Path(ov_path).exists():
                inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(ov_path)])
                scene_overlay_inputs.append((next_idx, ov))
                next_idx += 1

    # --- Build main_chain (b-roll scaling + eq, but NO drawbox banner anymore) ---
    main_chain = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "fps=30,"
        "eq=saturation=0.85:contrast=1.08"
    )

    # --- Compose filter graph with incremental overlay labels ---
    chain_parts = [f"[0:v]{main_chain}[base0]"]
    current = "[base0]"
    label_n = 0

    def next_label():
        nonlocal label_n
        label_n += 1
        return f"[v{label_n}]"

    # 1. Banner background (1860px all-corners-rounded PNG, lifted 25px from bottom,
    #    inset 30px from each side)
    if banner_idx is not None:
        new = next_label()
        chain_parts.append(f"{current}[{banner_idx}:v]overlay=x={BANNER_X}:y={BANNER_Y}{new}")
        current = new

    # 2. Contact text lines on top of the banner (drawtext — cheaper than PIL for this)
    # Layout: starts after logo plate area. Plate sits at BANNER_X+15, ~495px wide,
    # so text starts around BANNER_X+15+495+30 = ~570.
    text_x = (BANNER_X + 15 + 495 + 30) if plate_idx is not None else (BANNER_X + 30)
    drawtext_parts = []
    if banner_line1:
        safe1 = banner_line1.replace("'", "").replace(":", "").replace("\\", "")
        drawtext_parts.append(
            f"drawtext=fontfile='{FONT_BOLD}':text='{safe1}':fontcolor=white:fontsize=46:"
            f"x={text_x}:y={BANNER_Y + 32}"
        )
    if banner_line2:
        safe2 = banner_line2.replace("'", "").replace(":", "").replace("\\", "")
        drawtext_parts.append(
            f"drawtext=fontfile='{FONT}':text='{safe2}':fontcolor=0xdcdcdc:fontsize=30:"
            f"x={text_x}:y={BANNER_Y + 92}"
        )
    if drawtext_parts:
        new = next_label()
        chain_parts.append(f"{current}" + ",".join(drawtext_parts) + new)
        current = new

    # 3. Logo plate on left side of banner
    if plate_idx is not None:
        # Plate is 100px tall logo + padding → ~116px total. Center vertically in banner.
        plate_x = BANNER_X + 15
        plate_y = BANNER_Y + (BANNER_H - 116) // 2 + 2
        new = next_label()
        chain_parts.append(
            f"{current}[{plate_idx}:v]overlay=x={plate_x}:y={plate_y}{new}"
        )
        current = new

    # 4. QR card on right side of banner (inside the 1860px banner width)
    if qr_idx is not None:
        qr_x = BANNER_X + BANNER_W - 140 - 15
        qr_y = BANNER_Y + (BANNER_H - 140) // 2 + 2
        new = next_label()
        chain_parts.append(
            f"{current}[{qr_idx}:v]overlay=x={qr_x}:y={qr_y}{new}"
        )
        current = new

    # 5. Scene-5-only ask overlay: fades in with alpha at ask_stamp_at
    if ask_idx is not None:
        # Apply fade-in-alpha to the looping ask overlay image
        chain_parts.append(
            f"[{ask_idx}:v]format=rgba,"
            f"fade=t=in:st={ask_stamp_at}:d=1.0:alpha=1[askfade]"
        )
        new = next_label()
        chain_parts.append(
            f"{current}[askfade]overlay=x=120:y=180:eof_action=pass{new}"
        )
        current = new

    # 6. Timed scene overlays (rotating callouts, e.g. scene 2)
    # Each overlay has its own fade-in and fade-out timing; they're independent
    # images that drop into the frame's "dead space" for a few seconds each.
    # Positioning keyword 'right-nose' = vertically centered at ~y=310,
    # right-aligned with 80px margin from the right edge.
    for ov_idx, ov in scene_overlay_inputs:
        in_t = float(ov.get("in", 0.0))
        out_t = float(ov.get("out", duration))
        fade_d = 0.5  # half-second fade in AND out
        # Safety: make sure the fades don't overlap (fade-out must be after fade-in finishes)
        if out_t - in_t < fade_d * 2:
            out_t = in_t + fade_d * 2 + 0.1
        fade_out_start = out_t - fade_d

        label_a = f"[ov{ov_idx}a]"
        chain_parts.append(
            f"[{ov_idx}:v]format=rgba,"
            f"fade=t=in:st={in_t}:d={fade_d}:alpha=1,"
            f"fade=t=out:st={fade_out_start}:d={fade_d}:alpha=1{label_a}"
        )

        # Explicit x/y in the overlay spec override the named pos keyword
        if "x" in ov and "y" in ov:
            overlay_expr = f"x={ov['x']}:y={ov['y']}"
        else:
            pos = ov.get("pos", "right-nose")
            if pos == "right-nose":
                # Right-aligned, vertically centered near nose (y=310 in 1080 frame).
                overlay_expr = "x=W-w-80:y=310-h/2"
            elif pos == "right-top":
                overlay_expr = "x=W-w-60:y=100"
            elif pos == "left-top":
                overlay_expr = "x=60:y=100"
            elif pos == "left-nose":
                overlay_expr = "x=60:y=310-h/2"
            else:
                overlay_expr = "x=W-w-80:y=310-h/2"

        new = next_label()
        chain_parts.append(
            f"{current}{label_a}overlay={overlay_expr}:eof_action=pass{new}"
        )
        current = new

    # 7. Rename final current label to [vout]
    chain_parts.append(f"{current}null[vout]")

    filter_complex = ";".join(chain_parts)
    maps = ["-map", "[vout]", "-map", "1:a"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *maps,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg stderr: {result.stderr[-500:]}")
        raise RuntimeError("ffmpeg assemble failed")


def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip() or "0")


def build_final_card(job_dir, org, url, phone, qr_badge_path, final_music,
                     duration=12, bullets=None,
                     hero_image=None, logo_path=None, logo_plate_path=None,
                     brand_color="0xe94560", tagline=None,
                     credit_tag=None, credit_sub=None):
    """Build a closing card with optional hero image background, sponsor logo, and emotional tagline.

    Two modes:
      - BRANDED (hero_image provided): hero image full-bleed, logo top-left, tagline in dead zone,
        CTA visible from t=0, brand color for CTA accent.
      - LEGACY (no hero_image): solid dark-blue background, ORG name top, optional bullets drop in,
        CTA appears at t=6. Same behavior as before.
    """
    out_path = job_dir / "final_card.mp4"
    FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"

    org_up = org.upper().replace("'", "").replace(":", "")
    line1 = "DONATE TODAY"
    line2 = url.replace("'", "").replace(":", "")
    line3 = f"Call {phone}" if phone else ""
    line3 = line3.replace("'", "").replace(":", "")

    branded_mode = bool(hero_image and Path(hero_image).exists())
    # Prefer pre-generated logo plate PNG (consistent with scenes). Fall back to
    # raw logo + ffmpeg pad for backwards compatibility.
    has_plate = bool(logo_plate_path and Path(logo_plate_path).exists())
    has_logo = has_plate or bool(logo_path and Path(logo_path).exists())
    has_qr = bool(qr_badge_path and Path(qr_badge_path).exists())

    # --- BUILD INPUTS ---
    inputs = []
    idx = 0

    if branded_mode:
        # Input 0: hero image as looping video
        inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(hero_image)])
    else:
        # Input 0: solid dark blue background (legacy)
        inputs.extend(["-f", "lavfi", "-i", f"color=c=0x0f3460:s=1920x1080:d={duration}:r=30"])
    hero_idx = idx
    idx += 1

    # Input 1: final music
    inputs.extend(["-i", str(final_music)])
    music_idx = idx
    idx += 1

    logo_input_idx = None
    if has_logo:
        # Use the pre-generated plate PNG if available, else raw logo
        inputs.extend(["-i", str(logo_plate_path if has_plate else logo_path)])
        logo_input_idx = idx
        idx += 1

    qr_input_idx = None
    if has_qr:
        inputs.extend(["-i", str(qr_badge_path)])
        qr_input_idx = idx
        idx += 1

    # --- BUILD FILTER GRAPH ---
    chains = []

    if branded_mode:
        # Hero image: fill frame, darken + desaturate for text readability
        chains.append(
            f"[{hero_idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,fps=30,eq=brightness=-0.22:saturation=0.80,"
            f"setsar=1[bg0]"
        )
    else:
        chains.append(f"[{hero_idx}:v]null[bg0]")

    current = "[bg0]"

    # Overlay logo plate (top-left on final card).
    # If we have a pre-generated plate (PIL — matches scene banner), scale it up
    # and overlay directly. Otherwise, fall back to ffmpeg pad + scale on the raw logo.
    if has_logo:
        if has_plate:
            # Pre-rendered plate already has rounded corners + orange border — just scale.
            chains.append(
                f"[{logo_input_idx}:v]scale=460:-1[logofinal]"
            )
        else:
            chains.append(
                f"[{logo_input_idx}:v]scale=440:-1,"
                f"pad=iw+10:ih+10:5:5:{brand_color}[logofinal]"
            )
        chains.append(f"{current}[logofinal]overlay=x=80:y=80[bg1]")
        current = "[bg1]"

    # Overlay QR (bottom-right)
    if has_qr:
        chains.append(f"[{qr_input_idx}:v]scale=200:200[qrfinal]")
        chains.append(f"{current}[qrfinal]overlay=x=1680:y=820[bg2]")
        current = "[bg2]"

    # --- TEXT OVERLAYS ---
    drawtexts = []

    if branded_mode:
        # Branded layout: logo is the org identifier (skip big ORG text)
        # Tagline in dead zone ~y=440, rendered with a black outline (no backdrop box)
        if tagline:
            safe_tag = str(tagline).replace("'", "").replace(":", "").replace("\\", "")
            drawtexts.append(
                f"drawtext=fontfile='{FONT}':text='{safe_tag}':"
                f"fontcolor=white:fontsize=68:"
                f"x=(w-text_w)/2:y=430:"
                f"borderw=5:bordercolor=black"
            )

        # CTA visible from t=0 — brand color with black outline for contrast
        drawtexts.append(
            f"drawtext=fontfile='{FONT}':text='{line1}':"
            f"fontcolor={brand_color}:fontsize=120:"
            f"x=(w-text_w)/2:y=680:"
            f"borderw=8:bordercolor=black"
        )
        drawtexts.append(
            f"drawtext=fontfile='{FONT}':text='{line2}':"
            f"fontcolor=white:fontsize=56:"
            f"x=(w-text_w)/2:y=830:"
            f"borderw=4:bordercolor=black"
        )
        if line3:
            drawtexts.append(
                f"drawtext=fontfile='{FONT}':text='{line3}':"
                f"fontcolor=white:fontsize=40:"
                f"x=(w-text_w)/2:y=920:"
                f"borderw=3:bordercolor=black"
            )
    else:
        # LEGACY layout — preserve original behavior
        drawtexts.append(
            f"drawtext=fontfile='{FONT}':text='{org_up}':fontcolor=white:fontsize=64:"
            f"x=(w-text_w)/2:y=120"
        )
        drawtexts.append(
            f"drawbox=x=560:y=210:w=800:h=3:color={brand_color}@1.0:t=fill"
        )

        if bullets:
            bullet_y_start = 290
            bullet_spacing = 120
            appear_times = [1.0, 2.5, 4.0]
            for i, text in enumerate(bullets[:3]):
                safe = str(text).replace("'", "").replace(":", "").replace("\\", "")
                y = bullet_y_start + i * bullet_spacing
                appear = appear_times[i]
                drawtexts.append(
                    f"drawbox=x=300:y={y+32}:w=16:h=16:color={brand_color}@1.0:t=fill:"
                    f"enable='gte(t,{appear})'"
                )
                drawtexts.append(
                    f"drawtext=fontfile='{FONT}':text='{safe}':fontcolor=white:fontsize=52:"
                    f"x=350:y={y}:enable='gte(t,{appear})'"
                )

        cta_appear = 6.0
        drawtexts.append(
            f"drawtext=fontfile='{FONT}':text='{line1}':fontcolor={brand_color}:fontsize=90:"
            f"x=(w-text_w)/2:y=780:enable='gte(t,{cta_appear})'"
        )
        drawtexts.append(
            f"drawtext=fontfile='{FONT}':text='{line2}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=900:enable='gte(t,{cta_appear})'"
        )
        if line3:
            drawtexts.append(
                f"drawtext=fontfile='{FONT}':text='{line3}':fontcolor=0xcccccc:fontsize=36:"
                f"x=(w-text_w)/2:y=970:enable='gte(t,{cta_appear})'"
            )

    # Production credit (bottom-center two-line: bold brand-orange tag + white subtitle)
    # Appears on both branded and legacy modes for consistency.
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    if credit_tag:
        safe_tag = str(credit_tag).replace("'", "").replace(":", "").replace("\\", "")
        # y=1020 puts the tag ~60px above the bottom; sub line ~30px further down.
        sub_y = 1055
        tag_y = 1018 if credit_sub else 1030
        drawtexts.append(
            f"drawtext=fontfile='{FONT_BOLD}':text='{safe_tag}':"
            f"fontcolor={brand_color}:fontsize=26:"
            f"x=(w-text_w)/2:y={tag_y}:"
            f"borderw=2:bordercolor=black"
        )
        if credit_sub:
            safe_sub = str(credit_sub).replace("'", "").replace(":", "").replace("\\", "")
            drawtexts.append(
                f"drawtext=fontfile='{FONT}':text='{safe_sub}':"
                f"fontcolor=white:fontsize=20:"
                f"x=(w-text_w)/2:y={sub_y}:"
                f"borderw=2:bordercolor=black"
            )

    # Chain all drawtexts + fade in/out onto the current video layer
    text_chain = ",".join(drawtexts)
    text_chain += f",fade=t=in:st=0:d=0.8,fade=t=out:st={duration-1.5}:d=1.5"
    chains.append(f"{current}{text_chain}[vout]")

    # Audio
    chains.append(
        f"[{music_idx}:a]volume=0.12,afade=t=in:st=0:d=0.5,"
        f"afade=t=out:st={duration-2.0}:d=2.0[aout]"
    )

    filter_complex = ";".join(chains)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"final card stderr: {result.stderr[-800:]}")
        raise RuntimeError("Final card build failed")
    return out_path


def build_credits_segment(job_dir, sections, brand_color,
                          duration=18, bg_color="0x0a0a0a"):
    """Build a rolling-credits video segment that plays after the final card.

    Pipeline:
      1. PIL renders a tall PNG containing all the credit text (via
         make_rolling_credits_png). Header lines are in brand_color, body
         lines in white. Centered horizontally.
      2. ffmpeg loops the PNG as a video input and overlays it onto a dark
         background, using a y expression that scrolls the PNG from below
         the frame to above the frame over the segment duration. Result is
         the classic movie-style end credits.
      3. Fade in at start, fade out at end. Silent audio track at the end
         (so it can be concat'd cleanly — piano fades out into the credits).

    Returns the path to credits.mp4.
    """
    out_path = job_dir / "credits.mp4"
    png_path = job_dir / "credits.png"

    _, credits_h = make_rolling_credits_png(png_path, brand_color, sections)
    print(f"   📜 Credits PNG height: {credits_h}px")

    # Scroll expression: y moves from H (below) to -credits_h (above) over duration.
    # At t=0: overlay y = H (just below frame, starting invisible)
    # At t=duration: overlay y = -credits_h (just above frame, fully off)
    # Total scroll distance: H + credits_h
    H = 1080
    scroll_expr = f"{H}-(t/{duration})*({H}+{credits_h})"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:s=1920x1080:d={duration}:r=30",
        "-loop", "1", "-t", str(duration), "-i", str(png_path),
        "-f", "lavfi",
        "-t", str(duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex",
        # Fade in/out on background + overlay PNG with scrolling y
        f"[0:v]fade=t=in:st=0:d=1.0,fade=t=out:st={duration-1.5}:d=1.5[bg];"
        f"[1:v]format=rgba[pngs];"
        f"[bg][pngs]overlay=x=(W-w)/2:y='{scroll_expr}':eof_action=pass[vout]",
        "-map", "[vout]", "-map", "2:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"credits segment stderr: {result.stderr[-800:]}")
        raise RuntimeError("Credits segment build failed")
    return out_path


BUMPER_VOICE_ID = "Hc7x4ltPjBjqyWZ3X8mB"   # Douglas — Doug's cloned voice, bumper only
BUMPER_VOICE_TEXT = "Look Mom. No hands."
BUMPER_VOICE_CACHE = PROJECT_ROOT / "brand_assets" / "bumper_voice.mp3"


def _ensure_bumper_voice():
    """Generate 'Look Mom. No hands.' in Doug's voice once and cache it forever."""
    if BUMPER_VOICE_CACHE.exists():
        return BUMPER_VOICE_CACHE
    api_key = _load_env_key("~/.keys/.env", "ELEVENLABS_API_KEY")
    if not api_key:
        return None
    import urllib.request as _ur
    data = json.dumps({
        "text": BUMPER_VOICE_TEXT,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.80}
    }).encode()
    req = _ur.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{BUMPER_VOICE_ID}",
        data=data,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"}
    )
    with _ur.urlopen(req, timeout=60) as r:
        mp3_bytes = r.read()
    BUMPER_VOICE_CACHE.write_bytes(mp3_bytes)
    print(f"   🎙️  Bumper voice generated and cached: {BUMPER_VOICE_CACHE.name}")
    return BUMPER_VOICE_CACHE


def build_bumper_segment(job_dir, brand_color, duration=None,
                          black_hold=1.0, crash_sound_path=None):
    """Build the 'Look Mom, No Hands Productions' closing bumper.

    Structure:
      0.0 → black_hold s  : pure black frame, silence (suspense beat)
      black_hold          : bumper PNG stamps in + crash sound + Doug's voice

    Returns path to bumper.mp4.
    """
    out_path = job_dir / "bumper.mp4"
    bumper_png = job_dir / "bumper.png"
    make_bumper_png(bumper_png, brand_color_hex=brand_color)

    stamp_start = black_hold
    # Default crash sound: macOS system Glass sound
    if crash_sound_path is None or not Path(crash_sound_path).exists():
        crash_sound_path = "/System/Library/Sounds/Glass.aiff"
    has_crash = Path(crash_sound_path).exists()

    # Generate Doug's voice (cached after first run — free forever after)
    bumper_voice = _ensure_bumper_voice()
    has_voice = bumper_voice and Path(bumper_voice).exists()

    # Auto-size bumper duration to fit voice audio + tail
    if duration is None:
        if has_voice:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(bumper_voice)],
                capture_output=True, text=True
            )
            voice_dur = float(probe.stdout.strip() or "3.0")
            duration = black_hold + voice_dur + 1.0  # 1s tail
        else:
            duration = 4.5

    delay_ms = int(black_hold * 1000)

    inputs = [
        "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={duration}:r=30",
        "-loop", "1", "-t", str(duration), "-i", str(bumper_png),
    ]

    audio_inputs = []
    audio_chains = []
    idx = 2

    if has_crash:
        inputs.extend(["-i", str(crash_sound_path)])
        audio_chains.append(
            f"[{idx}:a]volume=0.12,adelay={delay_ms}|{delay_ms},"
            f"apad=whole_dur={duration},atrim=0:{duration}[crash]"
        )
        idx += 1

    if has_voice:
        inputs.extend(["-i", str(bumper_voice)])
        audio_chains.append(
            f"[{idx}:a]volume=1.0,adelay={delay_ms}|{delay_ms},"
            f"apad=whole_dur={duration},atrim=0:{duration}[vo]"
        )
        idx += 1

    # Mix whichever audio streams exist
    if has_crash and has_voice:
        audio_chains.append("[crash][vo]amix=inputs=2:normalize=0[aout]")
    elif has_crash:
        audio_chains[-1] = audio_chains[-1].replace("[crash]", "[aout]")
    elif has_voice:
        audio_chains[-1] = audio_chains[-1].replace("[vo]", "[aout]")
    else:
        inputs.extend([
            "-f", "lavfi", "-t", str(duration),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"
        ])
        audio_chains.append(f"[{idx}:a]anull[aout]")

    video_chain = (
        f"[1:v]format=rgba,"
        f"fade=t=in:st={stamp_start}:d=0.08:alpha=1[bstamp];"
        f"[0:v][bstamp]overlay=x=0:y=0:eof_action=pass[vout]"
    )

    filter_complex = video_chain + ";" + ";".join(audio_chains)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"bumper stderr: {result.stderr[-800:]}")
        raise RuntimeError("Bumper build failed")
    return out_path


def concat_scenes(scene_files, out_path, music_path=None, final_card=None, final_music=None, credits_segment=None, bumper_segment=None):
    """
    Simple two-step audio build — piano plays continuously through the entire video:
      1. Concatenate scene videos → body video (voice audio)
      2. Xfade body → final_card (video only; final_card's audio is discarded,
         body voice fades out over the xfade window into silence under the final card)
      3. Mix piano music underneath the entire combined video as ONE continuous bed,
         fading in at the start and fading out at the very end.

    The final_music parameter is retained for backwards compatibility but its audio
    is no longer mixed into the final output — piano carries the whole thing.
    """
    body_path = out_path.parent / "_body_video.mp4"
    combined_path = out_path.parent / "_combined_video.mp4"
    n = len(scene_files)
    parts = "".join(f"[{i}:v][{i}:a]" for i in range(n))

    # Step 1: Concat scene videos with voice audio only
    concat_inputs = []
    for f in scene_files:
        concat_inputs.extend(["-i", str(f)])
    filter_c = f"{parts}concat=n={n}:v=1:a=1[v][a]"
    cmd = [
        "ffmpeg", "-y",
        *concat_inputs,
        "-filter_complex", filter_c,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        str(body_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"body concat stderr: {result.stderr[-500:]}")
        raise RuntimeError("Body concat failed")

    body_dur = probe_duration(body_path)

    # Step 2: Xfade body → final_card (if provided), ignoring final_card's own audio
    if final_card and Path(final_card).exists():
        final_dur = probe_duration(Path(final_card))
        xfade_dur = 1.0
        xfade_offset = max(0, body_dur - xfade_dur)
        total_dur = body_dur + final_dur - xfade_dur

        cmd = [
            "ffmpeg", "-y",
            "-i", str(body_path),
            "-i", str(final_card),
            "-filter_complex",
            # Video: crossfade between body and final_card
            f"[0:v][1:v]xfade=transition=fade:duration={xfade_dur}:offset={xfade_offset}[v];"
            # Audio: body's voice, fading out during the xfade window, then silence
            # for the remaining final_card duration. Piano will fill all of it in step 3.
            f"[0:a]afade=t=out:st={xfade_offset}:d={xfade_dur}[voice_fade];"
            f"aevalsrc=0:d={final_dur - xfade_dur}[silence];"
            f"[voice_fade][silence]concat=n=2:v=0:a=1[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            str(combined_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"combined stderr: {result.stderr[-800:]}")
            raise RuntimeError("Combined body+final_card build failed")
    else:
        # No final card — body IS the combined
        shutil.copy2(body_path, combined_path)
        total_dur = body_dur

    # Step 3: Concat combined + credits + bumper into one silent-music assembly
    full_combined_path = out_path.parent / "_full_combined.mp4"
    tail_segments = []
    if credits_segment and Path(credits_segment).exists():
        tail_segments.append(credits_segment)
    if bumper_segment and Path(bumper_segment).exists():
        tail_segments.append(bumper_segment)

    if tail_segments:
        all_inputs = [combined_path] + [Path(s) for s in tail_segments]
        parts = "".join(f"[{i}:v][{i}:a]" for i in range(len(all_inputs)))
        filter_c = f"{parts}concat=n={len(all_inputs)}:v=1:a=1[v][a]"
        cmd = ["ffmpeg", "-y"]
        for seg in all_inputs:
            cmd.extend(["-i", str(seg)])
        cmd.extend([
            "-filter_complex", filter_c,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            str(full_combined_path),
        ])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"tail concat stderr: {result.stderr[-800:]}")
            raise RuntimeError("Tail segment concat failed")
    else:
        shutil.copy2(combined_path, full_combined_path)

    # Step 4: Mix music under the FULL video — scenes + final card + credits + bumper
    # Music now plays continuously through everything including rolling credits.
    if music_path and Path(music_path).exists():
        full_dur = probe_duration(full_combined_path)
        piano_fadeout_start = max(0, full_dur - 2.5)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(full_combined_path),
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex",
            f"[1:a]volume=0.10,afade=t=in:st=0:d=1.5,"
            f"afade=t=out:st={piano_fadeout_start}:d=2.5[piano];"
            f"[0:a][piano]amix=inputs=2:duration=first:dropout_transition=0:weights='1 1'[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"piano mix stderr: {result.stderr[-800:]}")
            raise RuntimeError("Final piano mix failed")
    else:
        shutil.copy2(full_combined_path, out_path)

    # Cleanup
    body_path.unlink(missing_ok=True)
    combined_path.unlink(missing_ok=True)
    full_combined_path.unlink(missing_ok=True)


# ---------- REAL FOOTAGE: article hero image → Ken Burns clip ----------

def fetch_article_hero(article_url, timeout=8):
    """Scrape an article page for its hero image (og:image preferred, then
    twitter:image, then first large <img>).

    Returns a direct image URL string, or None.
    """
    if not article_url:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(article_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MotherShowRunner/1.0)"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Google News link redirects — follow the chain (urllib does by default)
            html = resp.read(500_000).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    hero scrape failed ({article_url[:60]}): {e}")
        return None

    # Look for og:image and twitter:image in that order
    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = m.group(1)
            if url.startswith("//"):
                url = "https:" + url
            return url
    return None


def download_image(image_url, out_path, timeout=10):
    """Download an image URL to out_path. Returns True on success."""
    try:
        import urllib.request
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 2_000:  # likely a 1x1 tracking gif
            return False
        out_path.write_bytes(data)
        return True
    except Exception as e:
        print(f"    image download failed: {e}")
        return False


def image_to_kenburns_clip(image_path, out_path, duration, width=1920, height=1080):
    """Turn a still image into a slow pan/zoom MP4 (news-doc feel).

    Uses ffmpeg zoompan with a gentle 1.0 → 1.1 zoom over the full duration,
    scaled + padded to fit the target canvas so the picture is never cropped
    off-center.
    """
    image_path = Path(image_path)
    out_path = Path(out_path)
    fps = 30
    total_frames = max(1, int(duration * fps))

    # Scale the source image to at least 2x the canvas so zoompan has headroom
    # force_original_aspect_ratio=decrease keeps the full image visible
    vf = (
        f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,"
        f"pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"zoompan=z='min(zoom+0.0005,1.10)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    kenburns failed: {result.stderr[-400:]}")
        return False
    return True


def try_real_footage(article_url, scene_dir, duration, width=1920, height=1080):
    """Try to produce a scene-length MP4 from the article's own hero image.

    Returns Path to the generated MP4 on success, or None to fall back to Pexels.
    """
    if not article_url:
        return None
    hero_url = fetch_article_hero(article_url)
    if not hero_url:
        return None
    # Some hero URLs land with .jpg, some not — pick a safe extension
    ext = ".jpg"
    for e in (".png", ".webp", ".jpeg", ".jpg"):
        if hero_url.lower().split("?")[0].endswith(e):
            ext = e
            break
    img_path = scene_dir / f"hero{ext}"
    if not download_image(hero_url, img_path):
        return None
    clip_path = scene_dir / "hero_kenburns.mp4"
    if not image_to_kenburns_clip(img_path, clip_path, duration, width=width, height=height):
        return None
    print(f"    ✅ Using real article hero ({hero_url[:70]}...)")
    return clip_path


# ---------- CAPTIONS ----------

def add_soft_captions(video_path, model_size="base", words_per_caption=6):
    """Generate captions.srt next to video_path and mux it as a soft
    mov_text subtitle track into the MP4. The video itself is untouched
    (no burn-in) — players/YouTube toggle CC on/off.

    Returns the SRT sidecar Path. Leaves both the captioned MP4 (in place)
    and the .srt file alongside it.
    """
    video_path = Path(video_path)
    srt_path = video_path.with_suffix(".srt")

    # Extract audio
    audio_tmp = video_path.parent / f"_caption_audio_{video_path.stem}.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path), "-vn",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(audio_tmp),
    ], capture_output=True, text=True, check=False)
    if not audio_tmp.exists():
        print("  ⚠️  Caption skipped — could not extract audio")
        return None

    # Run Whisper
    try:
        sys.path.insert(0, str(Path(__file__).parent / "tools"))
        from whisper_captions import generate_srt_from_whisper
        print(f"  🎙️  Generating captions via Whisper ({model_size})...")
        generate_srt_from_whisper(audio_tmp, srt_path,
                                  words_per_caption=words_per_caption,
                                  model_size=model_size)
    except Exception as e:
        print(f"  ⚠️  Caption generation failed: {e}")
        audio_tmp.unlink(missing_ok=True)
        return None
    finally:
        audio_tmp.unlink(missing_ok=True)

    if not srt_path.exists() or srt_path.stat().st_size < 20:
        print("  ⚠️  SRT file empty, skipping mux")
        return None

    # Mux SRT as soft subtitle track (mov_text) — replace video in place
    muxed = video_path.with_name(f"_captioned_{video_path.name}")
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(srt_path),
        "-c:v", "copy", "-c:a", "copy",
        "-c:s", "tx3g",
        "-metadata:s:s:0", "language=eng",
        "-metadata:s:s:0", "title=English (CC)",
        "-disposition:s:0", "default",
        str(muxed),
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  Caption mux failed: {result.stderr[-300:]}")
        muxed.unlink(missing_ok=True)
        return srt_path  # at least the .srt sidecar survived

    # Swap in place
    video_path.unlink()
    muxed.rename(video_path)
    print(f"  ✅ Captions muxed: {srt_path.name} (+ soft track on {video_path.name})")
    return srt_path


# ---------- MAIN ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--cause", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--qr-url", default="", help="URL encoded into the QR code (defaults to --url if not set)")
    ap.add_argument("--ask", default="$19 a month")
    ap.add_argument("--phone", default="", help="Phone number for lower-third banner")
    ap.add_argument("--reuse", default="", help="Path to existing job dir to reuse audio/broll from")
    ap.add_argument("--music", default="", help="Path to background music file (mp3/wav)")
    ap.add_argument("--final-music", default="", help="Path to final-card music (violin/strings)")
    ap.add_argument("--vertical", action="store_true", help="Also output a 1080x1920 vertical version")
    ap.add_argument("--only-vertical", action="store_true", help="Only build vertical (skip landscape)")
    ap.add_argument("--script", default="", help="Path to hand-written script JSON (skips Ollama)")
    ap.add_argument("--bullets", default="", help="Pipe-separated bullet points for final card, e.g. 'Fact 1|Fact 2|Fact 3'")
    ap.add_argument("--hero-image", default="", help="Path to hero image for branded final card background")
    ap.add_argument("--logo", default="", help="Path to sponsor/org logo (PNG). Shown on final card top-left AND in lower-third banner right side during scenes")
    ap.add_argument("--brand-color", default="0xe94560", help="Brand accent color in hex (e.g. 0xe27d00 for NMS orange). Used for CTA on final card and banner accent stripe")
    ap.add_argument("--tagline", default="", help="Emotional tagline shown in the dead zone of the final card")
    ap.add_argument("--ask-stamp", default="", help="Short ask text shown large in top-right of scene 5 (e.g. '$19/MO')")
    ap.add_argument("--ask-stamp-at", type=float, default=2.5, help="Seconds into scene 5 when ask stamp fades in (default 2.5)")
    ap.add_argument("--credit-tag", default="", help="Production credit on the final card — main line (e.g. 'MS VOCAL ARTIST'). Rendered bottom-center.")
    ap.add_argument("--credit-sub", default="", help="Production credit on the final card — subtitle line (e.g. 'fundraiser video production'). Optional.")
    ap.add_argument("--rolling-credits", action="store_true", help="Append rolling end credits after the final card (uses rolling_credits in script JSON for content)")
    ap.add_argument("--credits-duration", type=float, default=18.0, help="Duration of the rolling credits segment in seconds (default 18)")
    ap.add_argument("--bumper", action="store_true", help="Append 'Look Mom, No Hands Productions' closing bumper (1.5s, stick figure stamp with crash SFX)")
    ap.add_argument("--bumper-crash", default="", help="Path to crash sound effect for bumper (defaults to /System/Library/Sounds/Glass.aiff)")
    ap.add_argument("--no-captions", action="store_true", help="Skip Whisper caption generation (default: captions ON)")
    ap.add_argument("--caption-model", default="base", help="Whisper model size (tiny/base/small/medium/large)")
    ap.add_argument("--voice", default="", help="OpenAI TTS voice: alloy, echo, fable, onyx (deep male), nova (female), shimmer. Overrides OPENAI_VOICE constant.")
    ap.add_argument("--tts", default="", help="TTS engine: elevenlabs, openai, piper. Overrides TTS_ENGINE constant.")
    ap.add_argument("--el-voice", default="", help="ElevenLabs voice ID. Overrides ELEVENLABS_VOICE_ID constant.")
    ap.add_argument("--music-volume", type=float, default=0.0, help="Override background music volume (0.0–1.0). Default uses built-in level.")
    args = ap.parse_args()

    banner_line1 = args.org.upper()
    banner_parts = []
    if args.phone:
        banner_parts.append(f"Call {args.phone}")
    banner_parts.append(args.url)
    banner_line2 = "   •   ".join(banner_parts)

    # Apply CLI overrides
    if args.voice:
        global OPENAI_VOICE
        OPENAI_VOICE = args.voice
    if args.tts:
        global TTS_ENGINE
        TTS_ENGINE = args.tts
    if args.el_voice:
        global ELEVENLABS_VOICE_ID
        ELEVENLABS_VOICE_ID = args.el_voice

    # Build the QR badge once (used on every scene)
    qr_badge_path = None

    reuse_dir = Path(args.reuse) if args.reuse else None
    if reuse_dir and reuse_dir.exists():
        # Rebuild in-place — reuse same job dir, overwrite output
        job_dir = reuse_dir
        print(f"♻️  REUSING existing job — no new TTS or Pexels charges")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        job_dir = OUT_DIR / f"{args.org.replace(' ', '_')}_{stamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

    print(f"📁 Output: {job_dir}")

    # ---- Generate branded lower-third asset package once per job ----
    # All of these are PIL-generated PNGs that ffmpeg overlays on each scene.
    qr_card_path = job_dir / "qr_card.png"
    banner_bg_path = job_dir / "banner_bg.png"
    logo_plate_path = None
    ask_overlay_path = None

    try:
        _qr_target = args.qr_url or args.url
        qr_url = _qr_target if _qr_target.startswith("http") else f"https://{_qr_target}"
        make_qr_card(qr_url, qr_card_path, brand_color_hex=args.brand_color, size=140)
        print(f"✅ QR card: {qr_card_path.name}")
    except Exception as e:
        print(f"⚠️  QR card failed: {e}")
        qr_card_path = None

    try:
        make_banner_bg(banner_bg_path, brand_color_hex=args.brand_color,
                       width=1860, height=155, radius=22, all_corners=True)
        print(f"✅ Banner background: {banner_bg_path.name}")
    except Exception as e:
        print(f"⚠️  Banner bg failed: {e}")
        banner_bg_path = None

    if args.logo and Path(args.logo).exists():
        logo_plate_path = job_dir / "logo_plate.png"
        try:
            make_logo_plate(args.logo, logo_plate_path,
                            brand_color_hex=args.brand_color, target_logo_h=100)
            print(f"✅ Logo plate: {logo_plate_path.name}")
        except Exception as e:
            print(f"⚠️  Logo plate failed: {e}")
            logo_plate_path = None

    if args.ask_stamp:
        ask_overlay_path = job_dir / "ask_overlay.png"
        try:
            make_ask_overlay(ask_overlay_path, brand_color_hex=args.brand_color,
                             amount_text=args.ask_stamp)
            print(f"✅ Ask overlay: {ask_overlay_path.name}")
        except Exception as e:
            print(f"⚠️  Ask overlay failed: {e}")
            ask_overlay_path = None

    # Step 1: Script (hand-written file > reuse > Ollama)
    script_path = job_dir / "script.json"
    if args.script and Path(args.script).exists():
        script_data = json.loads(Path(args.script).read_text())
        script_path.write_text(json.dumps(script_data, indent=2))
        print(f"✅ Script loaded from file: {args.script}")
    elif reuse_dir and script_path.exists():
        script_data = json.loads(script_path.read_text())
        print("♻️  Reusing existing script")
    else:
        script_data = write_script(args.org, args.cause, args.ask, args.url)
        script_path.write_text(json.dumps(script_data, indent=2))
        print("✅ Script written")
    for i in range(1, 6):
        key = f"scene{i}_" + {1:"hook", 2:"problem", 3:"stakes", 4:"solution", 5:"ask"}[i]
        print(f"   Scene {i}: {str(script_data.get(key,''))[:80]}...")

    # Step 2-4: Per-scene pipeline
    scene_durations = {1: 8, 2: 12, 3: 15, 4: 15, 5: 10}
    scene_files = []

    for i in range(1, 6):
        scene_name = {1:"hook", 2:"problem", 3:"stakes", 4:"solution", 5:"ask"}[i]
        text = script_data[f"scene{i}_{scene_name}"]
        keywords = script_data.get(f"keywords_scene{i}", [])
        target_duration = scene_durations[i]

        print(f"\n🎬 Scene {i} ({scene_name}) — {target_duration}s")
        scene_dir = job_dir / f"scene{i}"
        scene_dir.mkdir(exist_ok=True)

        # B-roll (reuse if existing)
        existing_broll = sorted(scene_dir.glob("broll_*.mp4"))
        if existing_broll:
            broll = existing_broll
            print(f"  ♻️  Reusing existing b-roll: {broll[0].name}")
        else:
            broll = fetch_broll(keywords, scene_dir, count=5)

        # Narration (reuse if existing — skip TTS charge)
        narration_wav = scene_dir / "narration.wav"
        if narration_wav.exists() and narration_wav.stat().st_size > 1000:
            print(f"  ♻️  Reusing existing narration (no TTS charge)")
        else:
            narrate_scene(text, narration_wav)
        narration_dur = probe_duration(narration_wav)
        # Use whichever is longer — narration dominates
        scene_dur = max(target_duration, narration_dur + 0.5)

        # Assemble scene with pre-baked branded lower-third package
        # (banner bg + logo plate + QR card + contact text + scene-5-only ask overlay
        #  + per-scene timed callouts from the script JSON)
        scene_mp4 = scene_dir / "scene.mp4"
        scene_ask_path = ask_overlay_path if (ask_overlay_path and i == 5) else None

        # Generate per-scene timed callout PNGs from the script's sceneN_overlays field
        # Supports two styles:
        #   "two-tone" (default) — use make_scene_overlay with pipe-separated lines
        #     spec keys: lines, in, out, pos | OR x, y
        #   "bullet" — use make_scene_bullet with head + optional sub
        #     spec keys: style="bullet", head, sub, in, out, x, y
        scene_overlay_list = []
        overlays_spec = script_data.get(f"scene{i}_overlays", [])
        for ov_idx, ov in enumerate(overlays_spec):
            ov_png = scene_dir / f"overlay_{ov_idx+1}.png"
            try:
                style = ov.get("style", "two-tone")
                if style == "bullet":
                    make_scene_bullet(
                        ov_png, args.brand_color,
                        head=ov.get("head", ""),
                        sub=ov.get("sub", ""),
                    )
                    label = f"{ov.get('head','')}/{ov.get('sub','')}"
                else:
                    make_scene_overlay(ov_png, args.brand_color, ov.get("lines", ""))
                    label = ov.get("lines", "")

                entry = {
                    "path": str(ov_png),
                    "in": ov.get("in", 0.0),
                    "out": ov.get("out", scene_dur),
                    "pos": ov.get("pos", "right-nose"),
                }
                # Explicit x/y override the pos keyword
                if "x" in ov:
                    entry["x"] = ov["x"]
                if "y" in ov:
                    entry["y"] = ov["y"]
                scene_overlay_list.append(entry)
                print(f"   📝 Scene {i} overlay {ov_idx+1} ({style}): "
                      f"{label} ({ov.get('in', 0)}→{ov.get('out', 0)}s)")
            except Exception as e:
                print(f"   ⚠️  Overlay {ov_idx+1} failed: {e}")

        # Pre-assemble b-roll: concat multiple clips (each ≤5s) into one video
        if len(broll) > 1:
            prebuilt = scene_dir / "_compiled_broll.mp4"
            result = prebuild_broll(broll, scene_dur, prebuilt, clip_max=5.0)
            broll_input = [prebuilt] if result else broll
        else:
            broll_input = broll

        assemble_scene(
            broll_input, narration_wav, scene_mp4, scene_dur,
            banner_line1=banner_line1,
            banner_line2=banner_line2,
            banner_bg_path=banner_bg_path,
            logo_plate_path=logo_plate_path,
            qr_card_path=qr_card_path,
            brand_color=args.brand_color,
            ask_overlay_path=scene_ask_path,
            ask_stamp_at=args.ask_stamp_at,
            scene_overlays=scene_overlay_list,
        )
        scene_files.append(scene_mp4)
        print(f"   ✓ {scene_dur:.1f}s")

    # Step 5: Build final card if requested
    final_card_path = None
    if args.final_music and Path(args.final_music).exists():
        print(f"\n🎻 Building final card with {Path(args.final_music).name}")
        bullets = [b.strip() for b in args.bullets.split("|")] if args.bullets else None
        # Longer duration if bullets so they have time to drop in
        final_duration = 12 if bullets else 9
        final_card_path = build_final_card(
            job_dir=job_dir,
            org=args.org,
            url=args.url,
            phone=args.phone,
            qr_badge_path=qr_card_path,  # reuse the new SCAN-TO-GIVE card
            final_music=args.final_music,
            duration=final_duration,
            bullets=bullets,
            hero_image=args.hero_image if args.hero_image else None,
            logo_path=args.logo if args.logo else None,
            logo_plate_path=logo_plate_path,
            brand_color=args.brand_color,
            tagline=args.tagline if args.tagline else None,
            credit_tag=args.credit_tag if args.credit_tag else None,
            credit_sub=args.credit_sub if args.credit_sub else None,
        )

    # Step 6: Concat with optional music bed + final card
    # Auto-version the output filename so reruns never overwrite
    version = 1
    while (job_dir / f"fundraiser_v{version}.mp4").exists():
        version += 1
    final = job_dir / f"fundraiser_v{version}.mp4"
    print(f"\n🔗 Concatenating scenes → {final.name}")
    music_path = args.music if args.music else None
    if music_path:
        print(f"   🎵 Mixing music: {Path(music_path).name}")
    # Optional: build rolling credits segment (appended after final card)
    credits_segment_path = None
    if args.rolling_credits:
        credits_spec = script_data.get("rolling_credits", [])
        if credits_spec:
            try:
                print(f"\n📜 Building rolling credits segment ({args.credits_duration}s)...")
                credits_segment_path = build_credits_segment(
                    job_dir=job_dir,
                    sections=credits_spec,
                    brand_color=args.brand_color,
                    duration=args.credits_duration,
                )
                print(f"   ✅ Credits segment: {credits_segment_path.name}")
            except Exception as e:
                print(f"   ⚠️  Rolling credits failed: {e}")
                credits_segment_path = None
        else:
            print("   ⚠️  --rolling-credits set but script JSON has no 'rolling_credits' section")

    # Optional: build 'Look Mom, No Hands Productions' closing bumper (1.5s)
    bumper_segment_path = None
    if args.bumper:
        try:
            print(f"\n🚴 Building Look Mom No Hands Productions bumper...")
            bumper_segment_path = build_bumper_segment(
                job_dir=job_dir,
                brand_color=args.brand_color,
                duration=1.5,
                black_hold=1.0,
                crash_sound_path=args.bumper_crash if args.bumper_crash else None,
            )
            print(f"   ✅ Bumper: {bumper_segment_path.name}")
        except Exception as e:
            print(f"   ⚠️  Bumper failed: {e}")
            bumper_segment_path = None

    concat_scenes(
        scene_files, final,
        music_path=music_path,
        final_card=final_card_path,
        final_music=args.final_music if args.final_music else None,
        credits_segment=credits_segment_path,
        bumper_segment=bumper_segment_path,
    )

    # Soft captions — Whisper SRT muxed as mov_text subtitle track
    if not getattr(args, "no_captions", False):
        try:
            add_soft_captions(final, model_size=getattr(args, "caption_model", "base"))
        except Exception as e:
            print(f"   ⚠️  Caption step failed (continuing): {e}")

    # Copy to user-facing folder with a clean, dated name
    user_stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    user_name = f"{args.org.replace(' ', '_')}_{user_stamp}_v{version}.mp4"
    user_copy = USER_OUT_DIR / user_name
    shutil.copy2(final, user_copy)
    srt_final = final.with_suffix(".srt")
    if srt_final.exists():
        shutil.copy2(srt_final, user_copy.with_suffix(".srt"))
    print(f"   📂 Copied to: {user_copy}")

    # Step 7: Optional vertical build (same assets, different canvas)
    if args.vertical or args.only_vertical:
        print(f"\n📱 Building VERTICAL (1080x1920) version from reused assets...")

        # Generate vertical-specific branded assets (smaller than landscape versions)
        banner_bg_v_path = job_dir / "banner_bg_v.png"
        logo_plate_v_path = None
        qr_card_v_path = qr_card_path  # reuse the same QR card — ffmpeg will scale it

        try:
            make_banner_bg(banner_bg_v_path, brand_color_hex=args.brand_color,
                           width=1020, height=200, radius=20, all_corners=True)
            print(f"   ✅ Vertical banner bg: {banner_bg_v_path.name}")
        except Exception as e:
            print(f"   ⚠️  Vertical banner failed: {e}")
            banner_bg_v_path = None

        if args.logo and Path(args.logo).exists():
            logo_plate_v_path = job_dir / "logo_plate_v.png"
            try:
                # Smaller logo for vertical: 55px tall → plate ~280px wide.
                # Must stay narrow enough that contact text has room in 1020 banner.
                make_logo_plate(args.logo, logo_plate_v_path,
                                brand_color_hex=args.brand_color, target_logo_h=55)
                print(f"   ✅ Vertical logo plate: {logo_plate_v_path.name}")
            except Exception as e:
                print(f"   ⚠️  Vertical logo plate failed: {e}")
                logo_plate_v_path = None

        vertical_scene_files = []
        for i in range(1, 6):
            scene_name = {1: "hook", 2: "problem", 3: "stakes", 4: "solution", 5: "ask"}[i]
            scene_dir = job_dir / f"scene{i}"

            existing_broll = sorted(scene_dir.glob("broll_*.mp4"))
            if not existing_broll:
                print(f"   ⚠️ Scene {i} missing b-roll, skipping")
                continue
            narration_wav = scene_dir / "narration.wav"
            if not narration_wav.exists():
                print(f"   ⚠️ Scene {i} missing narration, skipping")
                continue

            narration_dur = probe_duration(narration_wav)
            scene_duration = max(scene_durations[i], narration_dur + 0.5)

            # Reuse the per-scene overlay PNGs that the landscape pass generated
            # (they live at scene_dir / overlay_N.png). Vertical assembler
            # re-positions them to centered/stacked — ignores the landscape x/y.
            v_scene_overlay_list = []
            v_overlays_spec = script_data.get(f"scene{i}_overlays", [])
            for ov_idx_v, ov_spec in enumerate(v_overlays_spec):
                ov_png = scene_dir / f"overlay_{ov_idx_v+1}.png"
                if ov_png.exists():
                    v_scene_overlay_list.append({
                        "path": str(ov_png),
                        "in": ov_spec.get("in", 0.0),
                        "out": ov_spec.get("out", scene_duration),
                    })

            v_ask_path = ask_overlay_path if (ask_overlay_path and i == 5) else None

            # Vertical uses 3-line banner: org name / URL / phone (separated)
            # instead of landscape's 2-line "org / phone • URL" combo.
            v_line2 = args.url
            v_line3 = f"Call {args.phone}" if args.phone else ""

            # Pre-compile broll for vertical (same fix as landscape path)
            if len(existing_broll) > 1:
                prebuilt_v = scene_dir / "_compiled_broll_v.mp4"
                result_v = prebuild_broll(existing_broll, scene_duration, prebuilt_v, clip_max=5.0)
                v_broll_input = [prebuilt_v] if result_v else existing_broll
            else:
                v_broll_input = existing_broll

            scene_v = scene_dir / "scene_vertical.mp4"
            assemble_scene_vertical(
                v_broll_input, narration_wav, scene_v, scene_duration,
                banner_line1=banner_line1,
                banner_line2=v_line2,
                banner_line3=v_line3,
                banner_bg_v_path=banner_bg_v_path,
                logo_plate_v_path=logo_plate_v_path,
                qr_card_v_path=qr_card_v_path,
                brand_color=args.brand_color,
                ask_overlay_path=v_ask_path,
                ask_stamp_at=args.ask_stamp_at,
                scene_overlays=v_scene_overlay_list,
            )
            vertical_scene_files.append(scene_v)
            print(f"   ✓ scene{i} vertical ({scene_duration:.1f}s)")

        # Concat vertical scenes with music
        # Path B: no scene overlays, no rolling credits, no bumper in vertical —
        # keep it tight for short-form platforms.
        version_v = 1
        while (job_dir / f"fundraiser_vertical_v{version_v}.mp4").exists():
            version_v += 1
        final_vertical = job_dir / f"fundraiser_vertical_v{version_v}.mp4"
        concat_scenes(
            vertical_scene_files, final_vertical,
            music_path=music_path,
            final_card=None,
            final_music=None,
        )

        v_user_name = f"{args.org.replace(' ', '_')}_{user_stamp}_vertical_v{version_v}.mp4"
        v_user_copy = USER_OUT_DIR / v_user_name
        shutil.copy2(final_vertical, v_user_copy)
        print(f"   📂 Vertical saved: {v_user_copy}")

    dur = probe_duration(final)
    size_mb = final.stat().st_size / 1024 / 1024
    print(f"\n✅ DONE")
    print(f"   File: {final}")
    print(f"   Duration: {dur:.1f}s")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"   Cost: $0.00")


if __name__ == "__main__":
    main()
