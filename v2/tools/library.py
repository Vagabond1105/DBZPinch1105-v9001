"""
Phase 4: maintain the curated write-up library (zpinch/analysis/library/).

    .venv/bin/python tools/library.py stats   dataset/sweep-2026-10-19        # -> library/stats.json
    .venv/bin/python tools/library.py suggest dataset/sweep-2026-10-19 ID     # example-run candidates
    .venv/bin/python tools/library.py check   dataset/sweep-2026-10-19        # every entry on its example
    .venv/bin/python tools/library.py show    dataset/sweep-2026-10-19/runs/r00843.npz [--html out.html]
    .venv/bin/python tools/library.py replay  [ID ...] [--threads 8]           # textbook runs reproduce?

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
show     prints one run's write-up (--html also saves its full HTML report).
replay   re-simulates each textbook run from examples.json alone, the way
         the GUI's Textbook run list does (multi-threaded, with tracers),
         and fails unless it reaches the entry's class again. The sweep ran
         single-threaded; thread count changes rounding in the parallel
         loops, and a kink grows from rounding-level noise, so this checks
         the outcome is robust rather than assuming it.
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
from zpinch.analysis import rules as RU  # noqa: E402
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
                except (KeyError, ValueError):      # a feature newer than the labels table
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
    # the Kruskal-Shafranov bands quoted in the report's criteria table
    # (explain.criteria), with the same "little gravity or cooling" cut as
    # the library's compare boxes so the two never quote different counts
    out["nq_bands"] = []
    for lo, hi in ((0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, math.inf)):
        box = {"nq_seed": (lo, hi), "gravity": (0.0, 0.3), "cooling": (0.0, 0.3)}
        inside = [r for r in rows if WU.box_distance(r, box) == 0.0 and r["nq_seed"] < hi]
        out["nq_bands"].append({"lo": lo, "hi": hi, "runs": len(inside),
                                "labels": dict(Counter(r["label"] for r in inside)),
                                "no_kink": sum(r["m1_peak"] < RU.GROWN for r in inside)})
    with open(WU.STATS_PATH, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    for eid, s in out["entries"].items():
        print(f"  {eid:<40s} {s['runs']:5d}  {s['labels']}")
    for b in out["nq_bands"]:
        print(f"  n q {b['lo']:g}..{b['hi']:g}: {b['runs']} runs, no kink {b['no_kink']}, {b['labels']}")
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


def show(path, html_path=None):
    from zpinch.analysis.features import load_npz
    h, meta = load_npz(path)
    r = analyse_npz(path, with_ml=False)
    if html_path:
        from zpinch.analysis import report as RP
        b = RP.bundle(h, meta)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(b["html"])
        print(f"wrote {html_path}")
    w = WU.writeup(r, meta)
    if w is None:
        print(f"no library entry for {r['label']}")
        return
    print(f"{w['title']}\n")
    for h, txt in w["sections"].items():
        print(f"{h}\n  {txt}\n")
    print(WU.match_text(w))


def replay(ids, threads):
    import time
    import numba
    from zpinch.analysis import features as FE
    from zpinch.analysis.explain import analyse
    from zpinch.params import LiveParams, SetupParams
    from zpinch.pinch import ZPinch
    numba.set_num_threads(min(threads, numba.config.NUMBA_NUM_THREADS))
    numba.set_parallel_chunksize(4)                  # as the GUI worker
    ex = WU.load_examples()
    bad = 0
    for eid in ids or list(ex):
        x = ex[eid]
        t0 = time.perf_counter()
        sim = ZPinch(SetupParams(**{**x["setup"], "n_tracers": SetupParams().n_tracers}),
                     LiveParams(**x["live"]))
        while sim.t < x["t_end"]:
            sim.step()
        r = analyse(*FE.run_from_sim(sim), with_ml=False)
        w = r["writeup"] or {}
        ok = r["label"] == x["label"]
        bad += not ok
        print(f"  {'ok' if ok else '!!'} {eid:<34s} {x['run']}  sweep {x['label']:<20s} replay {r['label']:<20s}"
              f" entry {w.get('id')}  m1 peak {r['features']['m1_peak']:.2f}  ({time.perf_counter() - t0:.0f} s)",
              flush=True)
    print(f"{bad} textbook run{'' if bad == 1 else 's'} changed outcome")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats").add_argument("sweep")
    p = sub.add_parser("suggest")
    p.add_argument("sweep")
    p.add_argument("entry")
    p.add_argument("--n", type=int, default=6)
    sub.add_parser("check").add_argument("sweep")
    p = sub.add_parser("show")
    p.add_argument("run")
    p.add_argument("--html", help="also save the run's full HTML report here")
    p = sub.add_parser("replay")
    p.add_argument("ids", nargs="*", help="entry ids (default: every textbook run)")
    p.add_argument("--threads", type=int, default=8, help="physics threads (GUI default on 12 cores: 8)")
    a = ap.parse_args()
    if a.cmd == "stats":
        stats(a.sweep)
    elif a.cmd == "suggest":
        suggest(a.sweep, a.entry, a.n)
    elif a.cmd == "check":
        sys.exit(1 if check(a.sweep) else 0)
    elif a.cmd == "replay":
        sys.exit(1 if replay(a.ids, a.threads) else 0)
    else:
        show(a.run, a.html)


if __name__ == "__main__":
    main()
