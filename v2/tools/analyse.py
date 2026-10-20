"""
Phase 1 on saved runs: label and explain one run, or a whole sweep.

    .venv/bin/python tools/analyse.py dataset/sweep-2026-10-19/runs/r00843.npz   # one report
    .venv/bin/python tools/analyse.py dataset/sweep-2026-10-19/runs/r00843.npz --json
    .venv/bin/python tools/analyse.py dataset/sweep-2026-10-19                   # whole sweep

For a sweep directory it writes DIR/analysis/:
    labels.csv     one row per run: id, kind, stratum, twin, label, confidence,
                   secondary classes, then every feature (zpinch/analysis/features.py)
    features.md    what each feature column means, with units
    summary.txt    class counts (all runs and the broad stratum = a uniform
                   sample), borderline share, theory checks, 32^3 vs 48^3 label
                   agreement, numerical-health flags
These are the training data for Phase 3.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter

import numpy as np

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from zpinch.analysis import analyse_npz, format_report  # noqa: E402
from zpinch.analysis.features import FEATURES, FEATURE_NAMES  # noqa: E402
from zpinch.analysis.rules import CLASSES  # noqa: E402

# n q bins for the Kruskal-Shafranov check (seeded helix; runs without
# gravity or cooling, where the kink is the only thing that can happen)
NQ_BINS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 10.0]


def _json_default(x):
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    raise TypeError(type(x))


def one(path, as_json):
    r = analyse_npz(path)
    if as_json:
        print(json.dumps(r, indent=1, default=_json_default))
    else:
        print(format_report(r))


def table(counter, keys, total):
    return "\n".join(f"    {k:<20s} {counter.get(k, 0):5d}  {100 * counter.get(k, 0) / max(total, 1):5.1f} %"
                     for k in keys)


def sweep(d):
    runs_dir = os.path.join(d, "runs")
    files = sorted(f for f in os.listdir(runs_dir) if f.endswith(".npz") and ".part" not in f)
    out = os.path.join(d, "analysis")
    os.makedirs(out, exist_ok=True)
    rows = []
    for name in files:
        r = analyse_npz(os.path.join(runs_dir, name), with_ml=False)
        with np.load(os.path.join(runs_dir, name)) as z:
            meta = json.loads(str(z["meta"]))
        rows.append({"id": meta["id"], "kind": meta["kind"], "stratum": meta["stratum"],
                     "twin": meta["twin"] or "", "status": meta["status"], "r": r})

    with open(os.path.join(out, "labels.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "kind", "stratum", "twin", "status", "label", "confidence", "secondary",
                    "n_health_flags"] + FEATURE_NAMES)
        for row in rows:
            r = row["r"]
            w.writerow([row["id"], row["kind"], row["stratum"], row["twin"], row["status"], r["label"],
                        r["confidence"], ";".join(r["secondary"]), len(r["health"])]
                       + [f"{r['features'][k]:.6g}" for k in FEATURE_NAMES])
    with open(os.path.join(out, "features.md"), "w") as fh:
        fh.write("| column | unit | meaning |\n|---|---|---|\n")
        for name, unit, text in FEATURES:
            fh.write(f"| {name} | {unit} | {text} |\n")

    base = [x for x in rows if x["kind"] == "base"]
    broad = [x for x in base if x["stratum"] == "broad"]
    L = [f"Phase 1 rule labels for {d}", f"{len(rows)} runs ({len(base)} at 32^3, "
         f"{len(rows) - len(base)} 48^3 twins); analysis {rows[0]['r']['version']}", ""]
    L += [f"Classes, all 32^3 runs (n = {len(base)}):",
          table(Counter(x["r"]["label"] for x in base), CLASSES, len(base)), ""]
    L += [f"Classes, broad stratum only (uniform sample of the swept box, n = {len(broad)}):",
          table(Counter(x["r"]["label"] for x in broad), CLASSES, len(broad)), ""]
    low = Counter(x["r"]["label"] for x in base if x["r"]["confidence"] == "low")
    allc = Counter(x["r"]["label"] for x in base)
    L.append("Borderline (a decisive number within 15 % of its threshold):")
    L += [f"    {k:<20s} {low.get(k, 0):4d} of {allc.get(k, 0):4d}" for k in CLASSES if allc.get(k)]
    L.append(f"    total                {sum(low.values()):4d} of {len(base):4d}")
    L.append("")

    sec = Counter(s for x in base for s in x["r"]["secondary"])
    L += ["Secondary phases (happened, but did not name the run):",
          "    " + ", ".join(f"{k} {v}" for k, v in sec.most_common()), ""]

    pure = [x for x in base if x["r"]["features"]["gravity"] == 0 and x["r"]["features"]["cooling"] == 0]
    L.append(f"Kruskal-Shafranov check: label vs n q of the seeded helix (n q < 1: unstable; "
             f"runs without gravity or cooling, n = {len(pure)}):")
    for lo, hi in zip(NQ_BINS[:-1], NQ_BINS[1:]):
        sel = [x["r"]["label"] for x in pure if lo <= x["r"]["features"]["nq_seed"] < hi]
        c = Counter(sel)
        L.append(f"    n q {lo:4.2f}-{hi:<5.2f} n = {len(sel):3d}   " +
                 ", ".join(f"{k} {c[k]}" for k in CLASSES if c.get(k)))
    g = [x["r"]["features"]["m1_gamma_tA"] for x in base if x["r"]["features"]["m1_peak"] >= 0.1]
    if g:
        L.append(f"    kink growth rate gamma * t_A (runs where it grew): median {np.median(g):.2f}, "
                 f"10-90 % {np.percentile(g, 10):.2f}-{np.percentile(g, 90):.2f}")
    L.append("")

    by_id = {x["id"]: x for x in rows}
    twins = [(by_id[x["twin"]]["r"]["label"], x["r"]["label"], x["twin"])
             for x in rows if x["kind"] == "res48" and x["twin"] in by_id]
    if twins:
        same = sum(a == b for a, b, _ in twins)
        L.append(f"Resolution check: same label at 32^3 and 48^3 in {same} of {len(twins)} twins")
        for a, b, tid in twins:
            if a != b:
                L.append(f"    {tid}: {a} (32^3) -> {b} (48^3)")
        L.append("")

    hf = Counter()
    for x in base:
        for note in x["r"]["health"]:
            hf["vacuum floors > 5 % E0" if note.startswith("vacuum") else
               "energy budget error > 1e-3" if note.startswith("energy") else "stopped early"] += 1
    L += ["Numerical health flags (32^3):"] + [f"    {k:<28s} {v}" for k, v in hf.most_common()]
    text = "\n".join(L) + "\n"
    with open(os.path.join(out, "summary.txt"), "w") as fh:
        fh.write(text)
    print(text)
    print(f"wrote {out}/labels.csv, features.md, summary.txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="a run .npz, or a sweep directory")
    ap.add_argument("--json", action="store_true", help="one run: print the full analysis as JSON")
    args = ap.parse_args()
    if os.path.isdir(args.path):
        sweep(args.path)
    else:
        one(args.path, args.json)


if __name__ == "__main__":
    main()
