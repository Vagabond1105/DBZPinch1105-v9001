"""
Phase 6: a demo gallery that opens in any browser, no GUI needed.

    .venv/bin/python tools/demo.py dataset/sweep-2026-10-19 demo/
    xdg-open demo/index.html

Writes OUT/index.html, a single page with:
  - the headline numbers from models/metrics.json (both models and the
    baselines), and the outcome map, calibration and confusion figures;
  - one card per textbook run (zpinch/analysis/library/examples.json),
    linking to its full standalone report OUT/<entry>.html, built from the
    saved sweep run (no simulation, ~1 s per run).
The pages are self-contained (figures embedded), so the folder can be
zipped and sent. Nothing here is computed afresh: it only presents what the
pipeline already measured.
"""

import argparse
import base64
import html
import json
import os
import sys

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from zpinch.analysis import features as FE  # noqa: E402
from zpinch.analysis import report as RP  # noqa: E402
from zpinch.analysis import writeup as WU  # noqa: E402
from zpinch.analysis.explain import NAMES  # noqa: E402
from zpinch.analysis.model import MODEL_DIR  # noqa: E402

FIGURES = (("outcome_map.png", "What the outcome predictor expects, before any simulation, over axial field "
                               "and drive current. Dots are real sweep runs; the lines are n q = 0.5 and 1."),
           ("calibration.png", "When a model says 80 %, is it right 80 % of the time? Points on the diagonal "
                               "mean honest probabilities."),
           ("confusion.png", "Test runs: rows are the physics rules' label, columns the models' answer."))


def _img(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def headline(metrics):
    def pct(x):
        return f"{100 * x:.1f} %"
    a, b = metrics["run_classifier"]["test"], metrics["outcome_predictor"]["test"]
    rule = metrics["outcome_predictor"]["baseline_nq_rule"]
    rows = [("Run classifier (a): what happened, from the finished run", pct(a["accuracy"]),
             pct(a["balanced_accuracy"])),
            ("Outcome predictor (b): what will happen, from the settings alone", pct(b["accuracy"]),
             pct(b["balanced_accuracy"])),
            ("Baseline: the Kruskal-Shafranov number n q alone", pct(rule["accuracy"]),
             pct(rule["balanced_accuracy"]))]
    body = "".join(f"<tr><td>{html.escape(n)}</td><td><b>{x}</b></td><td>{y}</td></tr>" for n, x, y in rows)
    return (f"<table><tr><th>model</th><th>accuracy</th><th>balanced accuracy</th></tr>{body}</table>"
            f'<p class="meta">On {b["n"]} test runs locked away before training '
            f'({metrics["info"]["n_runs"]} finished runs in all). Details: models/MODEL_CARD.md.</p>')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweep")
    ap.add_argument("out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    runs = os.path.join(a.sweep, "runs")
    with open(os.path.join(MODEL_DIR, "metrics.json")) as fh:
        metrics = json.load(fh)

    cards = []
    for eid, ex in WU.load_examples().items():
        h, meta = FE.load_npz(os.path.join(runs, ex["run"] + ".npz"))
        b = RP.bundle(h, meta)
        r, w = b["report"], b["report"]["writeup"]
        with open(os.path.join(a.out, eid + ".html"), "w", encoding="utf-8") as fh:
            fh.write(RP.html(r, b["images"], meta, title=f"{w['title']} ({ex['run']})"))
        thumb = "data:image/png;base64," + base64.b64encode(b["images"]["modes.png"]).decode()
        first = w["sections"]["What happened"]
        cards.append(
            f'<a class="card" href="{html.escape(eid)}.html"><img src="{thumb}" alt="">'
            f'<span class="cls">{html.escape(NAMES[r["label"]])}</span>'
            f'<b>{html.escape(w["title"])}</b>'
            f'<span class="meta">sweep run {ex["run"]} · {html.escape(RP.run_line(r["features"]))}</span>'
            f'<span>{html.escape(first)}</span></a>')
        print(f"  {eid:<34s} {ex['run']}  {r['label']}")

    figs = "".join(f'<figure><img src="{_img(os.path.join(MODEL_DIR, n))}" alt="{n}">'
                   f'<figcaption class="meta">{html.escape(c)}</figcaption></figure>' for n, c in FIGURES)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Z-pinch MHD v3 demo</title>
<style>{RP.STYLE}
main {{ max-width: 1100px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
.card {{ display: flex; flex-direction: column; gap: 6px; padding: 12px; border: 1px solid var(--rule);
        border-radius: 10px; background: var(--card); color: var(--fg); text-decoration: none; }}
.card:hover {{ border-color: var(--accent); }}
.card img {{ width: 100%; border-radius: 6px; background: #fff; }}
.cls {{ color: var(--accent); font-size: 0.85rem; font-weight: 600; }}
figure {{ margin: 16px 0; }} figure img {{ max-width: 100%; border-radius: 6px; background: #fff; }}
</style>
</head>
<body>
<main>
<h1>Z-pinch MHD v3: what happened, why, and what to try next</h1>
<p>A 3D magnetohydrodynamics simulator of a plasma column that labels and explains each run. Physics rules
give the outcome and a timeline, the energy bookkeeping and stability criteria explain it, a curated
library writes it up in plain language, and two models trained on {metrics["info"]["n_runs"]} overnight
simulations cross-check it and forecast it before the run starts. Each card below is a real run from the
sweep; click it for its full report.</p>
<h2>How well it works</h2>
{headline(metrics)}
<h2>Textbook runs</h2>
<div class="grid">
{"".join(cards)}
</div>
<h2>The models, in pictures</h2>
{figs}
<p class="meta">Generated by tools/demo.py from dataset/{os.path.basename(os.path.normpath(a.sweep))};
technical overview: docs/06 - V3 Technical Overview.md.</p>
</main>
</body>
</html>
"""
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {os.path.join(a.out, 'index.html')} and {len(cards)} reports")


if __name__ == "__main__":
    main()
