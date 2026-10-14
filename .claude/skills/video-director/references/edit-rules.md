# Edit rules: structure, pacing, cuts, framing

All plan times are SOURCE seconds (from summary.md / analysis.json). The renderer maps them through
the cuts, so decide in source time and never compute output times yourself.

## Segments (story order)
- `segments` are kept source ranges **in output order**. Reordering is how you build structure
  (hook first, move a payoff later, drop tangents).
- Start a segment ~0.06-0.12s before the first word and end ~0.12-0.35s after the last (draft_plan does
  this from the style's `lead_pad`/`tail_pad`). Never start or end inside a word.
- Use `role` (hook/setup/body/payoff/cta/tease) so the plan reads like a story outline.

## Cuts inside segments (`cuts_removed`)
- Hard fillers (um, uh, erm) are cut with their surrounding gap. Soft fillers (like, so, basically,
  you know) are cut by you only when they add nothing; they're flagged `filler: "soft"` in analysis.json.
- Pauses: tighten to the style's `max_pause`; after a sentence end keep `pause_after_sentence`.
  **Keep longer pauses deliberately** after a punchline, an emotional line, or a question to the viewer
  (remove that cut from the plan and note why).
- Remove false starts and repeated takes: cut from the start of the bad attempt to the start of the good one.
- The renderer snaps each cut to the quietest 10 ms within +-50 ms (never inside a word) and to the
  frame grid, and adds 8 ms audio fades, so cuts don't click. You still choose the cut points.
- Laughter and reactions are content: don't cut them as "silence".

## Pacing by style (see styles/*.json)
| Style | Visual change every | Max pause | Captions | Zooms |
|---|---|---|---|---|
| high_energy | 1-2 s | 0.15 s | 2 words, pop | punch 1.2x every 2 s |
| bold_shorts | 2-3 s | 0.25 s | 3 words, pop | punch 1.15x every 3 s |
| podcast | ~4 s | 0.4 s | 4 words, karaoke | punch 1.1x every 7 s |
| documentary | ~5 s | 0.6 s | off / minimal | smooth 1.06x push-ins |
| clean | ~6 s | 0.45 s | sentence lines | rare smooth 1.08x |
"Visual change" = a cut, zoom change, graphic or B-roll. score.py measures it.
Vary rhythm: speed up through lists and setup, slow down (longer holds, no zoom) on the emotional peak.

## Zooms (`zooms`)
- `punch`: instant scale change on a cut or sentence start; it hides jump cuts. Alternate in/out so it
  doesn't feel stuck (styles set `alternate`).
- `smooth`: eased push-in over 2-6 s for emphasis or tension; use sparingly (one per 20-30 s).
- Zoom centres on the detected face and keeps eyes in the upper third. Max 1.25x on 1080p sources
  (more looks soft); max 1.4x on 4K sources.
- Don't zoom while a full-screen graphic, title or B-roll is on screen.

## Framing (reframe)
- 16:9 -> 9:16 crops around the face per piece (median face position). If two people talk, split
  the segment and set `reframe_x` per segment to follow the speaker (use `analysis.faces.samples`).
- Vertical source -> 16:9 uses a blurred-background fill automatically.
- Check `review_sheet.jpg`: heads must not be cut off; leave headroom.

## B-roll (`broll`)
- Use B-roll to illustrate concrete nouns ("our warehouse", "the city"), cover jump cuts, and reset
  attention on long talking-head stretches (every 8-15 s in YouTube edits).
- 1.5-4 s per shot; start it on the word it illustrates; speech continues underneath (the cut is
  picture-only, which feels like an L-cut).
- Images get an automatic slow push-in (Ken Burns). Only use files the user supplied or licensed;
  entries without `file` are skipped (use `query` to tell the user what footage would help).

## Colour (`color`)
- Fix before style: `brightness`/`gamma` for exposure, then `contrast` 1.03-1.1, `saturation` 0.9-1.2,
  `warmth` -0.3..0.3. `lut` for a look (.cube). Protect skin: if faces look orange or magenta, reduce
  warmth/saturation. `vignette` for documentary/cinematic.

## Platform specs (common.py PLATFORMS)
| Platform | Size | Loudness | Unsafe areas (UI) |
|---|---|---|---|
| youtube | 1920x1080 | -14 LUFS | bottom 10% (progress bar) |
| shorts | 1080x1920 | -14 | top 12%, bottom 22%, right 14% |
| reels | 1080x1920 | -14 | top 14%, bottom 25%, right 14% |
| tiktok | 1080x1920 | -14 | top 10%, bottom 25%, right 16% |
| square | 1080x1080 | -14 | small margins |
| podcast | 1920x1080 | -16 | bottom 10% |
Captions and graphics are kept inside the safe zone automatically; `position_y` must stay above the
bottom unsafe band.

## Captions (`captions`)
- Short-form: always on (most viewers watch muted). 2-4 words per line, word-synced, highlight the
  active word, UPPERCASE for bold styles. Put 1-3 key words per sentence in `emphasis_words` (numbers,
  outcomes, emotional words).
- Long-form: sentence lines (`line`) or `minimal`, max ~7 words, lower area.
- `drop_fillers: true` keeps captions clean even when a filler stays in the audio.
