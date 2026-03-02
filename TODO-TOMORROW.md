# KnockOff - Tomorrow's Tasks

## 1. Disk Cleanup (Do First)
- [ ] Delete SadTalker: `rm -rf ~/SadTalker` (762 MB)
- [ ] Move VG-BACKUPS to NAS
- [ ] Review ~/Documents and ~/Desktop - move old stuff to NAS
- [ ] Review IPTV folders - consolidate or move unused ones
- [ ] Goal: Get to 15+ GB free space

## 2. Finish MuseTalk Setup
- [ ] Install mmpose: `cd ~/MuseTalk && source venv/bin/activate && pip install mmpose mmcv mmdet`
- [ ] Test MuseTalk with sample video
- [ ] Verify it works with your photo + voice

## 3. Record Your Avatar
- [ ] Setup: Ring light, clean background, phone/camera on tripod
- [ ] Record 10-30 seconds of yourself looking at camera
- [ ] Neutral expression, mouth closed, minimal movement
- [ ] Save as MP4 to `~/KnockOff/avatars/doug.mp4`

## 4. Test Full Commercial Pipeline
- [ ] Your avatar (doug.mp4) + Your voice (doug.wav) + MuseTalk
- [ ] Generate a test video with your face speaking
- [ ] Check quality - adjust if needed

## 5. Optional: Fix API Access
- [ ] D-ID: May need paid plan for API access
- [ ] Sync Labs: Check correct API endpoint
- [ ] These are backup options if MuseTalk quality isn't good enough

---

## What's Already Done
- ✅ Voice clone working (`--voice doug`)
- ✅ Wav2Lip working (for testing, non-commercial)
- ✅ Background removal (rembg)
- ✅ B-roll/overlay stitching
- ✅ Caption generation
- ✅ API keys saved in .env
- ✅ MuseTalk downloaded (just needs mmpose)

## The Goal
**Sellable product:** Your face + your voice + MIT-licensed lip-sync = legal to sell

**Business model:** $10-15 per video minute, $0 cost = pure profit
