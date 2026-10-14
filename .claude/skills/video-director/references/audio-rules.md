# Audio rules: voice, music, SFX, loudness

Audio is half the video. Viewers forgive soft picture; they leave over bad sound.

## Speech cleanup (`audio.enhance_speech`)
Pick from the issues in summary.md:
| Condition | Setting | What it does |
|---|---|---|
| Clean studio audio | `"light"` (default) | gentle high-pass, light denoise, 2:1 compression, de-ess |
| Noise floor -50..-40 dBFS, some room | `true` (medium) | stronger denoise, 3:1 compression, presence boost |
| Noise floor > -40, clipping, echoey | `"strong"` | declick, heavy denoise, mud cut, presence, stronger de-ess |
| Music performance / ASMR / ambience is the content | `false` | leave it untouched |
If `strong` still sounds bad (check the preview), say so and offer: an external speech enhancer
(e.g. Adobe Enhance Speech, if connected), re-recording the key lines, or an AI voiceover.

## Voiceover (`audio.voiceover`)
- Use when there is no narration, or the original is unusable and the speaker consents to a replacement.
- Write the script from the brief: short sentences, spoken style, ~150 wpm, hook in the first line.
- Generate: `python scripts/audio.py tts script.txt -o $WORK/vo.mp3 --voice VOICE_ID`
  (`audio.py voices` lists voices), or use the ElevenLabs connector and save the file.
- `mode: "replace"` swaps the dialogue track; `"mix"` lays narration over the original (e.g. over B-roll).
- Never clone or imitate a real person's voice without their explicit consent.

## Music (`audio.music`)
- Match the arc: energetic for bold/high_energy, warm/minimal for clean, cinematic for documentary.
  Only use tracks the user owns or has licensed (or royalty-free libraries they have access to).
- `volume_db` -18 to -26 under speech (style default); `duck_db` -12 to -18 makes it dip whenever
  someone talks (sidechain), and swell back in pauses.
- Start music on the first beat of the hook or right after it; fade out over 1-2 s at the end
  (`fade_out`). Use `start_in` to skip a slow intro.
- No music under emotional confessions or jokes' punchlines if it competes; drop it for those segments
  by splitting the edit or lowering `volume_db`.

## SFX (`audio.sfx`)
- Built in: `pop`, `click`, `whoosh`, `riser`, `ding` (or `file` for your own). `at` in source time.
- Use to punctuate graphics and transitions, -8 to -14 dB. Fewer is better outside high-energy styles.

## Loudness (automatic)
Final mix is two-pass loudness-normalised to `output.lufs` (-14 for YouTube/social, -16 podcasts) with
a -1.5 dBTP ceiling. score.py verifies it.
