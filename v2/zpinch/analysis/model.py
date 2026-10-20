"""
Phase 3 models (plan section 5): learned versions of the outcome labels.

    (a) run classifier     finished run's features      -> outcome probabilities
    (b) outcome predictor  settings before pressing Start -> outcome probabilities

Both are gradient-boosted decision trees (scikit-learn's
HistGradientBoostingClassifier): many small yes/no trees, each correcting
the mistakes of the ones before. They suit a table of ~1000 rows of
physical numbers, need no scaling, and handle missing values.

The labels they learn are the physics rules' labels (rules.py). So (a) is
mostly a check on the rules: its value is the probabilities, which say how
clear-cut a run is, and the runs where it disagrees with the rules. (b) is
the new capability: an instant forecast, trusted only inside the region the
sweep covered.

Models are trained by tools/train.py and saved in v2/models/ together with
what they were trained on (run count, dataset hash, input ranges).
"""

import math
import os

import numpy as np

from . import features as FE

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "models")
FILES = {"run": "run_classifier.joblib", "outcome": "outcome_predictor.joblib"}

# (b) sees only what is known before the run. pinch_radius, background_density
# and t_alfven are constant in the sweep, so they carry no information there.
PRESTART_INPUTS = ["current", "rise_time", "axial_field", "resistivity", "viscosity", "cooling",
                   "gravity", "length", "q_a", "nq_seed", "seed_n", "kadomtsev_margin",
                   "t_resistive", "t_cooling", "lundquist"]
# (a) sees every feature of the finished run.
RUN_INPUTS = list(FE.FEATURE_NAMES)

# The 8 swept parameters and how "distance" between two settings is
# measured for the out-of-range check: log scale for the ones swept
# log-uniformly (tools/sweep.py), linear for the rest; cooling and gravity
# are often exactly 0, so they get log1p / linear.
SWEPT = {"current": "lin", "rise_time": "log", "axial_field": "lin", "resistivity": "log",
         "viscosity": "log", "cooling": "log1p", "gravity": "lin", "length": "lin"}
# Settings the sweep never varied: the models know nothing about other values.
FIXED = {"resolution": "Very fast (32 x 32 x 48)", "pinch_radius": 0.12, "background_density": 0.05,
         "perturbation": "Random + m=0 + m=1", "perturbation_amp": 0.02, "spitzer": False, "solver": "HLLD"}
# "Sparse region": the nearest training run is farther away than 95 % of
# training runs are from their own nearest neighbour. (A fixed radius does
# not work in 8 dimensions: a ball of radius 0.15 holds ~1e-6 of the box.)
SPARSE_PERCENTILE = 95
EDGE_SLACK = 0.02          # fraction of a parameter's sampled range allowed beyond it
INF_VALUE = 1e6            # stands in for inf (no cooling: t_cooling = inf)

_cache = {}


def matrix(rows, names):
    """List of feature dicts -> float array, inf replaced by INF_VALUE (nan stays: trees handle it)."""
    X = np.array([[float(r[n]) for n in names] for r in rows], dtype=float)
    X[np.isinf(X)] = INF_VALUE
    return X


def _warp(name, x):
    kind = SWEPT[name]
    x = np.asarray(x, dtype=float)
    if kind == "log":
        return np.log(np.maximum(x, 1e-12))
    if kind == "log1p":
        return np.log1p(10.0 * x)
    return x


def coverage_space(rows):
    """Training points in the warped, range-normalised space of SWEPT."""
    W = np.column_stack([_warp(n, [r[n] for r in rows]) for n in SWEPT])
    lo, hi = W.min(axis=0), W.max(axis=0)
    P = (W - lo) / np.where(hi > lo, hi - lo, 1.0)
    nn = np.empty(len(P))
    for i in range(len(P)):
        d = np.sqrt(np.sum((P - P[i]) ** 2, axis=1))
        d[i] = np.inf
        nn[i] = d.min()
    return {"lo": lo, "hi": hi, "points": P, "nn_limit": float(np.percentile(nn, SPARSE_PERCENTILE)),
            "raw_min": {n: float(min(r[n] for r in rows)) for n in SWEPT},
            "raw_max": {n: float(max(r[n] for r in rows)) for n in SWEPT}}


def coverage(bundle, f):
    """Is this setting inside what the sweep covered? Out-of-range names + nearest-run distance."""
    cov = bundle["coverage"]
    # random samples never reach the edge of the swept box exactly (B_z = 1.5,
    # L = 1.0 of the "Stable screw pinch" preset), so allow EDGE_SLACK past them
    # (measured on the scale each parameter was swept on: log for resistivity, ...)
    out = []
    for n in SWEPT:
        lo, hi = _warp(n, cov["raw_min"][n]), _warp(n, cov["raw_max"][n])
        pad = EDGE_SLACK * (hi - lo) + 1e-9
        if not lo - pad <= _warp(n, f[n]) <= hi + pad:
            out.append(n)
    w = np.array([_warp(n, f[n]) for n in SWEPT])
    span = np.where(cov["hi"] > cov["lo"], cov["hi"] - cov["lo"], 1.0)
    d = np.sqrt(np.sum(((w - cov["lo"]) / span - cov["points"]) ** 2, axis=1))
    return {"out_of_range": out, "nearest": float(d.min()), "nn_limit": cov["nn_limit"],
            "sparse": bool(d.min() > cov["nn_limit"])}


def load(kind):
    """The saved bundle for 'run' or 'outcome', or None if it has not been trained."""
    if kind not in _cache:
        path = os.path.join(MODEL_DIR, FILES[kind])
        if not os.path.exists(path):
            _cache[kind] = None
        else:
            import joblib
            _cache[kind] = joblib.load(path)
    return _cache[kind]


def _probs(bundle, x):
    # One row needs no parallelism, and scikit-learn's OpenMP threads would
    # otherwise wait for cores the physics is using (measured: minutes per
    # call while the sweep ran 12 jobs)
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1, user_api="openmp"):
        p = bundle["model"].predict_proba(x)[0]
    order = np.argsort(-p)
    return [(str(bundle["classes"][i]), float(p[i])) for i in order]


def predict_outcome(setup, live):
    """
    (b) Forecast before running. Returns None without a trained model, else
        probs      [(class, probability)], most likely first
        coverage   out_of_range / fixed_changed parameter names, sparse flag
        trusted    False when outside the sweep or in a sparse region
    """
    b = load("outcome")
    if b is None:
        return None
    f = FE.start_features(setup, live)
    cov = coverage(b, f)
    both = {**setup, **live}
    cov["fixed_changed"] = [k for k, v in FIXED.items() if k in both and both[k] != v]
    return {"probs": _probs(b, matrix([f], b["inputs"])), "coverage": cov,
            "trusted": not (cov["out_of_range"] or cov["fixed_changed"] or cov["sparse"]),
            "version": b["version"]}


def classify_run(features):
    """(a) Probabilities for a finished run's features, or None without a model."""
    b = load("run")
    if b is None:
        return None
    return {"probs": _probs(b, matrix([features], b["inputs"])), "version": b["version"]}


def format_prediction(pred, names=None, top=3):
    """'saturated kink 78 % · kink disruption 19 %' (+ a coverage warning)."""
    if pred is None:
        return "no outcome model trained (tools/train.py)"
    names = names or {}
    parts = [f"{names.get(c, c.replace('_', ' '))} {100 * p:.0f} %" for c, p in pred["probs"][:top]
             if p >= 0.03 or c == pred["probs"][0][0]]
    s = " · ".join(parts)
    cov = pred.get("coverage")         # only (b) has one
    if not cov:
        pass
    elif cov.get("fixed_changed"):
        s += "  [the sweep kept " + ", ".join(cov["fixed_changed"]) + " at the default: treat as a rough guess]"
    elif cov["out_of_range"]:
        s += "  [outside the training sweep: " + ", ".join(cov["out_of_range"]) + "]"
    elif cov["sparse"]:
        s += "  [few training runs near these settings: less certain]"
    return s


def expected_calibration_error(conf, correct, bins=10):
    """Average |confidence - accuracy| over confidence bins, weighted by bin size."""
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (conf > lo) & (conf <= hi)
        if s.any():
            ece += s.mean() * abs(conf[s].mean() - correct[s].mean())
    return float(ece)


def is_finite_number(x):
    return isinstance(x, (int, float)) and math.isfinite(x)
