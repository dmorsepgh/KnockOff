# FUNDRAISER VIDEO PLAYBOOK

**The reverse-engineered process for making an NMSS-grade nonprofit fundraiser video in one sitting, using `fundraiser_generator.py` + Claude as editor.**

Derived from the 2026-04-11 session where Doug Morse and Claude built the National MS Society demo video through 16+ iterations in one Saturday. Everything in here is stuff we actually learned (and many things we broke and fixed). Use this as the recipe for video #2, #3, and beyond.

---

## WHAT THIS PRODUCES

A ~60-80 second fundraiser video with:

- **5 narrated scenes** on a proven direct-response structure (hook → problem → stakes → solution → ask)
- **Branded lower-third banner** throughout (floating, top-rounded, with logo plate + contact text + SCAN TO GIVE QR card)
- **Dynamic in-frame overlays** during specific scenes (rotating callouts, cascading bullets, price stamps)
- **Branded final card** (hero image, logo, tagline, CTA, URL, phone, production credit)
- **~20-second rolling end credits** with your personal attribution and contact info
- **1.5-second "Look Mom, No Hands Productions" bumper** with crash SFX
- **Continuous piano underscore** through the entire video, no muddy handoffs
- Landscape (1920×1080) and optional vertical (1080×1920) delivery

Total cost per render: **~$0.02** in OpenAI TTS (if using `--reuse`, $0.00).

---

## PREREQUISITES (one-time setup)

You already have all of this from the NMSS session, but a new project needs:

1. **API keys** in `~/.keys/.env`:
   - `PEXELS_API_KEY` — for stock b-roll
   - `OPENAI_API_KEY` — for narration TTS
2. **Dependencies installed**:
   - `ffmpeg` (`brew install ffmpeg`)
   - `qrencode` (`brew install qrencode`)
   - `ollama` (with `mistral-small` pulled) — fallback script writer
   - Python 3.12 with `pillow`, `python-dotenv`, `requests`
3. **Music assets** in `~/KnockOff/music/fundraiser/`:
   - `emotional-piano.mp3` — continuous bed (mandatory)
   - `dramatic-violin-final.mp3` — used as the `--final-music` input (its audio is now discarded since the piano carries through, but the flag is still required for now)
4. **Brand assets folder** — `~/KnockOff/brand_assets/` has the NMSS assets (logo, hero images). For a new org, you'll add new ones.
5. **This playbook** (you're reading it)

---

## THE 8-STEP PROCESS

From a blank project to a shipped video, this is the order that works.

### Step 1: Gather the org's real assets

Before writing anything, collect:

| Asset | Where to get it |
|---|---|
| **Organization name** | Their website |
| **Donate URL** | Their website (direct donate page, not just the homepage) |
| **Phone number** | Their website contact page (for the banner) |
| **Logo PNG** | Their Open Graph tag on the homepage — fetch it like `curl https://theirsite.org \| grep -oE 'og:image[^"]*"[^"]*"' \| head` — or from their press kit |
| **Brand color** | Pull their main brand color from their website CSS. Grep for hex codes in the homepage HTML (`grep -oE "#[0-9a-fA-F]{6}" /tmp/page.html \| sort \| uniq -c \| sort -rn`) and pick the brand accent, not white/black. Format for the generator as `0xRRGGBB`. |
| **Brand tagline / angle** | Read their "About" / "Mission" page. Find one concrete verb (not "empower"). |

### Step 2: Pick a hero image

Search Pexels for 3-9 candidate hero images that thematically match the cause. Save to `/tmp/hero_options/`. Look at them side by side. Pick the one that:
- Has good horizontal composition (for landscape)
- Has natural dark areas at the bottom (for banner readability) OR will darken well under `eq=brightness=-0.22`
- Is thematically on-topic without being literal (the NMSS hero is three connected hands, not a doctor with a syringe)

Save as `~/KnockOff/brand_assets/<org>-hero-<theme>.jpg`.

### Step 3: Write the script (the single most important step)

**Copy `scripts_fundraiser/nmss_v2.json` as a template. Rewrite the scene text BY HAND.**

**The editorial rule that matters more than anything else:** every scene must contain *specific, concrete imagery that a human would notice*. NOT "empower communities," NOT "make a difference," NOT "give hope." Good examples from NMSS:

- `"A mother who can't pick up her toddler. A father who can't walk his daughter down the aisle."`
- `"More mornings without symptoms. More evenings still walking. More years before the wheelchair."`
- `"Help someone keep the next morning."`

Corporate mush kills videos. You discovered this when the Squeaky Squirrel test used LLM-generated copy and we rewrote NMSS by hand — the difference was enormous.

**Script structure (nmss_v2.json)**:

```json
{
  "scene1_hook": "Emotional opener, ~8 seconds. Put the viewer in a moment.",
  "scene2_problem": "State the problem. Include ONE specific statistic. ~12 seconds.",
  "scene3_stakes": "Who suffers and how. Concrete imagery — describe a person, a moment, a fear. ~15 seconds.",
  "scene4_solution": "What the org does. Specific verbs. ~15 seconds.",
  "scene5_ask": "Direct call to action. Specific amount. Specific URL. Emotional close. ~10 seconds.",

  "keywords_scene1": ["2-3 words", "visual descriptors"],
  "keywords_scene2": ["for", "pexels search"],
  "keywords_scene3": ["descriptive", "specific"],
  "keywords_scene4": ["solution", "imagery"],
  "keywords_scene5": ["hopeful", "close"],

  "scene2_overlays": [
    {"lines": "WORD ONE|*WORD TWO", "in": 0.3, "out": 2.8, "pos": "right-nose"},
    {"lines": "ANOTHER|*LINE", "in": 3.0, "out": 5.8, "pos": "right-nose"},
    {"lines": "*STAT|MORE CONTEXT|WORDS", "in": 6.2, "out": 10.8, "pos": "right-nose"}
  ],

  "scene4_overlays": [
    {"style": "bullet", "head": "MORE X", "sub": "context", "in": 7.5, "out": 14.0, "x": 1080, "y": 140},
    {"style": "bullet", "head": "MORE Y", "sub": "context", "in": 9.5, "out": 14.0, "x": 1080, "y": 350},
    {"style": "bullet", "head": "MORE Z", "sub": "context", "in": 11.0, "out": 14.0, "x": 1080, "y": 560}
  ],

  "rolling_credits": [
    {"header": "AI VOCAL ARTIST", "lines": ["presents", ""]},
    {"header": "", "lines": ["THE VIDEO TITLE", "a cause subtitle"]},
    {"header": "PRODUCED BY", "lines": ["Your Name", "your tagline"]},
    {"header": "", "lines": ["Optional personal attribution line"]},
    {"header": "WRITTEN & DIRECTED BY", "lines": ["AI Claude (Anthropic)"]},
    {"header": "PRODUCTION ENVIRONMENT", "lines": ["VS Code + Claude Code"]},
    {"header": "VOICE", "lines": ["OpenAI TTS — 'Nova'"]},
    {"header": "STOCK FOOTAGE", "lines": ["Pexels"]},
    {"header": "MUSIC", "lines": ["emotional piano", "dramatic violin"]},
    {"header": "RENDERED WITH", "lines": ["ffmpeg · Python · Pillow"]},
    {"header": "CONTACT", "lines": ["your-site.com", "you@yourdomain.com"]},
    {"header": "", "lines": ["", "© 2026 AI VOCAL ARTIST", "all rights reserved"]}
  ]
}
```

**On overlay styles:**

- **`two-tone`** (default) — stacked text lines with pipe separator. A `*` prefix on a line renders it in brand-color instead of white. Font is Impact. Used for rotating callouts (scene 2 style).
- **`bullet`** — single bullet: big brand-orange Impact headline + smaller white Arial Bold subtitle. Used for cascading bullets (scene 4 style).

**On overlay positioning:**

- **`pos` keyword** — `right-nose` (right side, vertically at y=310), `left-nose`, `right-top`, `left-top`. The "nose" keyword assumes a person's face is in the upper-center of the frame.
- **Explicit `x` and `y`** — override the keyword with absolute pixel coordinates in the 1920×1080 landscape frame. For cascading bullets you MUST use explicit x/y to stack them correctly.

**On overlay timing:**

- `in` and `out` are in SCENE-LOCAL seconds, not full-video seconds. Scene 2 starts at full-video ~8s but scene 2's `in=0.3` means 0.3s into scene 2.
- Fade is always 0.5s in and 0.5s out. Keep `out - in > 1.0` to avoid fade collisions.
- For ROTATING overlays (one at a time), space them so fade-out of one overlaps fade-in of next. For STACKING bullets (all staying visible), set all `out` times to the scene duration.

### Step 4: First render (the generator command)

```bash
cd ~/KnockOff && python3.12 fundraiser_generator.py \
  --org "Org Full Name" \
  --cause "one-sentence cause description" \
  --url "theirsite.org/donate" \
  --phone "1-800-xxx-xxxx" \
  --script scripts_fundraiser/<your_script>.json \
  --music music/fundraiser/emotional-piano.mp3 \
  --final-music music/fundraiser/dramatic-violin-final.mp3 \
  --hero-image brand_assets/<org>-hero.jpg \
  --logo brand_assets/<org>-logo.png \
  --brand-color 0xRRGGBB \
  --tagline "Your emotional tagline." \
  --ask-stamp "\$19" --ask-stamp-at 2.5 \
  --credit-tag "AI VOCAL ARTIST" --credit-sub "fundraiser video production" \
  --rolling-credits --credits-duration 20 \
  --bumper
```

**First-render flags** (no `--reuse` because there's no prior job):
- `--org`, `--cause`, `--url` — required
- `--phone` — optional but almost always wanted
- `--script` — path to your hand-written JSON
- `--hero-image`, `--logo`, `--brand-color` — brand package
- `--tagline` — emotional line shown on the final card (keep it under 50 chars)
- `--ask-stamp` and `--ask-stamp-at` — what shows on scene 5 ("JUST / $19 / A MONTH"); `--ask-stamp` takes just the dollar amount, the "JUST" and "A MONTH" are hardcoded
- `--credit-tag` and `--credit-sub` — production credit on the final card bottom
- `--rolling-credits` — enables the scrolling end credits (content from the JSON)
- `--bumper` — enables the closing Look Mom No Hands bumper

This produces `fundraisers/<Org_Name>_<timestamp>/fundraiser_v1.mp4` (and a copy in `~/Documents/Fundraiser Videos/`).

### Step 5: Watch it cold (the WATCH / REACT loop)

**Don't analyze.** Play it once, start to finish, no pausing. Feel it.

Then play it again with a checklist:
- Scene 1 hook — grabbing? or warm-up?
- Scene 2 problem — memorable stat?
- Scene 3 stakes — emotional?
- Scene 4 solution — concrete?
- Scene 5 ask — clean CTA?
- B-roll — any clip you wince at?
- Voice — any mispronunciation or weird pacing?
- Music — levels right?
- Banner — readable? corners clean?
- Logo plate — tight? too much whitespace?
- Overlays — timed to the narration?
- Final card — text readable on the hero image?
- Rolling credits — your info correct?
- Bumper — lands right?

Write down THE TOP 3 THINGS that are broken.

### Step 6: The Polish Loop (iterate until done)

**Rule zero: one change per cycle.**

```
1. WATCH the current version once
2. REACT: 1-3 specific things that feel wrong
3. FIX: Claude/you makes ONE edit
4. RENDER with --reuse for zero TTS cost
5. COMPARE new version to previous
6. DECIDE: keep it or revert
7. Go to 1.
```

**For re-renders**, add the `--reuse` flag pointing to your existing job directory:

```bash
--reuse fundraisers/Org_Name_20260412-143022
```

This skips Pexels and TTS, recycles all the scene assets, and only re-does the filter-graph composition. Each re-render is ~15 seconds and costs $0.00.

### Step 7: Commit as you go

Every "that version was better, keep it" is a commit. Follow this pattern:

```bash
cd ~/KnockOff && git add fundraiser_generator.py scripts_fundraiser/<your>.json brand_assets/
git commit -m "Short description of what changed"
```

Git is your safety net. If a later change makes something worse, `git checkout` the file and re-render.

### Step 8: Final render + ship

When you can't find anything else to fix, do ONE clean render without `--reuse` (to make sure nothing cached is stale) and copy the output. That's your shipping file.

For short-form, add `--vertical` (also does the 1080×1920 render alongside). Note: vertical is currently Path B — body scenes + banner only, no rolling credits or bumper yet. See `project_vertical_needs_finish.md` in memory for the unfinished work.

---

## EDITORIAL RULES WE LEARNED (the hard way)

These are non-negotiable. Every rule below has a specific scar from the NMSS session.

### 1. Specific imagery beats emotional abstraction
The Squeaky Squirrel A/B test proved this. Ollama-generated copy reads like generic charity mush. Hand-written copy with specific verbs ("We argue with Verizon," "Help someone keep the next morning") is dramatically more effective.

### 2. Show mockups before building visual changes
When making any visual change — new overlay, font, color, layout, badge, brand stamp — generate a static preview PNG via PIL and get yes/no approval BEFORE writing integration code or running a full render. Saves hours of wasted iteration. See `feedback_show_mockups_first.md` in memory.

### 3. Steal from proven nonprofit ads
Before inventing a design pattern, look at real nonprofit commercials currently running on TV. ASPCA and St. Jude were our references for the NMSS session. Their patterns are proven to convert — copying them is lower-risk than inventing. See `feedback_steal_from_proven_ads.md` in memory.

### 4. Outlined text beats backdrop boxes
Text on image backgrounds should use `borderw=N:bordercolor=black` outline stroke, NOT `box=1:boxcolor=black@X` backdrop boxes. Outlined text reads as part of the graphic; boxed text reads as a glued-on label. Rule of thumb: ~1px outline per ~15pt font size. See `feedback_outline_text_not_box.md` in memory.

### 5. Short b-roll clips WILL loop visibly
Pexels returns clips of varied length. If a scene is 10 seconds and the clip is 7 seconds, the b-roll will silently loop-restart at ~7s and viewers will see it. Always check that `probe_duration(broll) >= scene_duration`. If it's short, either fetch multiple clips and concat them, or use `tpad=stop_mode=clone` to freeze-pad the last frame.

### 6. Auto-crop logos before making plates
Open Graph-sized logos (usually 1200×630) have significant built-in whitespace around the actual artwork. The `make_logo_plate` helper now auto-crops using PIL's `ImageChops.difference` + `getbbox()` — but if you're doing any custom logo work, crop first.

### 7. Rounded banner corners need matching geometry
Rounded corners create transparent cutouts. If the banner is rounded and floats, the cutouts show the b-roll behind (intentional and fine). If the banner is rounded but tries to hug the frame edge, the cutouts show black/white frame borders and look broken. Either: round all 4 corners AND float the banner, OR use `top_rounded_rect` with a flat bottom that flushes to the frame edge.

### 8. Piano plays continuously — no instrument handoffs
The original code did a piano-to-violin crossfade 10 seconds before the final card. It sounded muddy. Simplified: piano plays as ONE continuous bed through the entire video (body + final card + credits), fading out only at the very end. The `final_music` param is retained in the API for backwards compat but its audio is discarded.

### 9. Scene 3 "flash of a clip that never makes it"
If you crossfade 3+ clips into a concat b-roll and the scene duration is shorter than the full concat length, the last crossfade can START but not complete before the scene cuts. Result: a flash of the final clip that confuses viewers. Fix: trim the concat to end CLEANLY inside the second clip, with a clone-frame pad at the end.

### 10. Vertical positions ≠ landscape positions
Scene overlays with explicit x/y in the script JSON are ALWAYS for the 1920×1080 landscape frame. In vertical, the assembler ignores those x/y values and centers everything horizontally at `x=(W-w)/2`, stacking vertically with auto-offsets. Don't hardcode vertical positions in the JSON — let the assembler handle it.

---

## COMMON GOTCHAS (from the NMSS session)

| Symptom | Cause | Fix |
|---|---|---|
| Logo plate too fat | Source logo has built-in whitespace | `make_logo_plate` auto-crops now; but verify the plate width looks right |
| Text overlapping logo plate in banner | `text_x` in assemble_scene doesn't account for actual plate width | Plate is ~495px wide in landscape after auto-crop; text_x should be 575+ |
| Banner corners show white spots | Rounded corners with transparent cutouts showing bright b-roll | Use `all_corners=True` + `BANNER_LIFT` (float the banner) |
| Scene 3 loops visibly | Broll clip shorter than scene duration | Fetch multiple clips and concat, or tpad-freeze the end |
| "Flash" clip at scene end | Xfade to new clip starts but doesn't complete | Trim concat cleanly, freeze last frame |
| Final card text unreadable | Backdrop box creating gray ghost | Switch to `borderw/bordercolor=black` outlined text |
| Scene 2 overlay hides the subject | Positioned on wrong side of frame | Put overlay on the OPPOSITE side from where the subject is looking |
| `-t` flag truncating tpad extension | `-t N` after `-i` applies to output, cuts tpad's added frames | Put `-t N` BEFORE `-i` to trim the input instead |
| Rolling credits scroll too fast/slow | Scroll speed is determined by PNG height / duration | Adjust `--credits-duration` or add/remove credit sections |
| Bumper looks pop-in | Alpha fade too short | Use 0.08-0.1s alpha fade, not 0 |

---

## WHAT LIVES WHERE

```
~/KnockOff/
├── fundraiser_generator.py         # The main generator
├── FUNDRAISER-PLAYBOOK.md         # This file
├── BUSINESS-PLAN.md                # Business-level thinking
├── scripts_fundraiser/
│   ├── nmss_v2.json                # NMSS reference script (use as template)
│   └── <new_org>.json              # Your next script
├── brand_assets/
│   ├── nmss-logo.png               # NMSS logo (example)
│   ├── nmss-hero-hands.jpg         # NMSS hero image
│   └── <new_org>-logo.png          # Your next org's assets
├── music/fundraiser/
│   ├── emotional-piano.mp3         # Main music bed (mandatory)
│   └── dramatic-violin-final.mp3   # Final music (still required even though audio is discarded)
└── fundraisers/                    # Per-job output directories (gitignored)
    └── <Org_Name>_<timestamp>/
        ├── scene1/ through scene5/
        │   ├── broll_0.mp4
        │   ├── narration.wav
        │   ├── scene.mp4
        │   ├── scene_vertical.mp4
        │   └── overlay_N.png
        ├── qr_card.png
        ├── banner_bg.png
        ├── logo_plate.png
        ├── ask_overlay.png
        ├── final_card.mp4
        ├── credits.mp4
        ├── bumper.mp4
        └── fundraiser_vN.mp4

~/Documents/Fundraiser Videos/      # Dated copies for Finder access
└── <Org>_<date>_<time>_vN.mp4
```

---

## STARTER CHECKLIST FOR VIDEO #2

Print this or put it in your task manager. Tick off as you go.

### Prep
- [ ] Pick the nonprofit (real or spec)
- [ ] Gather org name, donate URL, phone number, logo, brand color
- [ ] Download logo PNG to `brand_assets/<org>-logo.png`
- [ ] Search Pexels for 3-9 hero image candidates, save to `/tmp/hero_options/`
- [ ] Pick one hero image, save to `brand_assets/<org>-hero.jpg`

### Script
- [ ] Copy `scripts_fundraiser/nmss_v2.json` to `scripts_fundraiser/<org>.json`
- [ ] Rewrite all 5 scene texts BY HAND with specific imagery (no corporate mush)
- [ ] Rewrite 5 sets of keywords for Pexels b-roll search
- [ ] Rewrite scene2_overlays (3 callouts timed to narration)
- [ ] Rewrite scene4_overlays (3 cascading bullets timed to narration)
- [ ] Update rolling_credits with org-specific content (keep your personal attribution line)

### First render
- [ ] Build the generator command with all flags
- [ ] Run the first render (NO `--reuse` — it's a new job)
- [ ] Open output in Finder / player

### Polish Loop (expect 3-6 iterations)
- [ ] Watch once cold
- [ ] Note top 3 issues
- [ ] Fix one at a time, rerender with `--reuse`
- [ ] Commit as you go
- [ ] Stop when you can't find anything else

### Ship
- [ ] One clean render WITHOUT `--reuse` (fresh final)
- [ ] Upload as unlisted to YouTube
- [ ] Send the link (not the file) to your target audience

---

## HOW TO HAND THIS TO A FUTURE CLAUDE SESSION

Paste this exact prompt at the start of a new session:

> I want to make another nonprofit fundraiser video using the `fundraiser_generator.py` tool in `~/KnockOff/`. Read `~/KnockOff/FUNDRAISER-PLAYBOOK.md` first — that's the complete process I've already reverse-engineered from my last project (the National MS Society demo). Follow the 8-step process, enforce the editorial rules, and run the Polish Loop with me iteratively. My target nonprofit for this one is **[ORG NAME]**, their cause is **[ONE SENTENCE]**, their donate URL is **[URL]**, and their phone is **[PHONE]**. I'll send you their logo and we can pick a hero image together.

That prompt + this playbook gets you from zero to another video in dramatically less time than the first one took.

---

## WHAT'S STILL UNFINISHED

Known gaps that a future session should close:

1. **Vertical format is incomplete** — scenes render, but rolling credits, bumper, and branded final card are NOT ported to the 1080×1920 pipeline yet. See `project_vertical_needs_finish.md` in memory. Estimated: ~1 hour of focused work.
2. **Script writer is still Ollama, not Claude** — the `write_script` function uses local Mistral via Ollama. We proved in the Squeaky Squirrel test that Ollama generates corporate mush. Should be swapped for Anthropic Claude API (~$0.02-0.05 per script). Not yet done.
3. **Glass.aiff crash sound** — used in the bumper; licensed for personal use but unclear for commercial. Should be replaced with a royalty-free SFX before any paid client work.
4. **Hardcoded NMS-specific references** in the JSON — the NMSS template still has NMS-specific keywords. Should be cleaned up into a more neutral `_starter.json` template.

---

## CREDITS

This playbook was built by Doug Morse and Claude Opus 4.6 on 2026-04-11 during the NMSS Polish Loop session. 16+ video versions, ~8 hours of iteration, 6 git commits, and one completely shipped 79.3-second NMS Society fundraiser demo. The playbook captures what we learned so it doesn't have to be relearned.

Go make video #2.
