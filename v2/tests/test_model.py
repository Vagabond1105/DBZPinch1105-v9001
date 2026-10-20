"""
v3 phase 3: the models' plumbing (zpinch/analysis/model.py).

What the models *learned* is measured by tools/train.py (MODEL_CARD.md);
these tests check what must hold regardless: the before-the-run numbers
match the simulation's, the coverage check flags settings outside the
sweep, and a trained bundle round-trips through predict_outcome.
"""

import os

import numpy as np
import pytest

pytest.importorskip("sklearn")

from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

from zpinch.analysis import features as FE  # noqa: E402
from zpinch.analysis import model as M  # noqa: E402
from zpinch.analysis.features import derived_numbers  # noqa: E402
from zpinch.params import SetupParams, LiveParams  # noqa: E402
from zpinch.pinch import ZPinch  # noqa: E402


def _defaults():
    return SetupParams().__dict__.copy(), LiveParams().__dict__.copy()


@pytest.mark.parametrize("over", [{}, {"axial_field": 0.9, "length": 2.3}, {"resolution": "Fast (48 x 48 x 72)"}])
def test_prestart_numbers_match_the_simulation(over):
    setup, live = _defaults()
    setup.update(over, n_tracers=0)
    sim = ZPinch(SetupParams(**setup), LiveParams(**live))
    a, b = derived_numbers(sim), FE.derived_from_params(setup, live)
    for k, v in a.items():
        assert b[k] == pytest.approx(v, rel=1e-12), k


def _toy_bundle():
    """A model trained on synthetic 'runs' spread over the swept box."""
    rng = np.random.default_rng(0)
    setup, live = _defaults()
    rows, labels = [], []
    for _ in range(300):
        s = {**setup, "axial_field": 0.0 if rng.random() < 0.3 else rng.uniform(0, 1.5),
             "length": rng.uniform(1, 3)}
        lv = {**live, "current": rng.uniform(0.4, 2.8), "rise_time": float(np.exp(rng.uniform(np.log(0.05), 0))),
              "resistivity": float(np.exp(rng.uniform(np.log(1e-4), np.log(1e-2)))),
              "viscosity": float(np.exp(rng.uniform(np.log(1e-4), np.log(1e-2)))),
              "cooling": 0.0, "gravity": 0.0}
        f = FE.start_features(s, lv)
        rows.append(f)
        labels.append("kink_disruption" if f["nq_seed"] < 0.5 else
                      "saturated_kink" if f["nq_seed"] < 1.25 else "quiescent")
    m = HistGradientBoostingClassifier(max_iter=50, random_state=0).fit(
        M.matrix(rows, M.PRESTART_INPUTS), np.array(labels))
    return {"model": m, "classes": list(m.classes_), "inputs": M.PRESTART_INPUTS, "version": "toy",
            "coverage": M.coverage_space(rows)}


def test_predict_outcome_and_coverage(monkeypatch):
    b = _toy_bundle()
    monkeypatch.setitem(M._cache, "outcome", b)
    setup, live = _defaults()
    pure = M.predict_outcome(setup, live)                       # B_z = 0: n q = 0
    assert pure["probs"][0][0] == "kink_disruption"
    assert sum(p for _, p in pure["probs"]) == pytest.approx(1.0)
    assert pure["trusted"]
    stable = M.predict_outcome({**setup, "axial_field": 1.5, "length": 1.0}, live)
    assert stable["probs"][0][0] == "quiescent"

    far = M.predict_outcome(setup, {**live, "resistivity": 0.0})       # below the swept range
    assert "resistivity" in far["coverage"]["out_of_range"] and not far["trusted"]
    # a corner of the box, just inside every range: covered, but far from any run
    hi = b["coverage"]["raw_max"]
    corner = M.predict_outcome({**setup, "axial_field": 0.99 * hi["axial_field"], "length": 0.99 * hi["length"]},
                               {**live, "current": 0.99 * hi["current"], "rise_time": 0.99 * hi["rise_time"],
                                "resistivity": 0.99 * hi["resistivity"], "viscosity": 0.99 * hi["viscosity"]})
    assert corner["coverage"]["sparse"] and not corner["coverage"]["out_of_range"]
    fixed = M.predict_outcome({**setup, "pinch_radius": 0.18}, live)    # never varied in the sweep
    assert fixed["coverage"]["fixed_changed"] == ["pinch_radius"] and not fixed["trusted"]
    assert "rough guess" in M.format_prediction(fixed)


def test_no_model_means_none(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(M, "_cache", {})
    setup, live = _defaults()
    assert M.predict_outcome(setup, live) is None
    assert M.classify_run({}) is None
    assert "no outcome model" in M.format_prediction(None)


def test_ece_of_a_perfectly_calibrated_toy():
    conf = np.repeat([0.55, 0.95], 100)
    correct = np.r_[np.arange(100) < 55, np.arange(100) < 95]
    assert M.expected_calibration_error(conf, correct) == pytest.approx(0.0, abs=1e-12)


SAVED = os.path.join(M.MODEL_DIR, M.FILES["outcome"])


@pytest.mark.skipif(not os.path.exists(SAVED), reason="no trained model in v2/models/")
def test_saved_predictor_knows_the_presets(monkeypatch):
    monkeypatch.setattr(M, "_cache", {})
    from zpinch.params import PRESETS, apply_preset
    expect = {"Pure Z-pinch: kink -> disruption": "kink_disruption",
              "Stable screw pinch": "quiescent"}
    for name, label in expect.items():
        s, lv = SetupParams(), LiveParams()
        apply_preset(name, s, lv)
        assert M.predict_outcome(s.__dict__, lv.__dict__)["probs"][0][0] == label, name
