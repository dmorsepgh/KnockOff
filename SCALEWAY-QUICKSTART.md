# Scaleway Mac mini - Quick Start Guide

**Get KnockOff running on true on-demand Mac VMs in 15 minutes**

---

## Why Scaleway?

✅ **True on-demand** - Spin up/down via API
✅ **Self-service** - No sales calls, instant signup
✅ **Affordable** - €0.11-0.22/hour (~$0.12-0.24 per video)
✅ **M1/M2/M4 options** - Choose your speed vs cost
✅ **API-first** - Full automation ready

---

## Step 1: Sign Up (5 minutes)

1. Go to: https://account.scaleway.com/register
2. Enter email, password
3. Add payment method (credit card)
4. Verify email

**Cost**: Free signup, only pay for instances you use

---

## Step 2: Get API Credentials (2 minutes)

1. Log into: https://console.scaleway.com
2. Click your profile → **API Keys**
3. Click **"Generate API Key"**
4. **Save these immediately** (shown only once!):
   - `Access Key` (starts with SCW...)
   - `Secret Key` (UUID format)

5. Also collect from console:
   - **Project ID**: Settings → Project ID
   - **Organization ID**: Settings → Organization ID

---

## Step 3: Configure KnockOff (2 minutes)

Create `~/KnockOff/cloud_config.json`:

```json
{
  "scaleway": {
    "access_key": "SCWXXXXXXXXXXXXXXXXX",
    "secret_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "project_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "organization_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "zone": "fr-par-1",
    "mac_type": "m2"
  }
}
```

**Mac Types:**
- `m1`: €0.11/hour (cheapest, good for testing)
- `m2`: €0.17/hour (balanced, recommended)
- `m4`: €0.22/hour (fastest, latest hardware)

**Zones:**
- `fr-par-1`: France (Europe)
- `nl-ams-1`: Netherlands (Europe)

---

## Step 4: Test Connection (1 minute)

```bash
cd ~/KnockOff
source .venv/bin/activate

python tools/cloud_generate.py --provider scaleway --test-connection
```

Expected output:
```
✅ SSH connection successful!
```

If you see errors, check:
- API credentials are correct
- Project ID matches your account
- Zone is valid

---

## Step 5: Generate First Video (5 minutes)

```bash
python tools/cloud_generate.py \
  --script scripts/tattoo-builder-90s.md \
  --avatar vg-host \
  --provider scaleway \
  --quality Fast
```

**What happens:**
1. API spins up Mac mini M2 (30-60 seconds)
2. Deploys KnockOff automatically (2-3 minutes)
3. Generates video (3-7 minutes depending on quality)
4. Downloads result
5. Destroys instance
6. Shows cost

**Expected cost:** €0.17 (rounds up to 1 hour)

---

## Understanding Billing

### ⚠️ IMPORTANT: Scaleway rounds up to full hours

- Use 7 minutes → Charged for 1 hour
- Use 61 minutes → Charged for 2 hours

**Cost Per Video:**
- Fast quality (3 min) = €0.11-0.22 (1 hour)
- Improved quality (7 min) = €0.11-0.22 (1 hour)
- Enhanced quality (15 min) = €0.11-0.22 (1 hour)

**Batch Processing Tip:**
Generate multiple videos in one session to maximize the hour:

```bash
# All in same hour = €0.17 total
python tools/cloud_generate.py -s video1.md -a avatar --provider scaleway &
python tools/cloud_generate.py -s video2.md -a avatar --provider scaleway &
python tools/cloud_generate.py -s video3.md -a avatar --provider scaleway &
wait
```

---

## Common Commands

### Single Video
```bash
python tools/cloud_generate.py \
  -s scripts/my-video.md \
  -a vg-host \
  --provider scaleway
```

### Fast Preview
```bash
python tools/cloud_generate.py \
  -s scripts/test.md \
  -a vg-host \
  --provider scaleway \
  --quality Fast
```

### Different Mac Type
```bash
# Use M1 (cheapest)
python tools/cloud_generate.py \
  -s scripts/my-video.md \
  -a vg-host \
  --provider scaleway \
  --config cloud_config_m1.json
```

Create `cloud_config_m1.json` with `"mac_type": "m1"`

---

## Troubleshooting

### "API authentication failed"
- Check access_key and secret_key are correct
- Make sure no extra spaces in config JSON
- Verify API key is still active in console

### "No servers available in zone"
- Scaleway may be out of Mac minis in that zone
- Try different zone: `"zone": "nl-ams-1"`
- Wait and retry (availability fluctuates)

### "Server failed to start"
- Check Scaleway console for server status
- May be temporary provisioning issue
- Retry - most failures are transient

### "Timeout waiting for server"
- Mac minis can take 5-10 minutes to provision
- This is normal for first boot
- Subsequent boots are faster

### High costs
- Remember: Scaleway rounds UP to full hour
- Batch videos to maximize hour usage
- Use M1 for testing ($0.12/hour vs $0.24)

---

## Cost Optimization Tips

### 1. Batch Process
Run multiple videos in one hour:
```bash
for script in scripts/*.md; do
  python tools/cloud_generate.py -s "$script" -a vg-host --provider scaleway &
done
wait
```

### 2. Use M1 for Testing
Change `"mac_type": "m1"` in config
- €0.11/hour vs €0.22/hour
- Good enough for previews

### 3. Fast Quality for Drafts
```bash
--quality Fast  # 3 min generation vs 7 min
```

### 4. Keep Sessions Under 1 Hour
- 1-4 videos per session = €0.11-0.22
- 5-8 videos per session = €0.22-0.44 (2 hours)

---

## Next Steps

**You're all set up!**

Now you can:
- Generate videos on-demand
- Scale to parallel processing
- Only pay for what you use

**Monthly Budget Examples:**
- 10 videos/month = €1.70 (~$1.85)
- 50 videos/month = €8.50 (~$9.25)
- 100 videos/month = €17.00 (~$18.50)

Compare to:
- HeyGen: $29-89/month subscription
- Local Mac: Free but ties up your machine

---

## Advanced: Parallel Processing

Generate 4 videos simultaneously:

```bash
# Terminal 1
python tools/cloud_generate.py -s video1.md -a host1 --provider scaleway &

# Terminal 2
python tools/cloud_generate.py -s video2.md -a host2 --provider scaleway &

# Terminal 3
python tools/cloud_generate.py -s video3.md -a host3 --provider scaleway &

# Terminal 4
python tools/cloud_generate.py -s video4.md -a host4 --provider scaleway &
```

**Result:**
- 4 VMs running in parallel
- 4 videos in ~7 minutes (vs 28 minutes serial)
- Cost: 4 × €0.17 = €0.68 (4 instances × 1 hour each)

---

## Support

**Scaleway Docs:** https://www.scaleway.com/en/docs/
**API Reference:** https://www.scaleway.com/en/developers/api/apple-silicon/

**Issues?**
- Check logs: `~/KnockOff/logs/cloud_orchestrator_*.log`
- Verify credentials in cloud_config.json
- Test API manually: `python tools/scaleway_provider.py`

---

**Last Updated:** February 4, 2026
**Status:** Production Ready
