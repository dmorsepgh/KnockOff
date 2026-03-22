# Director Agent - Video Production Planning

The Director Agent analyzes your script and creates a production-ready plan using the optimal 60-second video structure.

## The 60-Second Structure

```
[0-20s]  INTRO  - Avatar with lip sync (chunk 1)
[20-40s] MIDDLE - B-roll with voiceover (no lip sync)
[40-60s] OUTRO  - Avatar with lip sync (chunk 2)
```

**Why this works:**
- Total 60 seconds fits perfectly into 3x 20-second chunks
- Only 40 seconds need lip syncing (intro + outro)
- Middle 20 seconds is pure voiceover over B-roll
- Continuous audio runs underneath entire video
- Avoids chunk boundary issues that plagued longer videos

## Usage

### Basic Usage
```bash
python tools/director_agent.py -s scripts/my-script.md
```

This will:
1. Analyze your script
2. Split it into intro/middle/outro segments
3. Calculate timing for each segment
4. Generate a production plan with shot lists
5. Save as `scripts/my-script-PRODUCTION.md`

### Auto-Trim Long Scripts
If your script is longer than 60 seconds:
```bash
python tools/director_agent.py -s scripts/my-script.md --auto-trim
```

This will automatically trim the script to ~60 seconds (150 words).

### Custom Output Path
```bash
python tools/director_agent.py -s scripts/my-script.md -o scripts/production-plan.md
```

## What You Get

The Director Agent generates a production plan that includes:

**Timing Breakdown:**
- Exact duration estimates for each segment
- Warnings if timing is off

**Production Structure:**
- Intro script text (20s) - what avatar says in first chunk
- Middle script text (20s) - voiceover for B-roll section
- Outro script text (20s) - what avatar says in final chunk

**Shot Lists:**
- What B-roll footage you need to capture
- What overlays/graphics to create
- File naming conventions

**Audio Production Notes:**
- How to generate continuous 60s audio
- Which portions need lip syncing
- Which portions are voiceover only

**Pre-Flight Checklist:**
- What assets need to be ready before generation
- Links to validation and generation commands

## Example Workflow

**1. Write your script** (can be any length)
```bash
# Write your script content
vim scripts/my-idea.md
```

**2. Run Director Agent** with auto-trim
```bash
python tools/director_agent.py -s scripts/my-idea.md --auto-trim
```

**3. Review production plan**
```bash
cat scripts/my-idea-PRODUCTION.md
```

**4. Capture B-roll** based on shot list

**5. Run pre-flight check**
```bash
python tools/preflight_check.py -s scripts/my-idea-PRODUCTION.md -a doug
```

**6. Generate video**
```bash
python tools/generate_avatar_video.py -s scripts/my-idea-PRODUCTION.md -a doug -f portrait
```

## Tips

**Script Length:**
- Target 150 words for 60-second videos
- ~50 words per 20-second segment
- Use `--auto-trim` if your script is too long

**Content Strategy:**
- **Intro (0-20s):** Hook and setup - avatar talking directly
- **Middle (20-40s):** Main content - B-roll with voiceover explaining concepts
- **Outro (40-60s):** Conclusion and CTA - avatar closing thoughts

**B-roll Planning:**
- Keep middle segment focused on visual storytelling
- Screen recordings work great here
- Text overlays for key points
- No need for avatar face in middle 20s

## Integration with Morning Prep

The Director Agent fits into the automated workflow:

```
6:00 AM  → morning_prep.py finds controversy, generates script
7:00 AM  → Director Agent plans production structure
          → You review plan and capture B-roll
          → generate_avatar_video.py produces final video
```

## Troubleshooting

**Script too long warning:**
- Use `--auto-trim` flag
- Or manually edit script to ~150 words

**Timing feels off:**
- Remember: ~2.5 words per second
- Adjust script content, regenerate plan

**Segments don't flow well:**
- Director Agent splits by word count
- Review production plan and adjust manually if needed
- The auto-split is a starting point, not final output
