# KnockOff Cloud Deployment Guide

**Generate videos on-demand using remote Mac servers**

Stop wasting your local Mac's resources. Spin up cloud Macs only when you need them, generate videos, and tear down. Pay only for what you use.

---

## Why Cloud Generation?

**The Problem:**
- Video generation is CPU/RAM intensive
- Ties up your Mac for 5-15 minutes
- Can't work on other things during generation
- Risk of crashes with limited local resources

**The Solution:**
- Rent Mac server on-demand (~$0.85 per video)
- Generate videos while you keep working
- No local resource usage
- Process multiple videos in parallel

---

## Quick Start

### 1. Setup Cloud Config

```bash
cd ~/KnockOff
cp cloud_config.example.json cloud_config.json
```

Edit `cloud_config.json` with your server credentials:

```json
{
  "macstadium": {
    "host": "your-server.macstadium.com",
    "username": "admin",
    "password": "your-password-here",
    "ssh_key": "/path/to/your/ssh/key",
    "hourly_rate": 0.85
  }
}
```

**Security Note:** Use SSH key authentication when possible, not passwords.

### 2. Install Cloud Dependencies

```bash
source .venv/bin/activate
pip install paramiko scp
```

### 3. Test Connection

```bash
python tools/cloud_generate.py --test-connection --provider macstadium
```

You should see:
```
✅ SSH connection successful!
```

### 4. Generate Your First Cloud Video

```bash
python tools/cloud_generate.py \
  --script scripts/my-video.md \
  --avatar vg-host \
  --quality Improved
```

**That's it!** The orchestrator handles everything else automatically.

---

## What Happens Behind the Scenes

When you run `cloud_generate.py`, here's the full workflow:

```
1. 🚀 Provision server (or connect to existing)
   ↓
2. 🔌 Connect via SSH
   ↓
3. 📦 Deploy KnockOff (setup.sh runs automatically)
   ↓
4. 📤 Upload your script + assets (avatar, B-roll, etc.)
   ↓
5. 🎬 Generate video on remote server
   ↓
6. 📥 Download finished video
   ↓
7. 💾 Save to local + NAS (if mounted)
   ↓
8. 🧹 Cleanup remote files
   ↓
9. 💰 Show costs and summary
```

**You don't touch ANY of this manually.** Just one command.

---

## Command Reference

### Basic Usage

```bash
# Standard generation
python tools/cloud_generate.py -s scripts/my-video.md -a vg-host

# With specific quality
python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --quality Enhanced

# Different format
python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --format landscape

# Female voice
python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --voice lessac

# Use different provider
python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --provider macly
```

### Testing & Debugging

```bash
# Test SSH connection
python tools/cloud_generate.py --test-connection

# Dry run (see what would happen without executing)
python tools/cloud_generate.py -s scripts/test.md -a vg-host --dry-run

# Use custom config file
python tools/cloud_generate.py -s scripts/test.md -a vg-host --config /path/to/config.json
```

### All Options

```
Required:
  -s, --script PATH       Path to script .md file
  -a, --avatar NAME       Avatar name (without .mp4)

Optional:
  -q, --quality LEVEL     Fast, Improved, Enhanced (default: Improved)
  -f, --format FORMAT     portrait, landscape, square (default: portrait)
  -v, --voice VOICE       joe, lessac (default: joe)
  --provider PROVIDER     macstadium, macly (default: macstadium)
  --config PATH           Custom config file path
  --test-connection       Test SSH without generating
  --dry-run               Show workflow without executing
```

---

## Cloud Providers

### MacStadium

**Overview:**
- On-demand Mac servers
- M1/M2/M3 Mac Minis available
- Pay-per-use pricing
- Good for one-off tests

**Setup:**
1. Sign up at [macstadium.com](https://www.macstadium.com)
2. Get server credentials
3. Add to `cloud_config.json` under `macstadium`

**Estimated Cost:** ~$0.85 per 2-minute video at Improved quality

### Macly

**Overview:**
- Similar to MacStadium
- Alternative pricing models
- Good customer support

**Setup:**
1. Sign up at [macly.com](https://www.macly.com)
2. Get server credentials
3. Add to `cloud_config.json` under `macly`

**Estimated Cost:** ~$0.85 per video

### Custom Server

You can use ANY Mac server (your own, a friend's, etc.):

```json
{
  "custom": {
    "host": "192.168.1.100",
    "username": "admin",
    "password": "your-password",
    "hourly_rate": 0.0
  }
}
```

Then use: `--provider custom`

---

## Cost Breakdown

### Per Video Costs (Estimated)

| Quality  | Time    | Compute | Transfer | Total   |
|----------|---------|---------|----------|---------|
| Fast     | 3 min   | $0.43   | $0.05    | $0.48   |
| Improved | 7 min   | $0.85   | $0.10    | $0.95   |
| Enhanced | 15 min  | $1.70   | $0.15    | $1.85   |

*Based on typical 2-minute video with moderate assets*

### Monthly Budget Examples

**Light Use (5 videos/month):**
- 5 videos × $0.95 = **$4.75/month**

**Moderate Use (20 videos/month):**
- 20 videos × $0.95 = **$19.00/month**

**Heavy Use (100 videos/month):**
- 100 videos × $0.95 = **$95.00/month**

**Compare to HeyGen:**
- HeyGen: $29-$89/month subscription
- KnockOff Cloud: Pay only for what you generate

---

## Security Best Practices

### SSH Keys (Recommended)

Generate an SSH key for cloud servers:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/knockoff_cloud -C "knockoff-cloud"
```

Add public key to remote server:

```bash
ssh-copy-id -i ~/.ssh/knockoff_cloud.pub user@remote-server
```

Update `cloud_config.json`:

```json
{
  "macstadium": {
    "ssh_key": "/Users/yourname/.ssh/knockoff_cloud",
    "password": ""
  }
}
```

### Config File Permissions

Protect your credentials:

```bash
chmod 600 cloud_config.json
```

### Environment Variables

For CI/CD or shared systems, use environment variables:

```bash
export MACSTADIUM_HOST="your-server.macstadium.com"
export MACSTADIUM_USER="admin"
export MACSTADIUM_KEY="/path/to/key"
```

The orchestrator will check environment variables if `cloud_config.json` is missing.

---

## Troubleshooting

### "SSH connection failed"

**Cause:** Wrong credentials or server not reachable

**Fix:**
1. Test connection manually: `ssh user@host`
2. Verify credentials in `cloud_config.json`
3. Check firewall/network settings
4. Try password auth if key auth fails

### "Failed to deploy KnockOff"

**Cause:** Missing dependencies on remote server

**Fix:**
1. Ensure remote server has Python 3.12
2. Ensure ffmpeg is installed
3. Check setup.sh logs on remote server
4. Manually SSH in and run setup.sh to see errors

### "Video generation failed"

**Cause:** Various - check remote logs

**Fix:**
1. Check local log: `logs/cloud_orchestrator_YYYYMMDD.log`
2. SSH to remote server and check: `/tmp/KnockOff/logs/`
3. Verify all assets uploaded correctly
4. Try with Fast quality first to isolate issue

### "Could not find generated video file"

**Cause:** Output file in unexpected location

**Fix:**
1. SSH to remote server
2. Check: `find /tmp/KnockOff -name "*.mp4"`
3. Manually download if found
4. Report issue for future fix

### High costs

**Cause:** Long generation times or inefficient workflow

**Fix:**
1. Use Fast quality for previews
2. Test locally first, cloud for final
3. Optimize script (shorter videos = lower costs)
4. Batch multiple videos in one session

---

## Advanced Usage

### Batch Processing

Generate multiple videos in sequence:

```bash
# Create a batch script
for script in scripts/*.md; do
  python tools/cloud_generate.py -s "$script" -a vg-host -q Fast
done
```

### Parallel Processing

Use multiple providers simultaneously:

```bash
# Terminal 1
python tools/cloud_generate.py -s scripts/video1.md -a vg-host --provider macstadium &

# Terminal 2
python tools/cloud_generate.py -s scripts/video2.md -a vg-host --provider macly &
```

### Custom Remote Directory

By default, KnockOff installs to `/tmp/KnockOff`. To use a different location, modify the orchestrator:

```python
orchestrator.generate_video(
    script_path='scripts/test.md',
    avatar='vg-host',
    remote_dir='/home/admin/KnockOff'  # Custom location
)
```

---

## API Integration (Future)

**Coming Soon:** Direct API integration with providers for true on-demand provisioning.

Currently, the orchestrator connects to pre-configured servers. Future versions will:
- Provision servers automatically via API
- Destroy servers after generation
- Handle billing automatically
- Support auto-scaling for batch jobs

---

## Performance Tips

### Optimize Upload Speed

1. **Compress B-roll before upload:**
   ```bash
   ffmpeg -i large-broll.mp4 -c:v libx264 -crf 23 compressed-broll.mp4
   ```

2. **Use smaller overlays:**
   - 1080p instead of 4K
   - PNG with compression

3. **Pre-deploy assets:**
   - Upload common assets once
   - Reuse across multiple generations
   - Only upload script-specific files

### Reduce Generation Time

1. Use **Fast quality** for previews
2. Keep videos under 2 minutes
3. Minimize B-roll count
4. Use lightweight avatars (shorter duration)

### Save Money

1. Test locally first, cloud for final render
2. Batch multiple videos in one session
3. Use Fast quality unless client-facing
4. Share server costs with team

---

## Monitoring & Logs

### Local Logs

All orchestration activity is logged:

```bash
tail -f ~/KnockOff/logs/cloud_orchestrator_$(date +%Y%m%d).log
```

### Remote Logs

SSH to check remote generation logs:

```bash
ssh user@remote-server
cat /tmp/KnockOff/logs/knockoff_*.log
```

### Cost Tracking

After each generation, costs are displayed:

```
💰 Total cost: $0.95
   Compute: $0.85 (7.2 minutes)
   Transfer: $0.10
```

Track monthly spend:

```bash
grep "Total cost" logs/cloud_orchestrator_*.log | awk '{sum+=$NF} END {print "Monthly total: $"sum}'
```

---

## FAQ

**Q: Do I need to keep the server running?**
A: No! The orchestrator connects, generates, and disconnects. Server can be shut down when not in use.

**Q: Can I use my own Mac as a "cloud" server?**
A: Yes! Add it as a custom provider. Great for testing before paying for cloud.

**Q: What happens if generation fails mid-way?**
A: Costs are calculated based on time used. You pay for compute time even if it fails.

**Q: Can I queue multiple videos?**
A: Not yet, but coming soon. For now, run multiple `cloud_generate.py` commands in parallel.

**Q: How much does data transfer cost?**
A: Usually included or very cheap (~$0.10 per video). Most cost is compute time.

**Q: Is this faster than local generation?**
A: Similar speed, but your Mac stays free for other work. That's the real win.

---

## Next Steps

1. ✅ Set up `cloud_config.json`
2. ✅ Test connection with `--test-connection`
3. ✅ Generate test video with Fast quality
4. ✅ Review costs and optimize workflow
5. ✅ Scale up to production videos

---

**Last Updated:** February 4, 2026
**Version:** 1.0
**Author:** Doug Morse (@dmpgh)

For questions or issues, check logs first, then report to GitHub issues.
