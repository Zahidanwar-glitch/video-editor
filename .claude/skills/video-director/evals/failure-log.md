# Failure log

Every bad edit becomes a rule and a test. Add an entry whenever a user corrects an edit or you spot a
failure in review. Then: add/adjust a rule in `references/`, add an eval case that reproduces it, and
check `run_evals.py` shows the fix without regressions.

| Date | Footage / case | What went wrong | Root cause | Fix (rule / code) | Eval case |
|---|---|---|---|---|---|
| 2026-10-14 | fixture, teased hook | Second play of the hook had no captions | captions mapped each word to its first occurrence only | captions.output_words maps per piece | fixture_clean_youtube |
| 2026-10-14 | fixture + music | dead-air check passed with a 2 s pause | music masked the silence in the audio measurement | score.py measures speech gaps from the transcript | (full-feature plan) |
| 2026-10-14 | any | colour pass 6x slower than needed | colorbalance converts to RGB | warmth via YUV lutyuv | all |
