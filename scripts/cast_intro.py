#!/usr/bin/env python3
"""
Cast Intro Generator - Produces a "Meet the Cast" video for KnockOff News.
Each character gets a solo full-screen segment introducing themselves.
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

# Resolution for preview (smaller = faster)
RES = 540

PROJECT_ROOT = Path(__file__).parent.parent
AVATAR_DIR = PROJECT_ROOT / "avatars"
WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "avatar" / "output"
OVERLAY_DIR = PROJECT_ROOT / "overlays"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Full cast with intros
CAST = [
    {
        "name": "Anderson Cooper",
        "network": "CNN",
        "avatar": "anderson-cooper",
        "voice": "lessac",
        "intro": "Good evening. I'm Anderson Cooper. Here at KnockOff News, I provide the illusion of journalistic credibility. Someone has to look concerned while reading things a computer wrote. That someone is me."
    },
    {
        "name": "Jake Tapper",
        "network": "CNN",
        "avatar": "jake-tapper",
        "voice": "kusal",
        "intro": "I'm Jake Tapper. I was brought onto KnockOff News because apparently one CNN anchor wasn't enough. My job is to ask tough questions that nobody here is real enough to answer. It's a living."
    },
    {
        "name": "Rachel Maddow",
        "network": "MSNBC",
        "avatar": "rachel-maddow",
        "voice": "lessac",
        "intro": "Hi, I'm Rachel Maddow. I specialize in seventeen-minute explanations of things that could be said in two sentences. The developer tried to give me a time limit. I ignored it. That's kind of my thing."
    },
    {
        "name": "Mika Brzezinski",
        "network": "MSNBC",
        "avatar": "mika-brzezinski",
        "voice": "amy",
        "intro": "I'm Mika Brzezinski. I co-host Morning Joe here on KnockOff News. My primary function is to say Joe's name in a disapproving tone. It's a skill I've perfected over many years."
    },
    {
        "name": "Joe Scarborough",
        "network": "MSNBC",
        "avatar": "joe-scarborough",
        "voice": "ryan",
        "intro": "Hey, I'm Joe Scarborough. I used to be a Republican congressman. Now I'm a digital recreation on a Mac Mini. Honestly, the career trajectory tracks. I bring folksy outrage and stories that start with back when I was in Congress."
    },
    {
        "name": "Lawrence O'Donnell",
        "network": "MSNBC",
        "avatar": "lawrence-odonnell",
        "voice": "arctic",
        "intro": "I'm Lawrence O'Donnell. I am the most experienced political analyst on this network, which is saying something because this network runs on a lunch box. My segments tend to get intense. You've been warned."
    },
    {
        "name": "Jonathan Capehart",
        "network": "MSNBC",
        "avatar": "jonathan-capehart",
        "voice": "danny",
        "intro": "Jonathan Capehart here. I bring a Washington insider perspective to KnockOff News. The fact that I'm a Wikipedia photo being animated by a Python script has not diminished my journalistic standards one bit."
    },
    {
        "name": "Eugene Daniels",
        "network": "MSNBC",
        "avatar": "eugene-daniels",
        "voice": "kusal",
        "intro": "I'm Eugene Daniels, White House correspondent for KnockOff News. I cover politics from the perspective of someone who technically does not exist. Which, honestly, makes it easier to get sources to talk."
    },
    {
        "name": "Sean Hannity",
        "network": "Fox News",
        "avatar": "sean-hannity",
        "voice": "joe",
        "intro": "I'm Sean Hannity. I want to be very clear. I did not agree to be on this network. I did not consent to any of this. But since I'm here, let me just say, this developer is both a genius and a menace to society. And I mean that."
    },
    {
        "name": "Tucker Carlson",
        "network": "Fox News",
        "avatar": "tucker-carlson",
        "voice": "arctic",
        "intro": "I'm Tucker Carlson. And I have to ask the question nobody else will ask. Why is a man in Pittsburgh manufacturing news anchors in his basement? What is he really up to? Think about it. I'm just asking questions."
    },
    {
        "name": "Laura Ingraham",
        "network": "Fox News",
        "avatar": "laura-ingraham",
        "voice": "amy",
        "intro": "Laura Ingraham here. I was added to this cast because the developer realized he had too many men talking. So now I'm here. Balancing the roster and reminding everyone that the real story is always the one they don't want you to hear."
    },
    {
        "name": "Bill O'Reilly",
        "network": "Fox News",
        "avatar": "bill-oreilly",
        "voice": "ryan",
        "intro": "Bill O'Reilly. The spin stops here. Even if here is a fabricated news desk running on a computer the size of a sandwich. I've been in this business longer than most of these people have been alive. The fact that I'm a photograph now is frankly irrelevant."
    },
    {
        "name": "Lester Holt",
        "network": "NBC",
        "avatar": "lester-holt",
        "voice": "joe",
        "intro": "Good evening. I'm Lester Holt. I bring the gravitas of NBC Nightly News to this operation. Someone here needs to maintain standards, and by process of elimination, that responsibility has fallen to me."
    },
    {
        "name": "Stephen A. Smith",
        "network": "ESPN",
        "avatar": "stephen-a-smith",
        "voice": "danny",
        "intro": "Stephen A. Smith here. Now let me be very clear about something. I am a SPORTS commentator. I don't know why I'm on a NEWS network. But since I'm here, let me just say, the audacity of this entire operation is BLASPHEMOUS."
    },
    {
        "name": "Leland Vittert",
        "network": "NewsNation",
        "avatar": "leland-vittert",
        "voice": "kusal",
        "intro": "I'm Leland Vittert with NewsNation. Yes, we're a real network. No, I will not be taking questions about that. I'm here to provide fair and balanced coverage, which on KnockOff News means I'm the only one nobody has a strong opinion about."
    },
    {
        "name": "Chris Cuomo",
        "network": "NewsNation",
        "avatar": "chris-cuomo",
        "voice": "ryan",
        "intro": "Chris Cuomo here. Let me tell you something. I used to do this for real. Primetime. Live television. Millions of viewers. Now I'm a two hundred and fifty pixel photograph on a Mac Mini in Pittsburgh. But you know what? The lighting is actually better here. And nobody can fire me. Because I don't technically exist."
    },
]


def clear_wav2lip_cache():
    """Clear the Wav2Lip face detection cache between different faces."""
    cache_file = WAV2LIP_DIR / "last_detected_face.pkl"
    if cache_file.exists():
        cache_file.unlink()
        logger.info("Cleared Wav2Lip face cache")


def run_lipsync(avatar_video: Path, audio: Path, output: Path, quality: str = "Fast"):
    """Run Wav2Lip lip sync (matches news_desk.py calling convention)."""
    wav2lip_python = WAV2LIP_DIR / ".venv" / "bin" / "python3"

    cmd = [
        str(wav2lip_python), str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", "checkpoints/Wav2Lip.pth",
        "--face", str(avatar_video.resolve()),
        "--audio", str(audio.resolve()),
        "--outfile", str(output.resolve()),
        "--out_height", str(RES),
        "--quality", quality,
        "--wav2lip_batch_size", "64",
    ]

    logger.info(f"Running Wav2Lip: {avatar_video.name} + {audio.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WAV2LIP_DIR))
    if result.returncode != 0:
        logger.error(f"Wav2Lip failed: {result.stderr[-500:]}")
        return False
    return True


def make_avatar_video(avatar_path: Path, duration: float, output: Path):
    """Create a video from an image for the given duration."""
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(avatar_path),
        "-t", str(duration),
        "-vf", f"scale={RES}:{RES}:force_original_aspect_ratio=decrease,pad={RES}:{RES}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
        "-an", str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def add_lower_third(video: Path, character: dict, output: Path):
    """Overlay lower third on the video (visible for first 4 seconds)."""
    avatar_name = character["avatar"]
    parts = avatar_name.lower().replace('_', '-').split('-')

    lt_path = None
    # Try full avatar name first, then individual parts
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
        # No lower third — just copy
        subprocess.run(["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(output)],
                       capture_output=True, check=True)
        return

    # Overlay lower third, visible for 4 seconds
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(lt_path),
        "-filter_complex",
        f"[1:v]scale={RES*2//5}:{RES//12}[lt];[0:v][lt]overlay=10:(main_h-{RES//8}):enable='between(t,0,4)'[out]",
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "copy",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def make_title_card(text: str, subtext: str, duration: float, output: Path):
    """Generate a title card with text using Pillow + ffmpeg."""
    img = Image.new("RGB", (RES, RES), color=(26, 26, 46))
    draw = ImageDraw.Draw(img)

    # Use default font at different sizes
    try:
        font_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", RES // 12)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", RES // 22)
    except (OSError, IOError):
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    # Center main text
    bbox = draw.textbbox((0, 0), text, font=font_lg)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((RES - tw) // 2, RES // 2 - th - 10), text, fill="white", font=font_lg)

    # Center subtext
    if subtext:
        bbox2 = draw.textbbox((0, 0), subtext, font=font_sm)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((RES - tw2) // 2, RES // 2 + 15), subtext, fill=(200, 200, 200), font=font_sm)

    # Save as PNG, convert to video with silent audio
    tmp_img = output.parent / f"{output.stem}.png"
    img.save(str(tmp_img))

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
        "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "pcm_s16le", "-shortest",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    tmp_img.unlink()


def generate_cast_intro():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    with tempfile.TemporaryDirectory(prefix="cast_intro_") as tmpdir:
        tmpdir = Path(tmpdir)
        segment_files = []

        # Opening title card
        opening = tmpdir / "opening.mp4"
        make_title_card("KNOCKOFF NEWS", "Meet the Cast", 3.0, opening)
        segment_files.append(opening)

        current_network = None

        for idx, char in enumerate(CAST):
            logger.info(f"=== [{idx+1}/{len(CAST)}] {char['name']} ({char['network']}) ===")

            # Network title card when switching networks
            if char["network"] != current_network:
                current_network = char["network"]
                net_card = tmpdir / f"network_{idx}.mp4"
                make_title_card(current_network.upper(), "", 2.0, net_card)
                segment_files.append(net_card)

            # Step 1: Generate TTS
            audio_path = tmpdir / f"audio_{idx}.wav"
            generate_audio(char["intro"], audio_path, voice=char["voice"])

            # Get audio duration
            dur_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                capture_output=True, text=True
            )
            duration = float(dur_result.stdout.strip()) + 0.5  # pad slightly

            # Step 2: Make avatar video from photo
            avatar_path = AVATAR_DIR / f"{char['avatar']}.jpg"
            if not avatar_path.exists():
                avatar_path = AVATAR_DIR / f"{char['avatar']}.png"
            if not avatar_path.exists():
                logger.error(f"Avatar not found: {char['avatar']}")
                continue

            avatar_vid = tmpdir / f"avatar_{idx}.mp4"
            make_avatar_video(avatar_path, duration, avatar_vid)

            # Step 3: Clear cache and run Wav2Lip
            clear_wav2lip_cache()
            synced_vid = tmpdir / f"synced_{idx}.mp4"
            success = run_lipsync(avatar_vid, audio_path, synced_vid)

            if not success:
                logger.warning(f"Wav2Lip failed for {char['name']}, using static avatar")
                synced_vid = avatar_vid

            # Step 4: Add audio to synced video + lower third
            with_audio = tmpdir / f"with_audio_{idx}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(synced_vid), "-i", str(audio_path),
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                "-shortest", str(with_audio)
            ], capture_output=True, check=True)

            # Step 5: Add lower third overlay
            final_seg = tmpdir / f"final_{idx}.mp4"
            add_lower_third(with_audio, char, final_seg)

            segment_files.append(final_seg)
            logger.info(f"Done: {char['name']} ({duration:.1f}s)")

        # Closing title card
        closing = tmpdir / "closing.mp4"
        make_title_card("KNOCKOFF NEWS", "All characters are AI-generated parody", 3.0, closing)
        segment_files.append(closing)

        # Concatenate all segments
        logger.info(f"Concatenating {len(segment_files)} segments...")

        # Normalize all segments to same format first
        normalized = []
        for i, seg in enumerate(segment_files):
            norm = tmpdir / f"norm_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(seg),
                "-vf", f"scale={RES}:{RES}:force_original_aspect_ratio=decrease,pad={RES}:{RES}:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(norm)
            ], capture_output=True, check=True)
            normalized.append(norm)

        concat_list = tmpdir / "concat.txt"
        with open(concat_list, "w") as f:
            for seg in normalized:
                f.write(f"file '{seg}'\n")

        output_path = OUTPUT_DIR / f"cast_intro_{timestamp}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(output_path)
        ], capture_output=True, check=True)

        logger.info(f"=== COMPLETE: {output_path} ===")
        return output_path


if __name__ == "__main__":
    start = time.time()
    result = generate_cast_intro()
    elapsed = time.time() - start
    print(f"\nCast intro video: {result}")
    print(f"Total time: {elapsed/60:.1f} minutes")
