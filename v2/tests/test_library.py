"""
v3 phase 4: the curated write-up library (zpinch/analysis/writeup.py,
zpinch/analysis/library/*.md).

Every entry must parse, have the three sections, use only placeholders a
run of its class can fill, and be covered by library/stats.json. Selection
must pick the most specific entry whose box contains the run and never a
regime entry outside its box. If the overnight sweep is present, every
entry's example run must get the entry's class, select that entry, and
fill every number (the plan's "done" criterion for phase 4).
"""

import json
import math
import os

os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")

import numpy as np
import pytest

from zpinch.analysis import analyse, analyse_npz, format_report
from zpinch.analysis import features as FE
from zpinch.analysis import writeup as WU
from zpinch.analysis.rules import CLASSES

from .test_analysis import A, SWEEP, T, grow, make_run

ENTRIES = WU.load(include_unreviewed=True)


def synthetic(cls):
    """A synthetic run of each class (same signatures as test_analysis)."""
    if cls == "quiescent":
        return make_run()
    if cls == "saturated_kink":
        return make_run(m1=grow(4.0, 0.4))
    if cls == "kink_disruption":
        return make_run(m1=grow(4.0, 1.0), radius=A * np.where(T > 1.2, 4.5, 1.0))
    if cls == "kink_growing":
        h, meta = make_run(m1=grow(4.0, 0.4))
        cut = T <= 0.7
        return {k: v[cut] for k, v in h.items()}, meta
    if cls == "gravity_sag":
        return make_run(live={"gravity": 1.0}, shift=grow(4.0, 1.0, seed=1e-3), m1=grow(4.0, 0.2))
    if cls == "radiative_collapse":
        return make_run(live={"cooling": 1.0}, core_temperature=np.maximum(1.0 - 0.4 * T, 0.1),
                        core_density=0.65 * (1.0 + T))
    if cls == "resistive_diffusion":
        return make_run(live={"resistivity": 8e-3}, core_density=0.65 * np.exp(-0.4 * T),
                        thermal=0.5 + 0.03 * T)
    if cls == "sausage":
        return make_run(m0=grow(4.0, 0.3, seed=0.014))
    raise KeyError(cls)


def test_every_entry_is_complete():
    ids = [e["id"] for e in ENTRIES]
    assert len(ids) == len(set(ids))
    for e in ENTRIES:
        assert os.path.basename(e["path"]) == e["id"] + ".md"
        assert e["class"] in CLASSES, e["id"]
        assert e["reviewed"] in ("no", *WU.REVIEW_STATES), e["id"]
        assert set(e["sections"]) == set(WU.SECTIONS), e["id"]
        for box in (e["regime"], e["compare"]):
            for key, (lo, hi) in box.items():
                assert key in FE.FEATURE_NAMES and lo <= hi, (e["id"], key)


def test_each_class_has_exactly_one_general_entry():
    for cls in CLASSES:
        general = [e["id"] for e in ENTRIES if e["class"] == cls and not e["regime"]]
        assert len(general) == 1, (cls, general)


@pytest.mark.parametrize("cls", CLASSES)
def test_every_entry_fills_on_a_run_of_its_class(cls):
    h, meta = synthetic(cls)
    r = analyse(h, meta, with_ml=False)
    assert r["label"] == cls
    stats = WU.load_stats()
    for e in (e for e in ENTRIES if e["class"] == cls):
        vals = WU.values(r, meta, stats, e)
        assert WU.placeholders(e) <= set(vals), (e["id"], WU.placeholders(e) - set(vals))
        WU.fill(e, vals)                       # no format errors


def test_stats_cover_every_entry():
    stats = WU.load_stats()
    assert stats and set(stats["entries"]) == {e["id"] for e in ENTRIES}
    assert sum(stats["classes"].values()) == stats["runs"]


def _entry(eid, cls, regime="", priority=0):
    return WU.parse(f"---\nid: {eid}\nclass: {cls}\ntitle: t\nregime: {regime}\npriority: {priority}\n"
                    f"reviewed: data-checked\n---\n## What happened\na\n## Why\nb\n## Try next\nc\n")


def test_selection_is_most_specific_and_stays_inside_boxes():
    lib = [_entry("gen", "saturated_kink"), _entry("band", "saturated_kink", "nq_seed 0.5..1.0"),
           _entry("band-calm", "saturated_kink", "nq_seed 0.5..1.0; gravity 0..0.3"),
           _entry("other", "quiescent")]
    e, m = WU.select("saturated_kink", {"nq_seed": 0.8, "gravity": 0.0}, lib)
    assert e["id"] == "band-calm" and m["kind"] == "regime"
    e, m = WU.select("saturated_kink", {"nq_seed": 0.8, "gravity": 1.0}, lib)
    assert e["id"] == "band"
    # just outside every box: the general entry, naming the nearest regime entry
    e, m = WU.select("saturated_kink", {"nq_seed": 1.1, "gravity": 0.0}, lib)
    assert e["id"] == "gen" and m["kind"] == "general" and m["distance"] == pytest.approx(0.2)
    assert WU.select("sausage", {"nq_seed": 0.8}, lib) == (None, None)


def test_priority_breaks_ties():
    lib = [_entry("gen", "kink_disruption"), _entry("weak", "kink_disruption", "axial_field 0.001..inf"),
           _entry("driven", "kink_disruption", "current 1.5..inf", priority=1)]
    assert WU.select("kink_disruption", {"axial_field": 0.2, "current": 2.0}, lib)[0]["id"] == "driven"
    assert WU.select("kink_disruption", {"axial_field": 0.2, "current": 1.0}, lib)[0]["id"] == "weak"


def test_unreviewed_entries_are_never_used():
    assert all(e["reviewed"] in WU.REVIEW_STATES for e in WU.load())


def test_absent_numbers_print_words_not_nan():
    assert f"{WU._clean(math.nan):.2f}" == "n/a" and f"{WU._clean(math.inf):.3g}" == "infinite"


def test_unresolved_helix_is_not_reported_as_n1():
    # seeded n >= 4: the kink lives outside n = 1..3, which stay at zero
    h, meta = make_run(m1=grow(4.0, 0.4), m1_n1=np.zeros(T.size), m1_n2=np.zeros(T.size),
                       m1_n3=np.zeros(T.size))
    f = FE.compute(h, meta)
    assert math.isnan(f["m1_dominant_n"]) and f["m1_resolved_frac"] == 0.0
    r = analyse(h, meta, with_ml=False)
    assert "resolves n = 1 to 3 only" in " ".join(c["text"] for c in r["causes"])


def test_report_leads_with_the_writeup():
    r = analyse(*synthetic("saturated_kink"), with_ml=False)
    text = format_report(r)
    w = r["writeup"]
    assert w and text.index(w["title"]) < text.index("Data appendix") < text.index("Timeline")
    assert "Try next" in text and "n/a" not in " ".join(w["sections"].values())
    json.dumps(r)


EXAMPLES = [e for e in ENTRIES if e["example"]]


@pytest.mark.skipif(not os.path.isdir(SWEEP), reason="overnight sweep dataset not present")
@pytest.mark.parametrize("eid,run_id", [(e["id"], e["example"]) for e in EXAMPLES])
def test_example_runs_select_their_entry(eid, run_id):
    r = analyse_npz(os.path.join(SWEEP, run_id + ".npz"), with_ml=False)
    w = r["writeup"]
    assert w is not None and w["id"] == eid, (r["label"], w and w["id"])
    text = " ".join(w["sections"].values())
    assert "n/a" not in text and "infinite" not in text


def test_examples_file_matches_the_entries():
    with open(os.path.join(WU.LIBRARY_DIR, "examples.json")) as fh:
        ex = json.load(fh)
    assert set(ex) == {e["id"] for e in EXAMPLES}
    for eid, x in ex.items():
        assert {"setup", "live", "run", "label"} <= set(x)


@pytest.mark.skipif(not os.path.isdir(SWEEP), reason="overnight sweep dataset not present")
def test_saturated_label_without_axial_field_is_explained_honestly():
    # r02217: B_z = 0, kink 1.06 a, column spread 1.00 time units after the
    # kink went nonlinear (the disruption cut-off), labelled saturated
    r = analyse_npz(os.path.join(SWEEP, "r02217.npz"), with_ml=False)
    assert r["label"] == "saturated_kink" and r["confidence"] == "low"
    assert r["writeup"]["id"] == "saturated-kink-no-bz"
    text = " ".join(r["writeup"]["sections"].values()) + " ".join(c["text"] for c in r["causes"])
    assert "held just enough" not in text and "stretch the axial field" not in text
