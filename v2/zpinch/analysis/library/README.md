# Curated write-up library

One file per entry. The analysis picks one entry per run and fills in the
run's numbers; the format and the selection rule are documented at the top
of `../writeup.py`. Plain-language overview: `docs/05.3 - V3 Phase 4 Write-up Library.md`.

| File | What it is |
|---|---|
| `*.md` | the entries: front matter (class, regime box, compare box, example run, preset, review state), then *What happened*, *Why*, *Try next* |
| `stats.json` | for each entry, the sweep runs inside its compare box and their labels; fills the `{regime_*}` numbers. Generated: `tools/library.py stats DIR` |
| `examples.json` | each example run's starting parameters, so the textbook runs can be loaded without the dataset. Generated: `tools/library.py check DIR` |

## Reviewing an entry

`reviewed:` is `no` (never used), `data-checked` (every claim checked
against the sweep statistics and the example run) or `yes` (a physicist has
read it too). To review one:

1. `.venv/bin/python tools/library.py show dataset/sweep-2026-10-19/runs/<example>.npz` prints it filled in.
2. Check each sentence of *Why* against notes 04 (Part 0) or a textbook, and
   each *Try next* against what actually happens if you do it.
3. Change `reviewed: data-checked` to `reviewed: yes`.

## After the dataset changes

```bash
.venv/bin/python tools/analyse.py dataset/sweep-2026-10-19        # relabel
.venv/bin/python tools/library.py stats dataset/sweep-2026-10-19  # recount
.venv/bin/python tools/library.py check dataset/sweep-2026-10-19  # every entry on its example
```
