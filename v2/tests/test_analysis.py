"""
v3 phase 1: features, rules and explanations (zpinch/analysis/).

Synthetic histories check that each rule fires on its own signature and
that the class priority and borderline flags work. A short live run checks
the GUI/headless path. If the overnight sweep is present, hand-checked runs
from every class must keep their labels (the plan's "done" criterion for
phase 1); those tests are skipped on a machine without the dataset.
"""

import json
import os

os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")

import numpy as np
import pytest

from zpinch.analysis import analyse, analyse_npz, analyse_sim, format_report
from zpinch.analysis import features as FE
from zpinch.analysis import rules as RU
from zpinch.params import SetupParams, LiveParams
from zpinch.pinch import HISTORY_KEYS, ZPinch

A = 0.12
T = np.arange(0.0, 3.0 + 1e-9, FE.DT_SAVE)


def make_run(live=None, **series):
    """A quiet equilibrium history; keyword arrays replace single keys."""
    n = T.size
    h = {k: np.zeros(n) for k in HISTORY_KEYS}
    h["t"] = T.copy()
    h.update(total=np.ones(n), magnetic=np.full(n, 0.5), thermal=np.full(n, 0.5),
             m1=np.full(n, 0.02), m0=np.full(n, 0.014), shift=np.full(n, 1e-3),
             radius=np.full(n, A), core_density=np.full(n, 0.65), core_temperature=np.ones(n),
             peak_density=np.ones(n), peak_temperature=np.ones(n),
             m1_n1=np.full(n, 0.005), m1_n2=np.full(n, 0.02), m1_n3=np.full(n, 0.005))
    for k, v in series.items():
        h[k] = np.asarray(v, dtype=float)
    lv = {**LiveParams().__dict__, **(live or {})}
    meta = {"id": "synthetic", "setup": SetupParams().__dict__, "live": lv, "status": "ok",
            "derived": {"Lz": 1.5, "q_a": 0.0, "kadomtsev_margin": 0.0, "lundquist": 283.0,
                        "beta_a": 1.0, "t_alfven": 0.17}}
    return h, meta


def label(h, meta):
    f = FE.compute(h, meta)
    return RU.classify(h, f, meta)


def grow(rate, top, t0=0.0, seed=0.02):
    return np.minimum(seed * np.exp(rate * np.maximum(T - t0, 0.0)), top)


def test_fit_growth_recovers_exact_rate():
    fit = FE.fit_growth(T, grow(4.0, 0.5))
    assert fit is not None
    assert fit["gamma"] == pytest.approx(4.0, rel=1e-9)
    assert fit["r2"] == pytest.approx(1.0, abs=1e-12)


def test_fit_growth_none_without_growth():
    assert FE.fit_growth(T, np.full(T.size, 0.02)) is None
    assert FE.fit_growth(T, grow(4.0, 0.05)) is None        # only 2.5x: below min_ratio


def test_quiescent():
    r = label(*make_run())
    assert r["label"] == "quiescent" and r["confidence"] == "high"


def test_saturated_kink():
    r = label(*make_run(m1=grow(4.0, 0.4)))
    assert r["label"] == "saturated_kink"
    assert r["evidence"]["saturated_kink"]["m1_sat"] == pytest.approx(0.4)
    assert [p["name"] for p in r["phases"]] == ["kink_growth", "saturated_kink"]


def test_kink_disruption_needs_the_column_torn():
    m1 = grow(4.0, 1.0)
    torn = A * np.where(T > 1.2, 4.5, 1.0)
    assert label(*make_run(m1=m1, radius=torn))["label"] == "kink_disruption"
    # same kink, but the column stays together: saturated
    assert label(*make_run(m1=m1))["label"] == "saturated_kink"
    # spreading long after the kink went nonlinear is not a disruption
    late = A * np.where(T > 2.9, 4.5, 1.0)
    assert label(*make_run(m1=m1, radius=late))["label"] == "saturated_kink"


def test_kink_still_growing_when_analysed_early():
    h, meta = make_run(m1=grow(4.0, 0.4))
    cut = T <= 0.7                                      # m1 = 0.33, still exponential
    early = {k: v[cut] for k, v in h.items()}
    r = label(early, meta)
    assert r["label"] == "kink_growing"
    assert "saturated_kink" not in r["evidence"]


def test_gravity_sag_only_with_gravity():
    shift = grow(4.0, 1.0, seed=1e-3)
    assert label(*make_run(live={"gravity": 1.0}, shift=shift))["label"] == "gravity_sag"
    assert label(*make_run(shift=shift))["label"] == "quiescent"


def test_sag_beats_a_small_saturated_kink():
    r = label(*make_run(live={"gravity": 1.0}, shift=grow(4.0, 1.0, seed=1e-3), m1=grow(4.0, 0.2)))
    assert r["label"] == "gravity_sag" and "saturated_kink" in r["secondary"]


def test_radiative_collapse_needs_cold_and_dense():
    Tc = np.maximum(1.0 - 0.4 * T, 0.1)
    rho = 0.65 * (1.0 + T)
    r = label(*make_run(live={"cooling": 1.0}, core_temperature=Tc, core_density=rho))
    assert r["label"] == "radiative_collapse"
    # cooling while expanding (density falls) is not a collapse
    r = label(*make_run(live={"cooling": 1.0}, core_temperature=Tc, core_density=0.65 / (1.0 + T)))
    assert r["label"] != "radiative_collapse"


def test_collapse_outranks_disruption():
    Tc = np.maximum(1.0 - 0.4 * T, 0.1)
    r = label(*make_run(live={"cooling": 1.0}, core_temperature=Tc, core_density=0.65 * (1.0 + T),
                        m1=grow(4.0, 1.0), radius=A * np.where(T > 1.2, 4.5, 1.0)))
    assert r["label"] == "radiative_collapse" and "kink_disruption" in r["secondary"]


def test_resistive_diffusion_needs_short_resistive_time():
    rho = 0.65 * np.exp(-0.4 * T)                     # falls to 0.30 of the start
    heat = 0.5 + 0.03 * T                             # +0.09 E0 of heat
    assert label(*make_run(live={"resistivity": 8e-3}, core_density=rho,
                           thermal=heat))["label"] == "resistive_diffusion"
    # same signature at low eta (a^2/eta = 48 >> run): numerical, not resistive
    assert label(*make_run(live={"resistivity": 3e-4}, core_density=rho,
                           thermal=heat))["label"] == "quiescent"


def test_sausage_must_be_the_largest_distortion():
    assert label(*make_run(m0=grow(4.0, 0.3, seed=0.014)))["label"] == "sausage"
    # late necking after a larger kink: only a phase
    m1 = np.where(T < 1.5, grow(4.0, 0.4), 0.05)
    m0 = np.where(T > 2.0, 0.2, 0.014)
    r = label(*make_run(m1=m1, m0=m0))
    assert r["label"] == "saturated_kink"
    assert "sausage" in [p["name"] for p in r["phases"]]


def test_compression_is_a_phase_not_a_class():
    rho = 0.65 * np.where((T > 0.2) & (T < 0.8), 1.6, 1.0)
    r = label(*make_run(live={"current": 2.5, "rise_time": 0.1}, core_density=rho))
    assert r["label"] == "quiescent" and "compression" in r["secondary"]


def test_borderline_is_low_confidence():
    r = label(*make_run(m1=grow(4.0, 0.105)))
    assert r["label"] == "saturated_kink" and r["confidence"] == "low"
    assert any("m1_peak" in note for note in r["borderline"])


def test_report_is_complete_and_json_safe():
    r = analyse(*make_run(m1=grow(4.0, 0.4)))
    text = format_report(r)
    for part in ("Outcome: Saturated helical kink", "Timeline", "Causes in detail",
                 "Stability criteria", "Energy budget"):
        assert part in text
    json.dumps(r)
    assert set(r["features"]) == set(FE.FEATURE_NAMES)


def test_live_run_analyses():
    sim = ZPinch(SetupParams(n_tracers=0))
    while sim.t < 0.2:
        sim.step()
    r = analyse_sim(sim)
    assert r["label"] == "quiescent"         # far too early for the kink
    assert r["features"]["t_final"] == pytest.approx(sim.history["t"][-1])


# hand-checked runs from the 2026-10-19 sweep (galleries reviewed by eye,
# 2026-10-20): one or more per class that occurs in the data. No run in
# the sweep is sausage-dominated, so that class is covered synthetically.
SWEEP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "dataset", "sweep-2026-10-19", "runs")
HAND_PICKED = {
    "r00843": "kink_disruption",      # B_z = 0: kink 0.7 a, column torn by t = 1.3
    "r00087": "kink_disruption",      # I = 2.1, B_z = 0
    "r00071": "saturated_kink",       # n q = 0.90
    "r00648": "saturated_kink",       # kink 0.34 a, survives as a helix
    "r00047": "gravity_sag",          # g = 1.9, B_z = 1.4: shift 1.5 a, kink < 0.1
    "r00863": "gravity_sag",          # g = 1.55, small kink rides on the sag
    "r00171": "radiative_collapse",   # C = 2: core to T = 0.05, 4.8x denser
    "r00005": "radiative_collapse",   # compression first, then collapse to 14x
    "r00999": "resistive_diffusion",  # eta = 7.6e-3, quiet, core to 0.4x
    "r00617": "resistive_diffusion",
    "r00021": "quiescent",            # n q = 1.5, I = 2.2 drive
    "r00105": "quiescent",            # n q = 1.6
}


@pytest.mark.skipif(not os.path.isdir(SWEEP), reason="overnight sweep dataset not present")
@pytest.mark.parametrize("run_id,expected", sorted(HAND_PICKED.items()))
def test_hand_picked_sweep_runs(run_id, expected):
    assert analyse_npz(os.path.join(SWEEP, f"{run_id}.npz"))["label"] == expected
