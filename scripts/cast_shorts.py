#!/usr/bin/env python3
"""
Cast Intro Shorts Generator - YouTube Shorts (9:16 vertical, <60s each).
One Short per network with branding: intro card + character intros + bumper flash.
"""

import subprocess
import sys
import tempfile
import time
import logging
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from tts import generate_audio

PROJECT_ROOT = Path(__file__).parent.parent
AVATAR_DIR = PROJECT_ROOT / "avatars"
WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
OUTPUT_DIR = PROJECT_ROOT / "output" / "keepers" / "shorts"
OVERLAY_DIR = PROJECT_ROOT / "overlays"
MUSIC_DIR = PROJECT_ROOT / "music"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Portrait 9:16 preview resolution
W = 540
H = 960

# Brand colors (matching intro_card.png style)
BG_COLOR = (26, 26, 46)       # Dark navy
ACCENT_RED = (200, 0, 0)      # Red accent
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (180, 180, 180)

# Network groupings — MSNBC split into two parts
NETWORKS = {
    "CNN": {
        "subtitle": "The Most Trusted Name in Fake News",
        "characters": [
            {
                "name": "Anderson Cooper",
                "avatar": "anderson-cooper",
                "voice": "lessac",
                "intro": "Good evening. I'm Anderson Cooper. Here at KnockOff News, I provide the illusion of journalistic credibility. Someone has to look concerned while reading things a computer wrote. That someone is me."
            },
            {
                "name": "Jake Tapper",
                "avatar": "jake-tapper",
                "voice": "kusal",
                "intro": "I'm Jake Tapper. I was brought onto KnockOff News because apparently one CNN anchor wasn't enough. My job is to ask tough questions that nobody here is real enough to answer. It's a living."
            },
        ]
    },
    "MSNBC Part 1": {
        "subtitle": "Lean Forward. Into the Uncanny Valley.",
        "characters": [
            {
                "name": "Rachel Maddow",
                "avatar": "rachel-maddow",
                "voice": "lessac",
                "intro": "Hi, I'm Rachel Maddow. I specialize in seventeen-minute explanations of things that could be said in two sentences. The developer tried to give me a time limit. I ignored it. That's kind of my thing."
            },
            {
                "name": "Mika Brzezinski",
                "avatar": "mika-brzezinski",
                "voice": "amy",
                "intro": "I'm Mika Brzezinski. I co-host Morning Joe here on KnockOff News. My primary function is to say Joe's name in a disapproving tone. It's a skill I've perfected over many years."
            },
            {
                "name": "Joe Scarborough",
                "avatar": "joe-scarborough",
                "voice": "ryan",
                "intro": "Hey, I'm Joe Scarborough. I used to be a Republican congressman. Now I'm a digital recreation on a Mac Mini. Honestly, the career trajectory tracks. I bring folksy outrage and stories that start with back when I was in Congress."
            },
        ]
    },
    "MSNBC Part 2": {
        "subtitle": "Lean Forward. Into the Uncanny Valley.",
        "characters": [
            {
                "name": "Lawrence O'Donnell",
                "avatar": "lawrence-odonnell",
                "voice": "arctic",
                "intro": "I'm Lawrence O'Donnell. I am the most experienced political analyst on this network, which is saying something because this network runs on a lunch box. My segments tend to get intense. You've been warned."
            },
            {
                "name": "Jonathan Capehart",
                "avatar": "jonathan-capehart",
                "voice": "danny",
                "intro": "Jonathan Capehart here. I bring a Washington insider perspective to KnockOff News. The fact that I'm a Wikipedia photo being animated by a Python script has not diminished my journalistic standards one bit."
            },
            {
                "name": "Eugene Daniels",
                "avatar": "eugene-daniels",
                "voice": "kusal",
                "intro": "I'm Eugene Daniels, White House correspondent for KnockOff News. I cover politics from the perspective of someone who technically does not exist. Which, honestly, makes it easier to get sources to talk."
            },
        ]
    },
    "Fox News": {
        "subtitle": "Fair. Balanced. Artificially Generated.",
        "characters": [
            {
                "name": "Sean Hannity",
                "avatar": "sean-hannity",
                "voice": "joe",
                "intro": "I'm Sean Hannity. I want to be very clear. I did not agree to be on this network. I did not consent to any of this. But since I'm here, let me just say, this developer is both a genius and a menace to society. And I mean that."
            },
            {
                "name": "Tucker Carlson",
                "avatar": "tucker-carlson",
                "voice": "arctic",
                "intro": "I'm Tucker Carlson. And I have to ask the question nobody else will ask. Why is a man in Pittsburgh manufacturing news anchors in his basement? What is he really up to? Think about it. I'm just asking questions."
            },
            {
                "name": "Laura Ingraham",
                "avatar": "laura-ingraham",
                "voice": "amy",
                "intro": "Laura Ingraham here. I was added to this cast because the developer realized he had too many men talking. So now I'm here. Balancing the roster and reminding everyone that the real story is always the one they don't want you to hear."
            },
            {
                "name": "Bill O'Reilly",
                "avatar": "bill-oreilly",
                "voice": "ryan",
                "intro": "Bill O'Reilly. The spin stops here. Even if here is a fabricated news desk running on a computer the size of a sandwich. I've been in this business longer than most of these people have been alive. The fact that I'm a photograph now is frankly irrelevant."
            },
        ]
    },
    "The Independents": {
        "subtitle": "No Network. No Rules. No Budget.",
        "characters": [
            {
                "name": "Lester Holt",
                "avatar": "lester-holt",
                "voice": "joe",
                "network_label": "NBC",
                "intro": "Good evening. I'm Lester Holt. I bring the gravitas of NBC Nightly News to this operation. Someone here needs to maintain standards, and by process of elimination, that responsibility has fallen to me."
            },
            {
                "name": "Stephen A. Smith",
                "avatar": "stephen-a-smith",
                "voice": "danny",
                "network_label": "ESPN",
                "intro": "Stephen A. Smith here. Now let me be very clear about something. I am a SPORTS commentator. I don't know why I'm on a NEWS network. But since I'm here, let me just say, the audacity of this entire operation is BLASPHEMOUS."
            },
            {
                "name": "Leland Vittert",
                "avatar": "leland-vittert",
                "voice": "kusal",
                "network_label": "NewsNation",
                "intro": "I'm Leland Vittert with NewsNation. Yes, we're a real network. No, I will not be taking questions about that. I'm here to provide fair and balanced coverage, which on KnockOff News means I'm the only one nobody has a strong opinion about."
            },
            {
                "name": "Chris Cuomo",
                "avatar": "chris-cuomo",
                "voice": "ryan",
                "network_label": "NewsNation",
                "intro": "Chris Cuomo here. Let me tell you something. I used to do this for real. Primetime. Live television. Millions of viewers. Now I'm a two hundred and fifty pixel photograph on a Mac Mini in Pittsburgh. But you know what? The lighting is actually better here. And nobody can fire me. Because I don't technically exist."
            },
        ]
    },
}


def clear_wav2lip_cache():
    cache_file = WAV2LIP_DIR / "last_detected_face.pkl"
    if cache_file.exists():
        cache_file.unlink()


def run_lipsync(avatar_video: Path, audio: Path, output: Path):
    wav2lip_python = WAV2LIP_DIR / ".venv" / "bin" / "python3"
    cmd = [
        str(wav2lip_python), str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", "checkpoints/Wav2Lip.pth",
        "--face", str(avatar_video.resolve()),
        "--audio", str(audio.resolve()),
        "--outfile", str(output.resolve()),
        "--out_height", str(H),
        "--quality", "Fast",
        "--wav2lip_batch_size", "64",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WAV2LIP_DIR))
    return result.returncode == 0


def make_avatar_video(avatar_path: Path, duration: float, output: Path):
    """Create portrait video from photo — face centered in upper portion."""
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(avatar_path),
        "-t", str(duration),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
        "-an", str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def make_intro_card(network_name: str, subtitle: str, duration: float, output: Path):
    """Generate vertical intro card with KnockOff News branding."""
    img = Image.new("RGB", (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_breaking = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 16)
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 9)
        font_network = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 14)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 24)
        font_meet = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 18)
    except (OSError, IOError):
        font_breaking = font_title = font_network = font_sub = font_meet = ImageFont.load_default()

    # "BREAKING" in red
    text = "BREAKING"
    bbox = draw.textbbox((0, 0), text, font=font_breaking)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 4 - 60), text, fill=ACCENT_RED, font=font_breaking)

    # "KNOCKOFF NEWS"
    text = "KNOCKOFF"
    bbox = draw.textbbox((0, 0), text, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 4), text, fill=TEXT_WHITE, font=font_title)

    text = "NEWS"
    bbox = draw.textbbox((0, 0), text, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 4 + 60), text, fill=TEXT_WHITE, font=font_title)

    # Red bar
    bar_y = H // 2 - 20
    draw.rectangle([0, bar_y, W, bar_y + 40], fill=ACCENT_RED)

    # "Fair. Balanced. Completely Made Up." on the bar
    tagline = "Fair. Balanced. Completely Made Up."
    bbox = draw.textbbox((0, 0), tagline, font=font_sub)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, bar_y + 8), tagline, fill=TEXT_WHITE, font=font_sub)

    # "Meet the Cast" below bar
    text = "Meet the Cast"
    bbox = draw.textbbox((0, 0), text, font=font_meet)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 + 50), text, fill=TEXT_GRAY, font=font_meet)

    # Network name
    # Clean up display name (remove "Part 1" etc for display)
    display_name = network_name.replace(" Part 1", "").replace(" Part 2", "")
    bbox = draw.textbbox((0, 0), display_name, font=font_network)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 + 100), display_name, fill=TEXT_WHITE, font=font_network)

    # Subtitle
    bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 + 150), subtitle, fill=TEXT_GRAY, font=font_sub)

    tmp_img = output.parent / f"{output.stem}_intro.png"
    img.save(str(tmp_img))

    # Add news sting audio
    news_sting = MUSIC_DIR / "news_sting.wav"
    if news_sting.exists():
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
            "-i", str(news_sting),
            "-t", str(duration),
            "-vf", f"scale={W}:{H}",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-shortest",
            str(output)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
            "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "pcm_s16le", "-shortest",
            str(output)
        ]
    subprocess.run(cmd, capture_output=True, check=True)
    tmp_img.unlink()


def make_outro_card(duration: float, output: Path):
    """1-second bumper frame flash + satire text, vertical."""
    bumper_frame = OVERLAY_DIR / "bumper_frame.png"

    img = Image.new("RGB", (W, H), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load and paste bumper frame in upper portion
    if bumper_frame.exists():
        bumper = Image.open(str(bumper_frame))
        # Scale to fit width, maintain aspect
        scale = W / bumper.width
        new_h = int(bumper.height * scale)
        bumper = bumper.resize((W, new_h), Image.LANCZOS)
        paste_y = (H // 2) - (new_h // 2) - 60
        img.paste(bumper, (0, max(0, paste_y)))

    try:
        font_satire = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 22)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", W // 30)
    except (OSError, IOError):
        font_satire = font_small = ImageFont.load_default()

    # Satire disclaimer at bottom
    draw.text((W // 2 - 80, H - 120), "SATIRE / PARODY", fill=ACCENT_RED, font=font_satire)
    disclaimer = "All characters are AI-generated"
    bbox = draw.textbbox((0, 0), disclaimer, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H - 70), disclaimer, fill=TEXT_GRAY, font=font_small)

    tmp_img = output.parent / f"{output.stem}_outro.png"
    img.save(str(tmp_img))

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
        "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "pcm_s16le", "-shortest",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    tmp_img.unlink()


def add_lower_third(video: Path, character: dict, output: Path):
    """Overlay lower third on portrait video."""
    avatar_name = character["avatar"]
    parts = avatar_name.lower().replace('_', '-').split('-')

    lt_path = None
    full_candidate = OVERLAY_DIR / f"lower_third_{avatar_name.lower().replace('_', '-')}.png"
    if full_candidate.exists():
        lt_path = full_candidate
    else:
        for part in parts:
            candidate = OVERLAY_DIR / f"lower_third_{part}.png"
            if candidate.exists():
                lt_path = candidate
                break

    if lt_path is None:
        subprocess.run(["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(output)],
                       capture_output=True, check=True)
        return

    lt_w = W - 20
    lt_h = H // 16
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(lt_path),
        "-filter_complex",
        f"[1:v]scale={lt_w}:{lt_h}[lt];[0:v][lt]overlay=10:(main_h-{H//7}):enable='between(t,0,4)'[out]",
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "copy",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def generate_network_short(network_name: str, network_config: dict, tmpdir: Path) -> Path:
    """Generate one YouTube Short for a network."""
    logger.info(f"{'='*60}")
    logger.info(f"Generating Short: {network_name}")
    logger.info(f"{'='*60}")

    characters = network_config["characters"]
    subtitle = network_config["subtitle"]
    segment_files = []

    # 1. Intro card with news sting (2.5 seconds)
    intro = tmpdir / f"intro_{network_name}.mp4"
    make_intro_card(network_name, subtitle, 2.5, intro)
    segment_files.append(intro)

    # 2. Character segments
    for idx, char in enumerate(characters):
        logger.info(f"  [{idx+1}/{len(characters)}] {char['name']}")

        # TTS
        audio_path = tmpdir / f"audio_{network_name}_{idx}.wav"
        generate_audio(char["intro"], audio_path, voice=char["voice"])
        duration = get_audio_duration(audio_path) + 0.5

        # Avatar video
        avatar_path = AVATAR_DIR / f"{char['avatar']}.jpg"
        if not avatar_path.exists():
            avatar_path = AVATAR_DIR / f"{char['avatar']}.png"
        if not avatar_path.exists():
            logger.error(f"  Avatar not found: {char['avatar']}")
            continue

        avatar_vid = tmpdir / f"avatar_{network_name}_{idx}.mp4"
        make_avatar_video(avatar_path, duration, avatar_vid)

        # Wav2Lip
        clear_wav2lip_cache()
        synced_vid = tmpdir / f"synced_{network_name}_{idx}.mp4"
        success = run_lipsync(avatar_vid, audio_path, synced_vid)
        if not success:
            logger.warning(f"  Wav2Lip failed for {char['name']}, using static")
            synced_vid = avatar_vid

        # Add audio
        with_audio = tmpdir / f"audio_{network_name}_{idx}_merged.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(synced_vid), "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
            "-shortest", str(with_audio)
        ], capture_output=True, check=True)

        # Lower third
        final_seg = tmpdir / f"final_{network_name}_{idx}.mp4"
        add_lower_third(with_audio, char, final_seg)
        segment_files.append(final_seg)

        seg_dur = get_audio_duration(final_seg)
        logger.info(f"  Done: {char['name']} ({seg_dur:.1f}s)")

    # 3. Outro bumper flash (1 second)
    outro = tmpdir / f"outro_{network_name}.mp4"
    make_outro_card(1.0, outro)
    segment_files.append(outro)

    # Normalize and concatenate
    normalized = []
    for i, seg in enumerate(segment_files):
        norm = tmpdir / f"norm_{network_name}_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(seg),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(norm)
        ], capture_output=True, check=True)
        normalized.append(norm)

    concat_list = tmpdir / f"concat_{network_name}.txt"
    with open(concat_list, "w") as f:
        for seg in normalized:
            f.write(f"file '{seg}'\n")

    # Clean filename
    safe_name = network_name.lower().replace(" ", "_")
    output_path = OUTPUT_DIR / f"cast_intro_{safe_name}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        str(output_path)
    ], capture_output=True, check=True)

    final_dur = get_audio_duration(output_path)
    logger.info(f"  => {output_path.name} ({final_dur:.1f}s)")

    if final_dur > 60:
        logger.warning(f"  WARNING: {network_name} is {final_dur:.1f}s — exceeds 60s Shorts limit!")

    return output_path


def generate_all_shorts():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cast_shorts_") as tmpdir:
        tmpdir = Path(tmpdir)
        results = []

        for network_name, network_config in NETWORKS.items():
            start = time.time()
            output = generate_network_short(network_name, network_config, tmpdir)
            elapsed = time.time() - start
            duration = get_audio_duration(output)
            results.append({
                "network": network_name,
                "file": output,
                "duration": duration,
                "render_time": elapsed,
            })

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("ALL SHORTS COMPLETE")
        logger.info(f"{'='*60}")
        total_render = 0
        for r in results:
            status = "OK" if r["duration"] <= 60 else "OVER 60s!"
            logger.info(f"  {r['network']:20s} | {r['duration']:5.1f}s | rendered in {r['render_time']/60:.1f}m | {status}")
            total_render += r["render_time"]
        logger.info(f"  Total render time: {total_render/60:.1f} minutes")
        logger.info(f"  Output: {OUTPUT_DIR}")

        return results


if __name__ == "__main__":
    start = time.time()
    generate_all_shorts()
    print(f"\nTotal time: {(time.time() - start)/60:.1f} minutes")
