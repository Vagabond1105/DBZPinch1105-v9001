"""
v3 phase 5: the run report (zpinch/analysis/report.py) and what carries it,
the export zip and the textbook-run list.

The standalone HTML must open anywhere: one file, figures embedded, nothing
fetched from the network. The GUI panel's HTML must stay inside what Qt's
rich-text engine renders. Every class's report must build.
"""

import html
import io
import json
import os
import re
import zipfile

os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")

import pytest

from zpinch.analysis import features as FE
from zpinch.analysis import report as RP
from zpinch.analysis import writeup as WU
from zpinch.analysis.rules import CLASSES
from zpinch.diagnostics import export_zip
from zpinch.params import LiveParams, PRESETS, SetupParams
from zpinch.pinch import ZPinch

from .test_library import synthetic


@pytest.fixture(scope="module")
def bundles():
    return {cls: RP.bundle(*synthetic(cls)) for cls in CLASSES}


@pytest.mark.parametrize("cls", CLASSES)
def test_every_class_gets_a_standalone_report(bundles, cls):
    b = bundles[cls]
    page, w = b["html"], b["report"]["writeup"]
    assert b["report"]["label"] == cls
    assert page.startswith("<!doctype html>") and "<title>" in page
    assert html.escape(w["title"]) in page
    for head in WU.SECTIONS:
        assert f"<h2>{head}</h2>" in page
    # every figure embedded, nothing loaded from elsewhere
    assert page.count('src="data:image/png;base64,') == len(RP.FIGURE_CAPTIONS)
    assert not re.search(r'(src|href)="(https?:)?//', page)
    assert "prefers-color-scheme: dark" in page
    json.dumps(b["report"])


def test_panel_html_stays_inside_qt_rich_text(bundles):
    b = bundles["saturated_kink"]
    panel = RP.body(b["report"], b["meta"], img=lambda n: "x/" + n, standalone=False)
    assert "<details" not in panel and "<style" not in panel and "var(--" not in panel
    for name in RP.FIGURE_CAPTIONS:
        assert f'src="x/{name}"' in panel
    assert panel.index(html.escape(b["report"]["writeup"]["title"])) < panel.index("Data appendix")


def test_numbers_print_as_words():
    assert RP._num(float("nan")) == "n/a" and RP._num(float("inf")) == "infinite"
    assert RP._num(True) == "yes" and RP._num("HLLD") == "HLLD"


def test_feature_csv_has_every_feature(bundles):
    rows = list(io.StringIO(bundles["quiescent"]["csv"]))
    assert rows[0].startswith("feature,value,unit,meaning")
    assert len(rows) == 1 + len(FE.FEATURE_NAMES)


def test_export_zip_carries_the_report(tmp_path):
    sim = ZPinch(SetupParams(n_tracers=0))
    while sim.t < 0.1:
        sim.step()
    path = export_zip(sim, str(tmp_path / "run.zip"), include_fields=False)
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert {"report.html", "analysis.txt", "analysis.json", "features.csv", "timeseries.csv"} <= names
        assert "data:image/png;base64," in zf.read("report.html").decode()


def test_textbook_runs_load_into_the_parameter_classes():
    ex = WU.load_examples()
    assert ex and set(ex) <= {e["id"] for e in WU.load()}
    for eid, x in ex.items():
        assert x["title"] and x["t_end"] > 0
        SetupParams(**{k: v for k, v in x["setup"].items()})     # every key is a real setting
        LiveParams(**{k: v for k, v in x["live"].items()})


def test_presets_named_by_the_library_exist():
    for e in WU.load():
        assert not e["preset"] or e["preset"] in PRESETS, (e["id"], e["preset"])
