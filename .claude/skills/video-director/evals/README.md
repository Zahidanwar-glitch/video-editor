# Evals: measure every change

Top skills get good through a loop: **measure every output -> find failures -> fix -> re-measure**.

```bash
python evals/run_evals.py                 # all cases, proxy renders, compares with the previous run
python evals/run_evals.py --only NAME     # one case
python evals/run_evals.py --full-res      # final-quality renders
python -m pytest tests -q                 # fast unit tests (timeline, captions, cuts, validation, e2e)
```

Each run writes `results/<timestamp>.json` and prints the score per case, the change versus the last
run, and which checks got worse. Exit code 1 means a regression (score drop > 2 points or a crash).

## Building a real test set (do this next)
The bundled cases use a synthetic fixture (`make_fixture.py`): tone "speech" with planted problems.
It tests the machinery, not taste. Add 20-30 real videos you have rights to:

1. Put footage in `evals/footage/` (git-ignored) with a word-level transcript JSON if you have one.
2. Cover the variety you edit: talking head, interview (2 speakers), tutorial/screen, vlog, podcast,
   noisy audio, phone vertical footage, multi-language, very long (30+ min).
3. For each, add `cases/<name>.json`. Use `draft` to test the rules, or have Claude write the plan
   and save it as a fixed `plan` to lock in a known-good edit (regression test for the renderer).
4. Where you have a professional's edit of the same footage, keep it next to the case and use the
   blind judge prompt in `references/review-checklist.md` to compare.

## When something goes wrong
Log it in `failure-log.md` (what, root cause, fix, eval case), turn it into a rule in `references/`
or a code fix, add a case that reproduces it, and run the evals to confirm the fix with no regressions.
