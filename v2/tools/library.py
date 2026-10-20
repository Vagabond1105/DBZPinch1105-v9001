"""
Phase 4: maintain the curated write-up library (zpinch/analysis/library/).

    .venv/bin/python tools/library.py stats   dataset/sweep-2026-10-19        # -> library/stats.json
    .venv/bin/python tools/library.py suggest dataset/sweep-2026-10-19 ID     # example-run candidates
    .venv/bin/python tools/library.py check   dataset/sweep-2026-10-19        # every entry on its example
    .venv/bin/python tools/library.py show    dataset/sweep-2026-10-19/runs/r00843.npz

stats    counts, for every entry, the sweep runs inside its compare box
         (default: its regime box) and their labels (base runs only: the 48^3 twins repeat base runs). The
         {regime_*} placeholders quote these numbers, so rerun it after
         tools/analyse.py whenever the dataset changes.
suggest  lists clean runs (high confidence, no health flags, finished) of the
         entry's class inside its box, closest to the middle of the box first.
check    analyses each entry's example run and fails unless the run gets the
         entry's class, the selector picks that entry, and every number in the
         text is filled in. It also writes library/examples.json (each
         example's starting parameters), so the program can offer the
         textbook runs without the dataset.
show     prints one run's write-up.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter

import numpy as np

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from zpinch.analysis import analyse_npz  # noqa: E402
from zpinch.analysis import writeup as WU  # noqa: E402
from zpinch.analysis.features import FEATURE_NAMES  # noqa: E402

EXAMPLES_PATH = os.path.join(WU.LIBRARY_DIR, "examples.json")


def read_labels(sweep):
    path = os.path.join(sweep, "analysis", "labels.csv")
    rows = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            for k in FEATURE_NAMES:
                try:
                    row[k] = float(row[k])
                except ValueError:
                    row[k] = math.nan
            rows.append(row)
    return rows


def stats(sweep):
    rows = [r for r in read_labels(sweep) if r["kind"] == "base"]
    out = {"source": f"{os.path.basename(os.path.normpath(sweep))}, {len(rows)} runs at 32^3 "
                     f"(tools/analyse.py labels)",
           "runs": len(rows), "classes": dict(Counter(r["label"] for r in rows)), "entries": {}}
    for e in WU.load(include_unreviewed=True):
        inside = [r for r in rows if WU.box_distance(r, e["compare"]) == 0.0]
        out["entries"][e["id"]] = {"runs": len(inside), "labels": dict(Counter(r["label"] for r in inside))}
    with open(WU.STATS_PATH, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    for eid, s in out["entries"].items():
        print(f"  {eid:<40s} {s['runs']:5d}  {s['labels']}")
    print(f"wrote {WU.STATS_PATH}")


def suggest(sweep, eid, n):
    e = next(e for e in WU.load(include_unreviewed=True) if e["id"] == eid)
    rows = [r for r in read_labels(sweep)
            if r["kind"] == "base" and r["status"] == "ok" and r["label"] == e["class"]
            and r["confidence"] == "high" and r["n_health_flags"] == "0"
            and WU.box_distance(r, e["regime"]) == 0.0]
    if not rows:
        print("no clean run of this class inside the box")
        return
    keys = ["nq_seed", "current", "gravity", "cooling", "resistivity"]
    X = np.array([[r[k] for k in keys] for r in rows])
    X[:, 4] = np.log10(X[:, 4])
    mid, spread = np.median(X, axis=0), X.std(axis=0) + 1e-9
    order = np.argsort(np.abs((X - mid) / spread).sum(axis=1))
    for i in order[:n]:
        r = rows[i]
        print(f"  {r['id']}  " + "  ".join(f"{k} {r[k]:.3g}" for k in keys + ["axial_field", "m1_peak", "shift_peak"])
              + f"  secondary [{r['secondary']}]")


def check(sweep):
    entries, st = WU.load(include_unreviewed=True), WU.load_stats()
    examples, bad = {}, 0
    for e in entries:
        if not e["example"]:
            print(f"  -- {e['id']:<40s} (no example run)")
            continue
        path = os.path.join(sweep, "runs", e["example"] + ".npz")
        from zpinch.analysis.features import load_npz
        _, meta = load_npz(path)
        r = analyse_npz(path, with_ml=False)
        w = WU.writeup(r, meta, entries, st)
        text = " ".join(w["sections"].values()) if w else ""
        problems = []
        if r["label"] != e["class"]:
            problems.append(f"labelled {r['label']}")
        if not w or w["id"] != e["id"]:
            problems.append(f"selector picked {w['id'] if w else None}")
        if "n/a" in text or "infinite" in text:
            problems.append("unfilled number in the text")
        if set(WU.SECTIONS) - set(e["sections"]):
            problems.append("missing sections")
        bad += bool(problems)
        print(f"  {'ok' if not problems else '!!'} {e['id']:<40s} {e['example']}  {'; '.join(problems)}")
        examples[e["id"]] = {"run": e["example"], "label": r["label"], "setup": meta["setup"],
                             "live": meta["live"], "t_end": r["features"]["t_final"]}
    with open(EXAMPLES_PATH, "w") as fh:
        json.dump(examples, fh, indent=1, sort_keys=True)
    print(f"wrote {EXAMPLES_PATH}; {bad} entr{'y' if bad == 1 else 'ies'} with problems")
    return bad


def show(path):
    from zpinch.analysis.features import load_npz
    _, meta = load_npz(path)
    r = analyse_npz(path, with_ml=False)
    w = WU.writeup(r, meta)
    if w is None:
        print(f"no library entry for {r['label']}")
        return
    print(f"{w['title']}\n")
    for h, txt in w["sections"].items():
        print(f"{h}\n  {txt}\n")
    print(WU.match_text(w))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats").add_argument("sweep")
    p = sub.add_parser("suggest")
    p.add_argument("sweep")
    p.add_argument("entry")
    p.add_argument("--n", type=int, default=6)
    sub.add_parser("check").add_argument("sweep")
    sub.add_parser("show").add_argument("run")
    a = ap.parse_args()
    if a.cmd == "stats":
        stats(a.sweep)
    elif a.cmd == "suggest":
        suggest(a.sweep, a.entry, a.n)
    elif a.cmd == "check":
        sys.exit(1 if check(a.sweep) else 0)
    else:
        show(a.run)


if __name__ == "__main__":
    main()
