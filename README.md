# Video Director: an AI video-editing skill for Claude

A Claude skill that edits raw footage the way a senior editor would. Claude analyzes the video,
writes a creative brief, decides every cut, graphic and audio fix in one editable plan, renders it
with FFmpeg, then scores and reviews its own work.

```
raw video ──► analyze.py ──► summary.md + contact sheet ──► Claude: brief + story decisions
                                                                     │
          score.py ◄── render.py ◄── validate_plan.py ◄── edit_plan.json ◄── draft_plan.py (rules)
             │
             └──► objective score + review sheet ──► Claude self-review ──► fix plan ──► re-render
```

## What it does
| Area | Features |
|---|---|
| Understanding | word-level transcript (faster-whisper, ElevenLabs Scribe, or your file), pauses, fillers, sentence energy (hook finding), shot changes, face tracking, loudness/noise/clipping, auto-detected issues, one-image contact sheet |
| Story | creative brief, sentence selection, hook-first reordering (`move` or `tease`) |
| Cutting | filler and dead-air removal by style, cuts snapped to the quietest 10 ms and never inside a word, click-free audio fades |
| Picture | 16:9 / 9:16 / 1:1 reframing that follows the face, blurred fill for vertical sources, punch-in and smooth zooms, B-roll (clips and Ken Burns images), colour (eq, warmth, LUT, vignette), fades |
| Graphics | animated counter, list (items appear as they are spoken), bar chart, quote, lower third, callout and title, placed inside platform safe zones away from faces and captions |
| Captions | word-synced `.ass` captions: word-pop, karaoke, line, minimal; emphasis words; UPPERCASE; filler-free |
| Audio | 3-level speech enhancement, AI voiceover (ElevenLabs), music with sidechain ducking, built-in SFX, two-pass loudness to platform target |
| Quality | plan validator, 15 objective checks scored 0-100, output review sheet, eval suite with regression tracking, unit tests |
| Speed | analysis steps run in parallel and are cached by file fingerprint; pieces render in parallel and are cached; graphics are cached; proxy (half-res) previews; optional GPU encoding |

Styles: `bold_shorts`, `high_energy`, `clean`, `documentary`, `podcast` (`styles/*.json`).
Platforms: `youtube`, `shorts`, `reels`, `tiktok`, `square`, `podcast`.

## Layout
```
.claude/skills/video-director/
├── SKILL.md                 workflow Claude follows
├── references/              editorial knowledge: brief, edit, infographic, audio rules, review rubric
├── styles/                  style profiles (pacing, zoom, captions, graphics, audio, colour)
├── schemas/                 edit_plan JSON schema
├── scripts/                 analyze, draft_plan, validate_plan, render, score, captions, graphics, audio
├── examples/                a complete edit plan using every feature
├── evals/                   test cases, fixture generator, eval runner, failure log
├── tests/                   unit + end-to-end tests
└── preferences.json         the user's saved taste and brand kit
```

## Quick start
Requirements: FFmpeg with libass, Python 3.10+.
```bash
cd .claude/skills/video-director
pip install -r requirements.txt            # add faster-whisper for local transcription
python -m pytest tests -q                  # check everything works
```
**With Claude Code:** this repo already has the skill in `.claude/skills/`, so open the repo and ask
"make a 45-second Short from interview.mp4". To use it in other projects, copy the folder to
`~/.claude/skills/`.
**With claude.ai:** zip `video-director/` and upload it in claude.ai's Skills settings
(long renders are better in Claude Code, which runs on real hardware).

Manual run (what Claude does):
```bash
VD=.claude/skills/video-director/scripts
python $VD/analyze.py talk.mp4 -o talk_edit
python $VD/draft_plan.py talk_edit/analysis.json -o talk_edit/edit_plan.json --style bold_shorts --hook S12 --keep S3-S20
python $VD/render.py talk_edit/edit_plan.json -o talk_short.mp4
python $VD/score.py talk_edit/render_report.json
```

## Roadmap
Next steps, in priority order:
1. **Real test set**: 20-30 real videos with transcripts in `evals/` and blind-judge comparisons (see `evals/README.md`).
2. **Speaker-aware framing**: diarization (pyannote / Scribe speaker ids) to switch crop or angle to the active speaker; multi-camera support.
3. **Finer cuts**: snap to eye blinks and breaths; J/L cuts that offset audio and picture between segments.
4. **NLE export**: FCPXML/EDL so editors can finish in Premiere, Resolve or Final Cut.
5. **Assets**: B-roll search over a tagged local library or a licensed stock API, music matched by mood/BPM, cuts on the beat.
6. **Motion graphics**: optional Remotion renderer for more advanced animated templates and brand kits.
7. **Learning from performance**: map YouTube retention drops to edit decisions and update the rules.
