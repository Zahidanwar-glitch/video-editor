# Review checklist (self-review and eval judge)

Run `score.py` first and fix every `FIX` line: those are objective failures. Then look at
`review/review_sheet.jpg` (and the preview if you can play it) and grade the subjective part below.

## Subjective rubric (1-5 each)
| # | Criterion | 5 means |
|---|---|---|
| 1 | Hook | First 3 s would stop a scroller: surprising, specific, clear without context |
| 2 | Story | Every kept moment serves `brief.message`; clear beginning, middle, payoff |
| 3 | Pacing | Never drags, never breathless; rhythm varies with content |
| 4 | Cut quality | No audible clicks, no clipped words, no jarring jumps (zoom/B-roll hides jump cuts) |
| 5 | Framing | Faces fully in frame with headroom; reframe follows the speaker |
| 6 | Graphics | Readable in 1 s, exact numbers, land on the word, don't cover faces or captions |
| 7 | Captions | In sync, 2-4 word chunks (short-form), key words emphasized, inside safe zone |
| 8 | Sound | Clear voice, music supports not competes, consistent level |
| 9 | Polish | Colour consistent, no black/frozen frames, clean ending |
| 10 | Platform fit | Right aspect, length, safe zones, style matches the platform and audience |

Pass = objective score >= 90 AND every subjective item >= 4. Otherwise change the plan and re-render
(max 2 rounds), then report what still falls short and why.

## Judge prompt (for evals: compare two edits of the same footage, blind)
> You are a senior video editor judging two edits (A and B) of the same raw footage for <platform>.
> You see each edit's review sheet, transcript of kept lines, and objective score report.
> Grade both on the 10 criteria above (1-5), justify each grade in one line, then say which edit is
> better overall and why in 2 sentences. Do not favour an edit because it is longer, busier or has
> more effects; favour the one a real audience would watch to the end.

## Common failures to look for
- Hook that needs context ("And that's why...") or opens on a filler.
- Graphic text that paraphrases or invents a number.
- Punch-in zoom pushing the face into a graphic or out of frame.
- Captions covering a lower third or sitting in the platform's UI area.
- Music louder than speech during fast talking; music ending abruptly.
- Pause kept after the wrong line, or the dramatic pause removed after the key line.
