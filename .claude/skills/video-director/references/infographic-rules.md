# Infographic rules: which graphic, when, and how it reads

Graphics turn what is *said* into something *seen*. Each must earn its place: if removing it loses
nothing, remove it.

## Trigger -> graphic
| Speaker says... | `type` | Key fields |
|---|---|---|
| A number, %, money, multiple ("grew 300%") | `counter` | `value`, `prefix` ("$"), `suffix` ("%", "K", "x"), `label` |
| A comparison ("from 1.2M to 4.8M", "X vs Y") | `bar` | `bars: [{label, value}]`, `title`, `prefix`/`suffix` |
| "N reasons / lessons / steps / mistakes" | `list` | `title`, `items`, `item_times` (source time of each item) |
| A memorable line, a testimonial | `quote` | `text`, `attribution` |
| A person's first appearance | `lower_third` | `title` (name), `subtitle` (role) |
| A key claim / reaction to emphasize | `callout` | `text` (1-4 words) |
| Chapter start, intro, end card | `title` | `title`, `subtitle` |

`suggestions` in the draft plan lists detected numbers and lists; review and promote the good ones.

## Wording
- Label and callout: 2-5 words, no full sentences. "Revenue growth", not "Last year our revenue grew".
- List items: 1-4 words each, parallel grammar ("Start small / Ship fast / Listen to users").
- Quote: trim to the core (max ~14 words); keep the speaker's words, don't paraphrase.
- Numbers must be exactly what was said. Never invent data, years, or sources.

## Timing
- `at` = source start of the word that triggers it, minus ~0.1 s, so the graphic lands with the word.
- `dur`: counter/callout 2-3 s; bar 2.5-4 s; quote 3-5 s (reading time ~ 0.3 s/word + 1 s);
  list = until ~1 s after the last item is said; lower third 3-4 s; title 1.5-3 s.
- `item_times` makes each list item appear exactly when it's spoken: this is what makes it feel edited.
- Add an SFX on entry for energetic styles (pop for counters/callouts, whoosh for lists/titles) at -10 dB.

## Density and placement
- Respect the style's `graphics.min_gap_s` (bold 6 s ... clean 15 s). One graphic on screen at a time.
- Placement is automatic (`position: auto`): vertical video -> top area, or above the captions if the
  face is high; horizontal -> the side away from the face; lower thirds bottom-left; titles centred.
  Override with `top|center|bottom|left|right` only when review_sheet.jpg shows a problem.
- Don't stack a graphic on a zoom-in that pushes the face into it; score.py checks face and caption overlap.
- Use one `accent` colour per video (style default or the user's brand colour from preferences.json).
