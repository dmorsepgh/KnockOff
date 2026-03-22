#!/usr/bin/env python3
"""
Video Assembler - Combine lip-synced avatar with broll, overlays, CTAs, and music.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    ColorClip,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.fx.resize import resize

from parse_script import Segment, MusicTrack

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

FORMATS = {
    "portrait":  (1080, 1920),
    "landscape": (1920, 1080),
    "square":    (1080, 1080),
}

# PIP corner position for overlay mode (bottom-left)
PIP_SCALE = 0.35       # avatar shrinks to 35% of frame width
PIP_MARGIN = 30        # pixels from edge


def _parse_volume_db(volume_str: str) -> float:
    """Convert '-12dB' style string to a 0–1 moviepy factor."""
    s = volume_str.lower().replace("db", "").strip()
    try:
        db = float(s)
    except ValueError:
        db = -12.0
    # Convert dB to linear factor: factor = 10^(dB/20)
    return 10 ** (db / 20)


def _fit_clip(clip, target_w: int, target_h: int):
    """Resize and crop clip to fill target dimensions exactly."""
    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h

    if clip_ratio > target_ratio:
        # Clip is wider — fit by height, crop sides
        clip = clip.resize(height=target_h)
    else:
        # Clip is taller — fit by width, crop top/bottom
        clip = clip.resize(width=target_w)

    # Center crop
    x_center = clip.w / 2
    y_center = clip.h / 2
    clip = clip.crop(
        x_center=x_center, y_center=y_center,
        width=target_w, height=target_h
    )
    return clip


def _make_cta_clip(main_text: str, subtext: str, duration: float, w: int, h: int):
    """Create a CTA text overlay clip (white text, centered)."""
    from moviepy.editor import TextClip
    clips = []

    main = TextClip(
        main_text,
        fontsize=72,
        color="white",
        font="Arial-Bold",
        stroke_color="black",
        stroke_width=2,
    ).set_duration(duration)
    main = main.set_position(("center", h // 2 - 60))
    clips.append(main)

    if subtext:
        sub = TextClip(
            subtext,
            fontsize=48,
            color="white",
            font="Arial",
            stroke_color="black",
            stroke_width=1,
        ).set_duration(duration)
        sub = sub.set_position(("center", h // 2 + 20))
        clips.append(sub)

    return clips


def assemble(
    avatar_video: Path,
    segments: list[Segment],
    output_path: Path,
    music_track: Optional[MusicTrack] = None,
    format: str = "portrait",
) -> Path:
    """
    Assemble the final video from a lip-synced avatar and script segments.

    Args:
        avatar_video: Path to lip-synced avatar video
        segments: Parsed script segments from parse_script.py
        output_path: Where to save the final .mp4
        music_track: Optional background music
        format: "portrait", "landscape", or "square"

    Returns:
        Path to the output video
    """
    avatar_video = Path(avatar_video)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format not in FORMATS:
        raise ValueError(f"format must be one of {list(FORMATS.keys())}")

    target_w, target_h = FORMATS[format]
    logger.info(f"Assembling {format} video ({target_w}x{target_h})")

    # Load avatar — will be looped or trimmed as needed per speech segment
    avatar_source = VideoFileClip(str(avatar_video))
    avatar_duration = avatar_source.duration

    # Track position in avatar for speech segments
    avatar_pos = 0.0

    clips = []
    speech_segments = [s for s in segments if s.type == "speech"]
    speech_idx = 0

    for seg in segments:

        if seg.type == "speech":
            # Each speech segment: slice the avatar to the speech portion
            # (The avatar was lip-synced to the full speech audio, so we
            #  advance through it sequentially.)
            # For now, use the full avatar for every speech segment and let
            # generate.py handle timing. We mark it and stitch below.
            # Simpler: treat the avatar as one continuous clip across all speech.
            speech_idx += 1
            continue  # handled after loop

        elif seg.type == "broll":
            broll_path = PROJECT_ROOT / "broll" / seg.content
            if not broll_path.exists():
                logger.warning(f"B-roll not found, skipping: {broll_path}")
                continue
            duration = seg.duration or 5.0
            broll = VideoFileClip(str(broll_path))
            broll = broll.subclip(0, min(duration, broll.duration))
            broll = _fit_clip(broll, target_w, target_h)
            clips.append(("broll", broll))

        elif seg.type == "overlay":
            overlay_path = PROJECT_ROOT / "overlays" / seg.content
            if not overlay_path.exists():
                logger.warning(f"Overlay not found, skipping: {overlay_path}")
                continue
            duration = seg.duration or 10.0
            clips.append(("overlay", (overlay_path, duration)))

        elif seg.type == "cta":
            duration = seg.duration or 5.0
            clips.append(("cta", (seg.content, seg.options.get("subtext", ""), duration)))

    # Now build the full clip list in segment order, inserting the avatar
    # for speech runs. We rebuild from segments.
    final_clips = []
    speech_start = 0.0  # track where in avatar_source we are

    # We need to know the duration of each speech segment.
    # Since the avatar was lip-synced to the full TTS audio, the avatar's
    # total duration = sum of all speech segment durations. We divide it
    # proportionally by character count as a rough proxy (or use full avatar
    # if there's only one speech segment).
    speech_segs = [s for s in segments if s.type == "speech"]
    total_chars = sum(len(s.content) for s in speech_segs) or 1
    avatar_total = avatar_source.duration

    for seg in segments:

        if seg.type == "speech":
            # Allocate proportional slice of avatar
            seg_chars = len(seg.content)
            seg_duration = avatar_total * (seg_chars / total_chars)
            seg_end = min(speech_start + seg_duration, avatar_total)

            avatar_clip = avatar_source.subclip(speech_start, seg_end)
            # Loop if short
            if avatar_clip.duration < 0.5:
                speech_start = seg_end
                continue
            avatar_clip = _fit_clip(avatar_clip, target_w, target_h)
            final_clips.append(avatar_clip)
            speech_start = seg_end

        elif seg.type == "broll":
            broll_path = PROJECT_ROOT / "broll" / seg.content
            if not broll_path.exists():
                logger.warning(f"B-roll not found, skipping: {seg.content}")
                continue
            duration = seg.duration or 5.0
            broll = VideoFileClip(str(broll_path))
            broll = broll.subclip(0, min(duration, broll.duration))
            broll = _fit_clip(broll, target_w, target_h)
            broll = broll.without_audio()
            final_clips.append(broll)
            logger.info(f"  + B-roll: {seg.content} ({broll.duration:.1f}s)")

        elif seg.type == "overlay":
            overlay_path = PROJECT_ROOT / "overlays" / seg.content
            if not overlay_path.exists():
                logger.warning(f"Overlay not found, skipping: {seg.content}")
                continue
            duration = seg.duration or 10.0

            # Determine how much avatar to use for this overlay segment
            seg_chars = 0  # overlays play over no speech
            # Use a fixed duration slice of the avatar (loop if needed)
            overlay_avatar_end = min(speech_start + duration, avatar_total)
            if speech_start >= avatar_total:
                avatar_bg = avatar_source.subclip(0, min(duration, avatar_total))
            else:
                avatar_bg = avatar_source.subclip(speech_start, overlay_avatar_end)
            avatar_bg = _fit_clip(avatar_bg, target_w, target_h)

            # Load overlay
            suffix = overlay_path.suffix.lower()
            if suffix in (".mp4", ".mov", ".avi"):
                overlay_clip = VideoFileClip(str(overlay_path))
                overlay_clip = overlay_clip.subclip(0, min(duration, overlay_clip.duration))
            else:
                overlay_clip = ImageClip(str(overlay_path)).set_duration(duration)

            # Fill frame with overlay
            overlay_clip = _fit_clip(overlay_clip, target_w, target_h)

            # Shrink avatar to PIP in bottom-left
            pip_w = int(target_w * PIP_SCALE)
            pip_h = int(pip_w * avatar_bg.h / avatar_bg.w)
            pip = resize(avatar_bg, width=pip_w)
            pip = pip.set_position((PIP_MARGIN, target_h - pip_h - PIP_MARGIN))

            composite = CompositeVideoClip(
                [overlay_clip, pip],
                size=(target_w, target_h)
            ).set_duration(duration)
            final_clips.append(composite)
            logger.info(f"  + Overlay: {seg.content} ({duration:.1f}s)")

        elif seg.type == "cta":
            duration = seg.duration or 5.0
            # Avatar plays behind CTA text
            if speech_start < avatar_total:
                avatar_bg = avatar_source.subclip(speech_start, min(speech_start + duration, avatar_total))
            else:
                avatar_bg = avatar_source.subclip(0, min(duration, avatar_total))
            avatar_bg = _fit_clip(avatar_bg, target_w, target_h)

            text_clips = _make_cta_clip(
                seg.content,
                seg.options.get("subtext", ""),
                duration,
                target_w,
                target_h,
            )
            composite = CompositeVideoClip(
                [avatar_bg] + text_clips,
                size=(target_w, target_h)
            ).set_duration(duration)
            final_clips.append(composite)
            logger.info(f"  + CTA: {seg.content!r} ({duration:.1f}s)")

    if not final_clips:
        raise RuntimeError("No clips to assemble — check your segments and asset files")

    # Concatenate all clips
    logger.info(f"Concatenating {len(final_clips)} clips...")
    final = concatenate_videoclips(final_clips, method="compose")

    # Add background music
    if music_track:
        music_path = PROJECT_ROOT / "music" / music_track.filename
        if music_path.exists():
            vol = _parse_volume_db(music_track.volume)
            music = AudioFileClip(str(music_path)).volumex(vol)
            # Loop music if shorter than video
            if music.duration < final.duration:
                loops = int(final.duration / music.duration) + 1
                from moviepy.audio.AudioClip import concatenate_audioclips
                music = concatenate_audioclips([music] * loops)
            music = music.subclip(0, final.duration)

            # Mix with existing audio
            if final.audio:
                from moviepy.audio.AudioClip import CompositeAudioClip
                mixed = CompositeAudioClip([final.audio, music])
                final = final.set_audio(mixed)
            else:
                final = final.set_audio(music)
            logger.info(f"  + Music: {music_track.filename} at {music_track.volume}")
        else:
            logger.warning(f"Music file not found, skipping: {music_path}")

    # Write output
    logger.info(f"Writing output: {output_path}")
    final.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=30,
        bitrate="8000k",
        logger="bar",
    )

    avatar_source.close()
    logger.info(f"Done: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Quick test — needs a lipsync output to exist
    lipsync_out = PROJECT_ROOT / ".tmp" / "test_lipsync.mp4"
    if not lipsync_out.exists():
        print(f"Run lipsync.py first to generate {lipsync_out}")
        sys.exit(1)

    from parse_script import parse_script

    sample = """
This is a test of the video assembler.

[CTA: It Works | KnockOff is running]

Thanks for watching.
"""
    segments, music = parse_script(sample)
    out = PROJECT_ROOT / ".tmp" / "test_assembled.mp4"
    assemble(lipsync_out, segments, out, music_track=music, format="portrait")
    print(f"Assembled: {out}")
    import subprocess
    subprocess.run(["open", str(out)])
