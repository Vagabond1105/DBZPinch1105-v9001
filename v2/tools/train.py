"""
Phase 3: train and evaluate the two models on a sweep, write a model card.

    .venv/bin/python tools/train.py dataset/sweep-2026-10-19

What happens, in order:
  1. Every saved run is analysed by the physics rules (zpinch/analysis),
     which gives its label. Only finished 32^3 runs are used ("ok"; runs
     stopped by the wall-clock cap are left out, their label is "so far").
  2. 20 % of the runs are locked away as a TEST set before anything else.
  3. On the other 80 %, 5-fold cross-validation picks the tree settings
     (the ones with the best log loss, i.e. the most honest probabilities).
  4. The chosen model is scored once on the TEST set, against baselines:
     always guessing the commonest class, and for (b) a one-line physics
     rule using only n q (rules.py / docs 05.1 section 5).
  5. Both models are refit on all runs and saved to v2/models/, with
     MODEL_CARD.md, metrics.json and figures (confusion matrices,
     calibration, the outcome map).

Models: zpinch/analysis/model.py. Plan: docs/05 section 8, phases 3a and 3b.
"""

import argparse
import hashlib
import itertools
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

import numpy as np

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,  # noqa: E402
                             f1_score, log_loss, precision_recall_fscore_support)
from sklearn.model_selection import StratifiedKFold, train_test_split  # noqa: E402

from zpinch.analysis import analyse  # noqa: E402
from zpinch.analysis import features as FE  # noqa: E402
from zpinch.analysis import model as M  # noqa: E402
from zpinch.analysis.explain import NAMES  # noqa: E402
from zpinch.params import SetupParams, LiveParams  # noqa: E402

SEED = 2026
TEST_FRACTION = 0.2
MIN_CLASS = 10            # a class needs this many runs to be learned at all
# Small grid: ~1000 rows cannot support fine tuning, and every extra
# setting tried is another chance to fit noise in the validation folds.
# A trial (2026-10-20) found the smaller, more regularised trees gave the
# best log loss (0.26 vs 0.44) at the same accuracy, so the grid sits there.
GRID = {"learning_rate": [0.05], "max_leaf_nodes": [4, 7, 15], "l2_regularization": [0.0, 1.0]}
MAX_ITER = 200
VERSION = "1.0"


def nq_rule(f):
    """Physics baseline for (b): the n q table of docs/05.1 section 5, nothing else."""
    if f["nq_seed"] < 0.5:
        return "kink_disruption"
    if f["nq_seed"] < 1.25:
        return "saturated_kink"
    return "quiescent"


# =====================================================
# data
# =====================================================

def collect(d):
    runs_dir = os.path.join(d, "runs")
    rows = []
    for name in sorted(os.listdir(runs_dir)):
        if not name.endswith(".npz") or ".part" in name:
            continue
        h, meta = FE.load_npz(os.path.join(runs_dir, name))
        r = analyse(h, meta, with_ml=False)
        rows.append({"id": meta["id"], "kind": meta["kind"], "twin": meta["twin"],
                     "stratum": meta["stratum"], "status": meta["status"], "label": r["label"],
                     "confidence": r["confidence"], "features": r["features"],
                     "start": FE.start_features(meta["setup"], meta["live"], meta["derived"])})
    return rows


def dataset_hash(rows):
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r["id"]):
        h.update(f"{r['id']}:{r['label']};".encode())
    return h.hexdigest()[:12]


# =====================================================
# fitting and scoring
# =====================================================

def make_model(**params):
    return HistGradientBoostingClassifier(max_iter=MAX_ITER, random_state=SEED, **params)


def tune(X, y):
    """5-fold CV over GRID on the training part; returns (best params, table)."""
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    classes = np.unique(y)
    table = []
    for values in itertools.product(*GRID.values()):
        params = dict(zip(GRID, values))
        losses, accs = [], []
        for tr, va in cv.split(X, y):
            m = make_model(**params).fit(X[tr], y[tr])
            p = m.predict_proba(X[va])
            losses.append(log_loss(y[va], p, labels=m.classes_))
            accs.append(accuracy_score(y[va], m.classes_[p.argmax(1)]))
        table.append({**params, "cv_log_loss": float(np.mean(losses)), "cv_log_loss_std": float(np.std(losses)),
                      "cv_accuracy": float(np.mean(accs))})
    best = min(table, key=lambda r: r["cv_log_loss"])
    del classes
    return {k: best[k] for k in GRID}, table


def score(y, pred, proba=None, classes=None):
    out = {"n": int(len(y)), "accuracy": float(accuracy_score(y, pred)),
           "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
           "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0))}
    if proba is not None:
        out["log_loss"] = float(log_loss(y, proba, labels=classes))
        conf = proba.max(axis=1)
        out["ece"] = M.expected_calibration_error(conf, pred == y)
    labels = sorted(set(y) | set(pred))
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    out["per_class"] = {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                            "support": int(s[i])} for i, c in enumerate(labels)}
    out["confusion_labels"] = labels
    out["confusion"] = confusion_matrix(y, pred, labels=labels).tolist()
    return out


def evaluate(kind, rows_tr, rows_te, inputs, key):
    """Tune on train, score on test; returns (params, metrics, fitted test-model, X_te, y_te)."""
    X_tr, y_tr = M.matrix([r[key] for r in rows_tr], inputs), np.array([r["label"] for r in rows_tr])
    X_te, y_te = M.matrix([r[key] for r in rows_te], inputs), np.array([r["label"] for r in rows_te])
    t0 = time.time()
    params, table = tune(X_tr, y_tr)
    m = make_model(**params).fit(X_tr, y_tr)
    proba = m.predict_proba(X_te)
    pred = m.classes_[proba.argmax(1)]
    metrics = {"params": params, "tuning": table, "tuning_seconds": round(time.time() - t0, 1),
               "test": score(y_te, pred, proba, m.classes_)}
    broad = np.array([r["stratum"] == "broad" for r in rows_te])
    if broad.any():
        metrics["test_broad"] = score(y_te[broad], pred[broad], proba[broad], m.classes_)
    common = Counter(y_tr).most_common(1)[0][0]
    metrics["baseline_majority"] = score(y_te, np.full(len(y_te), common))
    if kind == "outcome":
        metrics["baseline_nq_rule"] = score(y_te, np.array([nq_rule(r["start"]) for r in rows_te]))
    imp = permutation_importance(m, X_te, y_te, n_repeats=10, random_state=SEED, scoring="accuracy")
    order = np.argsort(-imp.importances_mean)
    metrics["permutation_importance"] = [
        {"input": inputs[i], "mean": float(imp.importances_mean[i]), "std": float(imp.importances_std[i])}
        for i in order[:12]]
    return params, metrics, m, proba, pred, y_te


# =====================================================
# figures
# =====================================================

def plot_confusion(ax, met, title):
    labels = met["confusion_labels"]
    C = np.array(met["confusion"], dtype=float)
    R = C / np.maximum(C.sum(axis=1, keepdims=True), 1)
    ax.imshow(R, cmap="Blues", vmin=0, vmax=1)
    short = [NAMES.get(c, c).replace("Kink -> disruption", "Disruption").replace("Saturated helical kink",
             "Saturated kink") for c in labels]
    ax.set_xticks(range(len(labels)), short, rotation=40, ha="right", fontsize=7)
    ax.set_yticks(range(len(labels)), short, fontsize=7)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if C[i, j]:
                ax.text(j, i, int(C[i, j]), ha="center", va="center", fontsize=7,
                        color="white" if R[i, j] > 0.5 else "black")
    ax.set_xlabel("predicted", fontsize=8)
    ax.set_ylabel("rule label (truth)", fontsize=8)
    ax.set_title(f"{title}\naccuracy {met['accuracy']:.2f}, balanced {met['balanced_accuracy']:.2f}", fontsize=9)


def plot_calibration(ax, results):
    ax.plot([0, 1], [0, 1], ":", color="0.5", label="perfect")
    for name, (proba, pred, y) in results.items():
        conf = proba.max(axis=1)
        edges = np.linspace(0, 1, 11)
        xs, ys, ns = [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            s = (conf > lo) & (conf <= hi)
            if s.sum() >= 5:
                xs.append(conf[s].mean())
                ys.append((pred[s] == y[s]).mean())
                ns.append(s.sum())
        ax.plot(xs, ys, "o-", label=f"{name} (ECE {M.expected_calibration_error(conf, pred == y):.3f})")
    ax.set_xlabel("model's confidence in its top answer", fontsize=8)
    ax.set_ylabel("fraction actually right", fontsize=8)
    ax.set_title("Calibration on the test runs (bins with >= 5 runs)", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)


CLASS_COLOURS = {"kink_disruption": "#d1495b", "saturated_kink": "#edae49", "quiescent": "#66a182",
                 "gravity_sag": "#8d96a3", "radiative_collapse": "#7b4fa6", "resistive_diffusion": "#00798c",
                 "sausage": "#e07a5f", "kink_growing": "#f4d35e"}


def plot_outcome_map(path, bundle, rows):
    """
    Predicted outcome over B_z x current, everything else at the GUI
    defaults, with the Kruskal-Shafranov lines n q = 0.5 and 1 of the seeded
    helix, and the real sweep runs that are close to this slice.
    """
    setup, live = SetupParams().__dict__.copy(), LiveParams().__dict__.copy()
    bz = np.linspace(0.0, 1.5, 121)
    cur = np.linspace(0.4, 2.8, 97)
    classes = list(bundle["classes"])
    pts = []
    for c in cur:
        for b in bz:
            pts.append(FE.start_features({**setup, "axial_field": b}, {**live, "current": c}))
    P = bundle["model"].predict_proba(M.matrix(pts, bundle["inputs"]))
    top = P.argmax(1).reshape(len(cur), len(bz))
    conf = P.max(1).reshape(len(cur), len(bz))
    rgb = np.array([matplotlib.colors.to_rgb(CLASS_COLOURS.get(c, "#cccccc")) for c in classes])
    img = rgb[top] * (0.45 + 0.55 * conf[..., None]) + (1 - (0.45 + 0.55 * conf[..., None]))

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.imshow(img, origin="lower", aspect="auto", extent=[bz[0], bz[-1], cur[0], cur[-1]])
    f0 = FE.start_features(setup, live)
    n = f0["seed_n"]
    q_per_bz = f0["q_a"] / max(setup["axial_field"], 1e-12) if setup["axial_field"] else \
        FE.start_features({**setup, "axial_field": 1.0}, live)["q_a"]
    for nq, ls in ((0.5, "--"), (1.0, "-")):
        b_line = nq / (n * q_per_bz)
        if b_line <= 1.5:
            ax.axvline(b_line, color="k", ls=ls, lw=1.2)
            ax.text(b_line + 0.01, 2.72, f"n q = {nq:g}", fontsize=8, va="top")
    # sweep runs near this slice: same column length (+-0.25), no gravity, weak cooling
    near = [r for r in rows if r["kind"] == "base" and abs(r["start"]["length"] - setup["length"]) < 0.25
            and r["start"]["gravity"] == 0 and r["start"]["cooling"] < 0.05]
    for c in classes:
        sel = [r for r in near if r["label"] == c]
        if sel:
            ax.scatter([r["start"]["axial_field"] for r in sel], [r["start"]["current"] for r in sel],
                       s=22, color=CLASS_COLOURS.get(c, "#ccc"), edgecolor="k", lw=0.6, label=NAMES.get(c, c))
    handles = [matplotlib.patches.Patch(color=CLASS_COLOURS.get(c, "#ccc"), label=NAMES.get(c, c)) for c in classes]
    leg1 = ax.legend(handles=handles, fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1.0),
                     title="predicted (paler = less sure)", title_fontsize=8)
    ax.add_artist(leg1)
    ax.legend(fontsize=8, loc="lower left", bbox_to_anchor=(1.02, 0.0),
              title=f"real sweep runs\n(L = {setup['length']:g} +- 0.25,\nno gravity or cooling)", title_fontsize=8)
    ax.set_xlabel("axial guide field B_z / B_theta(a)")
    ax.set_ylabel("drive current I / I_Bennett")
    ax.set_title(f"Outcome predictor (b): most likely outcome\n"
                 f"L = {setup['length']:g}, rise {live['rise_time']:g}, eta = nu = {live['resistivity']:g}, "
                 f"no cooling, no gravity (seeded helix n = {int(n)})", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# =====================================================
# model card
# =====================================================

def pct(x):
    return f"{100 * x:.1f} %"


def card(info, met_a, met_b, twins, dropped, disagreements):
    L = [f"# Model card: run classifier (a) and outcome predictor (b), v{VERSION}", "",
         f"Trained {info['created']} on `{info['dataset']}`: {info['n_runs']} finished 32^3 runs "
         f"(dataset hash `{info['hash']}`), scikit-learn {info['sklearn']}. Generated by `tools/train.py`; "
         f"see docs/05.2 for the plain-language version.", "",
         "## What they are", "",
         f"- **(a) Run classifier**: input = the {len(M.RUN_INPUTS)} features of a *finished* run (zpinch/analysis/features.py); "
         "output = probability of each outcome class.",
         "- **(b) Outcome predictor**: input = only what is known *before* pressing Start (the 8 swept "
         f"settings and the stability numbers computed from them, e.g. n q: {len(M.PRESTART_INPUTS)} inputs); "
         "output = probability of each outcome.",
         "- Both: gradient-boosted trees (`HistGradientBoostingClassifier`), labels = the physics rules "
         "(zpinch/analysis/rules.py).", "",
         f"Classes learned: {', '.join(info['classes'])}."
         + (f" Left out (fewer than {MIN_CLASS} runs): {dropped}." if dropped else ""), "",
         "## How they were tested", "",
         f"{pct(TEST_FRACTION)} of the runs ({met_b['test']['n']}) were locked away before any tuning. "
         "Settings were chosen by 5-fold cross-validation on the rest (best log loss), then each model was "
         "scored once on the locked-away runs.", "",
         "| | accuracy | balanced accuracy | macro F1 | log loss | calibration error (ECE) |",
         "|---|---|---|---|---|---|"]
    for name, m in (("(a) run classifier", met_a["test"]), ("(b) outcome predictor", met_b["test"]),
                    ("(b) baseline: n q rule only", met_b["baseline_nq_rule"]),
                    ("baseline: always the commonest class", met_b["baseline_majority"])):
        L.append(f"| {name} | {pct(m['accuracy'])} | {pct(m['balanced_accuracy'])} | {m['macro_f1']:.3f} | "
                 f"{m.get('log_loss', float('nan')):.3f} | {m.get('ece', float('nan')):.3f} |")
    if "test_broad" in met_b:
        L += ["", f"On the broad stratum only (a uniform sample of the box, n = {met_b['test_broad']['n']}): "
              f"(a) {pct(met_a['test_broad']['accuracy'])}, (b) {pct(met_b['test_broad']['accuracy'])}."]
    for title, m in (("(a) run classifier", met_a), ("(b) outcome predictor", met_b)):
        L += ["", f"### {title}: per class (test runs)", "", "| class | precision | recall | runs |", "|---|---|---|---|"]
        for c, v in m["test"]["per_class"].items():
            L.append(f"| {c} | {v['precision']:.2f} | {v['recall']:.2f} | {v['support']} |")
        L += ["", f"Chosen settings: {m['params']}. What it relies on most (accuracy lost when the input is "
              "shuffled):", ""]
        L += [f"- `{p['input']}`: {p['mean']:.3f} ± {p['std']:.3f}" for p in m["permutation_importance"][:6]]
    L += ["", "## Resolution check (a)", "",
          f"Applied to the 48^3 twins (never seen in training): agrees with their rule label in "
          f"{twins['agree']} of {twins['n']}.", "",
          "## (a) vs the rules on the test runs", "",
          f"{len(disagreements)} test runs where the classifier's top answer differs from the rule label "
          "(listed in `disagreements.md` for review)."]
    L += ["", "## Limits", "",
          "- The labels come from rules, not from experiments. (a) mostly learns the rules back; "
          "its use is the probabilities and the disagreements.",
          "- (b) is only meaningful inside the swept box (tools/sweep.py) at 32^3 with the default seed "
          "perturbation, pinch radius and background density. The GUI warns outside it.",
          "- Thin classes (radiative collapse, resistive diffusion) have few test runs, so their per-class "
          "numbers are uncertain by ±10-20 %.",
          "- The random seed of a run is not an input, so runs with the same settings but different seeds "
          "can differ; this caps (b)'s possible accuracy."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="sweep directory (tools/sweep.py)")
    ap.add_argument("--out", default=M.MODEL_DIR)
    args = ap.parse_args()
    import joblib
    import sklearn
    from threadpoolctl import threadpool_limits
    # a few threads only: the sweep may be using every core (oversubscribed
    # OpenMP made one prediction take minutes, 2026-10-20)
    threadpool_limits(limits=int(os.environ.get("TRAIN_THREADS", "2")), user_api="openmp")

    t0 = time.time()
    rows_all = collect(args.dir)
    rows = [r for r in rows_all if r["kind"] == "base" and r["status"] == "ok"]
    counts = Counter(r["label"] for r in rows)
    keep = sorted(c for c, n in counts.items() if n >= MIN_CLASS)
    dropped = {c: n for c, n in counts.items() if n < MIN_CLASS}
    rows = [r for r in rows if r["label"] in keep]
    print(f"{len(rows_all)} runs analysed in {time.time() - t0:.1f} s; training on {len(rows)} "
          f"({dict(Counter(r['label'] for r in rows))})")

    y = np.array([r["label"] for r in rows])
    idx_tr, idx_te = train_test_split(np.arange(len(rows)), test_size=TEST_FRACTION, stratify=y,
                                      random_state=SEED)
    tr, te = [rows[i] for i in idx_tr], [rows[i] for i in idx_te]

    print("tuning + testing (a) run classifier ...", flush=True)
    pa, met_a, ma, proba_a, pred_a, y_te = evaluate("run", tr, te, M.RUN_INPUTS, "features")
    print(f"  test accuracy {met_a['test']['accuracy']:.3f}  ({met_a['tuning_seconds']} s)")
    print("tuning + testing (b) outcome predictor ...", flush=True)
    pb, met_b, mb, proba_b, pred_b, _ = evaluate("outcome", tr, te, M.PRESTART_INPUTS, "start")
    print(f"  test accuracy {met_b['test']['accuracy']:.3f}  (n q rule {met_b['baseline_nq_rule']['accuracy']:.3f}, "
          f"majority {met_b['baseline_majority']['accuracy']:.3f})")

    disagreements = [(r, pred_a[i], proba_a[i].max()) for i, r in enumerate(te) if pred_a[i] != r["label"]]

    # refit on everything and save
    os.makedirs(args.out, exist_ok=True)
    info = {"version": VERSION, "created": datetime.now().isoformat(timespec="seconds"),
            "dataset": os.path.relpath(os.path.abspath(args.dir), V2), "n_runs": len(rows),
            "hash": dataset_hash(rows), "sklearn": sklearn.__version__, "classes": keep}
    bundles = {}
    for kind, params, inputs, key in (("run", pa, M.RUN_INPUTS, "features"),
                                      ("outcome", pb, M.PRESTART_INPUTS, "start")):
        X = M.matrix([r[key] for r in rows], inputs)
        model = make_model(**params).fit(X, y)
        bundles[kind] = {"model": model, "classes": list(model.classes_), "inputs": inputs,
                         "version": f"{kind} v{VERSION} ({info['n_runs']} runs, {info['hash']})",
                         "info": info, "coverage": M.coverage_space([r["start"] for r in rows])}
        joblib.dump(bundles[kind], os.path.join(args.out, M.FILES[kind]), compress=3)

    twin_rows = [r for r in rows_all if r["kind"] == "res48" and r["label"] in keep]
    twins = {"n": len(twin_rows), "agree": 0}
    if twin_rows:
        p = bundles["run"]["model"].predict(M.matrix([r["features"] for r in twin_rows], M.RUN_INPUTS))
        twins["agree"] = int(sum(a == r["label"] for a, r in zip(p, twin_rows)))

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    plot_confusion(axes[0], met_a["test"], "(a) run classifier, test runs")
    plot_confusion(axes[1], met_b["test"], "(b) outcome predictor, test runs")
    plot_confusion(axes[2], met_b["baseline_nq_rule"], "baseline: n q rule only, test runs")
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "confusion.png"), dpi=120)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 5))
    plot_calibration(ax, {"(a) run classifier": (proba_a, pred_a, y_te),
                          "(b) outcome predictor": (proba_b, pred_b, y_te)})
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "calibration.png"), dpi=120)
    plt.close(fig)
    plot_outcome_map(os.path.join(args.out, "outcome_map.png"), bundles["outcome"], rows_all)

    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump({"info": info, "run_classifier": met_a, "outcome_predictor": met_b, "twins": twins,
                   "dropped_classes": dropped}, f, indent=1)
    with open(os.path.join(args.out, "MODEL_CARD.md"), "w") as f:
        f.write(card(info, met_a, met_b, twins, dropped, disagreements))
    with open(os.path.join(args.out, "disagreements.md"), "w") as f:
        f.write("# (a) run classifier vs the rules, test runs\n\n| run | rule label | rule confidence | "
                "classifier says | classifier confidence |\n|---|---|---|---|---|\n")
        for r, p, c in sorted(disagreements, key=lambda x: x[0]["id"]):
            f.write(f"| {r['id']} | {r['label']} | {r['confidence']} | {p} | {c:.2f} |\n")
    print(f"saved to {args.out} in {time.time() - t0:.0f} s: run_classifier.joblib, outcome_predictor.joblib, "
          "MODEL_CARD.md, metrics.json, confusion.png, calibration.png, outcome_map.png, disagreements.md")


if __name__ == "__main__":
    main()
