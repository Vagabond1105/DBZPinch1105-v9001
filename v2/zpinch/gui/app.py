"""
Main window. Physics runs in a separate process (see worker.py); the UI
polls for snapshots at ~30 Hz, so dragging a slider or orbiting the
camera never waits on the solver, and the solver never waits on the UI.
"""

import dataclasses
import os

import numpy as np
import vispy
from matplotlib import colormaps as mpl_colormaps
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

vispy.use(app="pyqt5")

from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: E402

from ..diagnostics import draw_live  # noqa: E402
from ..params import SetupParams, LiveParams, PRESETS, apply_preset, describe  # noqa: E402
from ..pinch import FIELDS, HISTORY_KEYS  # noqa: E402
from .controls import build_form  # noqa: E402
from .view3d import PinchView, RENDER_MODES, COLORMAPS  # noqa: E402
from .worker import SimClient, default_threads  # noqa: E402

PLOT_INTERVAL_MS = 1000

# fields that span orders of magnitude look best on a log scale
LOG_DEFAULT = {"Density", "Pressure", "Plasma beta", "Current density |J|"}

# the sweep the models were trained on ran every case to t = 3, and the
# outcome predictor forecasts the outcome at t = 3: pausing there compares
# a GUI run with the textbook runs and the prediction like for like
STOP_AT_DEFAULT = 3.0


class ReportView(QtWidgets.QTextBrowser):
    """The report panel's text: serves the report's figures from memory."""

    def __init__(self):
        super().__init__()
        self.images = {}
        self.setOpenExternalLinks(True)
        from ..analysis.report import QT_STYLE
        self.document().setDefaultStyleSheet(QT_STYLE)
        self.setPlaceholderText("Press Finish & analyse (or let the run reach the pause time) "
                                "to see what happened in this run, why, and what to try next.")

    def show_report(self, html, images):
        self.images = images
        self.setHtml(html)
        self.verticalScrollBar().setValue(0)

    def loadResource(self, kind, url):
        img = self.images.get(url.toString())
        if kind == QtGui.QTextDocument.ImageResource and img is not None:
            return img
        return super().loadResource(kind, url)


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Z-Pinch MHD v2")
        self.resize(1600, 980)

        self.setup = SetupParams()
        self.live = LiveParams()
        self.client = SimClient()
        self.geom = None            # geometry of the current run (from the worker)
        self.history = {k: [] for k in HISTORY_KEYS}
        self.latest_snap = None
        self.running = False
        self._clim = None
        self._tracer_colors = None
        self._plotted_n = -1
        self._last_data = None
        self.report = None          # the last analysis (zpinch.analysis.report.bundle)
        self._n_reports = 0
        try:
            from ..analysis.writeup import load_examples
            self.examples = load_examples()
        except Exception:  # noqa: BLE001 - a broken library must not break the window
            self.examples = {}

        self.view = PinchView()
        self._build_ui()

        self._send_stop_at()
        self.client.send("rebuild", dataclasses.asdict(self.setup), dataclasses.asdict(self.live))

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / 60))
        self.plot_timer = QtCore.QTimer(self)
        self.plot_timer.timeout.connect(self._update_plots)
        self.plot_timer.start(PLOT_INTERVAL_MS)

    # =====================================================
    # layout
    # =====================================================

    def _build_ui(self):
        central = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(central)
        hl.setContentsMargins(4, 4, 4, 4)

        left = QtWidgets.QVBoxLayout()
        self.status = QtWidgets.QLabel("Compiling physics kernels (first launch only, ~30 s)...")
        self.status.setStyleSheet("font-family: monospace; padding: 3px;")
        # the status line is long once a run starts; let it clip instead of
        # setting the window's minimum width (with the report panel docked
        # beside the view, it pushed the window past a 1920-pixel screen)
        self.status.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        left.addWidget(self.status)
        self.view.canvas.native.setParent(central)
        self.view.canvas.native.setFocusPolicy(QtCore.Qt.StrongFocus)
        left.addWidget(self.view.canvas.native, 1)
        hl.addLayout(left, 1)

        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        pl.setContentsMargins(2, 2, 2, 2)
        pl.addWidget(self._run_group())
        live_box, self.live_controls = build_form(self.live, describe(LiveParams), self._on_live)
        pl.addWidget(self._group("Live physics (applies immediately)", live_box))
        setup_box, self.setup_controls = build_form(self.setup, describe(SetupParams), self._on_setup)
        pl.addWidget(self._group("Setup (applied on Reset)", setup_box))
        pl.addWidget(self._view_group())
        pl.addWidget(self._stats_group())
        pl.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(470)
        hl.addWidget(scroll)
        self.setCentralWidget(central)

        # live plots dock
        self.fig = Figure(figsize=(12, 2.6), dpi=90)
        self.plot_canvas = FigureCanvasQTAgg(self.fig)
        dock = QtWidgets.QDockWidget("Diagnostics", self)
        dock.setWidget(self.plot_canvas)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        self._report_dock()

        QtWidgets.QShortcut(QtGui.QKeySequence("Space"), self, activated=self._toggle_run)
        QtWidgets.QShortcut(QtGui.QKeySequence("N"), self, activated=self._step_once)

    @staticmethod
    def _group(title, widget):
        g = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(g)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.addWidget(widget)
        return g

    def _run_group(self):
        g = QtWidgets.QGroupBox("Run")
        grid = QtWidgets.QGridLayout(g)
        self.btn_run = QtWidgets.QPushButton("Start  [Space]")
        self.btn_run.clicked.connect(self._toggle_run)
        self.btn_step = QtWidgets.QPushButton("Step  [N]")
        self.btn_step.clicked.connect(self._step_once)
        self.btn_reset = QtWidgets.QPushButton("Reset")
        self.btn_reset.setToolTip("Rebuild the initial state with the current Setup values.")
        self.btn_reset.clicked.connect(self._reset)
        btn_defaults = QtWidgets.QPushButton("Reset to defaults")
        btn_defaults.clicked.connect(self._reset_defaults)
        self.btn_export = QtWidgets.QPushButton("Export data...")
        self.btn_export.clicked.connect(self._export)
        self.btn_analyse = QtWidgets.QPushButton("Finish && analyse")
        self.btn_analyse.setToolTip("Pause, then label the run so far and open the report: what "
                                    "happened, why, what to try next, and the data behind it.")
        self.btn_analyse.clicked.connect(self._analyse)
        self.sp_threads = QtWidgets.QSpinBox()
        self.sp_threads.setRange(1, os.cpu_count() or 1)
        self.sp_threads.setValue(default_threads())
        self.sp_threads.setToolTip("CPU threads used by the physics. More = faster physics, "
                                   "until the UI and graphics driver start competing for cores.")
        self.sp_threads.valueChanged.connect(lambda n: self.client.send("threads", n))
        grid.addWidget(self.btn_run, 0, 0)
        grid.addWidget(self.btn_step, 0, 1)
        grid.addWidget(self.btn_reset, 1, 0)
        grid.addWidget(btn_defaults, 1, 1)
        self.cb_preset = QtWidgets.QComboBox()
        self.cb_preset.addItems(list(PRESETS))
        self.cb_preset.setToolTip("Load a named starting point (all other values back to defaults) and reset.")
        self.cb_preset.activated[str].connect(self._load_preset)
        grid.addWidget(self.btn_analyse, 2, 0)
        grid.addWidget(self.btn_export, 2, 1)
        grid.addWidget(QtWidgets.QLabel("Preset"), 3, 0)
        grid.addWidget(self.cb_preset, 3, 1)
        self.cb_textbook = QtWidgets.QComboBox()
        # long entry titles must not widen the fixed-width control column
        self.cb_textbook.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_textbook.setMinimumContentsLength(20)
        self.cb_textbook.addItem("choose..." if self.examples else "none (library/examples.json missing)", None)
        for eid, ex in self.examples.items():
            self.cb_textbook.addItem(ex["title"], eid)
        self.cb_textbook.setToolTip(
            "Load the exact settings of a run from the overnight sweep that a library write-up was "
            "checked on. Press Start; it pauses at t = 3 and opens the report.")
        self.cb_textbook.activated[int].connect(
            lambda i: i > 0 and self._load_textbook(self.cb_textbook.itemData(i)))
        grid.addWidget(QtWidgets.QLabel("Textbook run"), 4, 0)
        grid.addWidget(self.cb_textbook, 4, 1)
        self.chk_stop = QtWidgets.QCheckBox("Pause && analyse at t =")
        self.chk_stop.setChecked(True)
        self.sp_stop = QtWidgets.QDoubleSpinBox()
        self.sp_stop.setRange(0.1, 100.0)
        self.sp_stop.setSingleStep(0.5)
        self.sp_stop.setValue(STOP_AT_DEFAULT)
        tip = ("Pause the run and open the report when the time first reaches this value. The "
               "training sweep and the outcome predictor both stop at t = 3. Resume carries on.")
        self.chk_stop.setToolTip(tip)
        self.sp_stop.setToolTip(tip)
        self.chk_stop.toggled.connect(lambda _: self._send_stop_at())
        self.sp_stop.valueChanged.connect(lambda _: self._send_stop_at())
        grid.addWidget(self.chk_stop, 5, 0)
        grid.addWidget(self.sp_stop, 5, 1)
        grid.addWidget(QtWidgets.QLabel("Physics CPU threads"), 6, 0)
        grid.addWidget(self.sp_threads, 6, 1)
        self.lbl_predict = QtWidgets.QLabel()
        self.lbl_predict.setWordWrap(True)
        self.lbl_predict.setToolTip(
            "Outcome predictor (v3 phase 3b): a model trained on the overnight sweep forecasts what a "
            "run with these settings will do by t = 3, before you press Start. It only knows the "
            "region the sweep covered and says so when you leave it.")
        grid.addWidget(self.lbl_predict, 7, 0, 1, 2)
        self._update_prediction()
        return g

    def _update_prediction(self):
        try:
            from ..analysis.explain import NAMES
            from ..analysis.model import format_prediction, predict_outcome
            pred = predict_outcome(dataclasses.asdict(self.setup), dataclasses.asdict(self.live))
        except Exception as exc:  # noqa: BLE001 - a missing/broken model must not break the window
            self.lbl_predict.setText(f"Predicted outcome: unavailable ({type(exc).__name__})")
            return
        if pred is None:
            self.lbl_predict.setText("Predicted outcome: no model trained yet (tools/train.py)")
            return
        self.lbl_predict.setText("<b>Predicted outcome by t = 3:</b> " + format_prediction(pred, NAMES))

    def _report_dock(self):
        self.report_view = ReportView()
        self.btn_save_report = QtWidgets.QPushButton("Save report...")
        self.btn_save_report.setToolTip("Save the report as a standalone HTML page (figures included, "
                                        "opens in any browser) or as plain text.")
        self.btn_save_report.clicked.connect(self._save_report)
        self.btn_copy_report = QtWidgets.QPushButton("Copy as text")
        self.btn_copy_report.clicked.connect(
            lambda: self.report and QtWidgets.QApplication.clipboard().setText(self.report["text"]))
        self.btn_textbook = QtWidgets.QPushButton("Load its textbook run")
        self.btn_textbook.clicked.connect(lambda: self._load_textbook(self.btn_textbook.property("entry")))
        self.btn_preset = QtWidgets.QPushButton("Load preset")
        self.btn_preset.clicked.connect(lambda: self._load_preset(self.btn_preset.property("preset")))
        for b in (self.btn_save_report, self.btn_copy_report, self.btn_textbook, self.btn_preset):
            b.setEnabled(False)
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)
        row = QtWidgets.QGridLayout()
        row.addWidget(self.btn_save_report, 0, 0)
        row.addWidget(self.btn_copy_report, 0, 1)
        row.addWidget(self.btn_textbook, 1, 0)
        row.addWidget(self.btn_preset, 1, 1)
        lay.addLayout(row)
        lay.addWidget(self.report_view, 1)
        self.report_dock = QtWidgets.QDockWidget("Run report", self)
        self.report_dock.setWidget(w)
        self.report_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable
                                     | QtWidgets.QDockWidget.DockWidgetFloatable
                                     | QtWidgets.QDockWidget.DockWidgetClosable)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.report_dock)
        self.report_dock.hide()

    def _view_group(self):
        g = QtWidgets.QGroupBox("View")
        form = QtWidgets.QFormLayout(g)
        self.cb_field = QtWidgets.QComboBox()
        self.cb_field.addItems(list(FIELDS))
        self.cb_field.currentTextChanged.connect(self._on_field)
        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.addItems(list(RENDER_MODES))
        self.cb_mode.currentTextChanged.connect(lambda m: self._restyle(mode=m))
        self.cb_cmap = QtWidgets.QComboBox()
        self.cb_cmap.addItems(COLORMAPS)
        self.cb_cmap.currentTextChanged.connect(lambda c: self._restyle(cmap=c))
        self.chk_log = QtWidgets.QCheckBox("log10 scale")
        self.chk_log.setChecked(True)
        self.chk_log.toggled.connect(lambda _: self._invalidate_clim())
        self.chk_lock = QtWidgets.QCheckBox("lock colour range")
        self.sl_iso = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_iso.setRange(1, 99)
        self.sl_iso.setValue(45)
        self.sl_iso.valueChanged.connect(lambda v: self._restyle(threshold=v / 100.0))
        self.chk_tracers = QtWidgets.QCheckBox("show tracers")
        self.chk_tracers.setChecked(True)
        self.chk_tracers.toggled.connect(lambda _: self._force_redraw())
        self.sp_size = QtWidgets.QDoubleSpinBox()
        self.sp_size.setRange(0.5, 10.0)
        self.sp_size.setValue(2.0)
        self.sp_size.valueChanged.connect(lambda _: self._force_redraw())
        btn_cam = QtWidgets.QPushButton("Reset camera  [R]")
        btn_cam.clicked.connect(self.view.reset_camera)
        scale_row = QtWidgets.QHBoxLayout()
        scale_row.addWidget(self.chk_log)
        scale_row.addWidget(self.chk_lock)
        tr_row = QtWidgets.QHBoxLayout()
        tr_row.addWidget(self.chk_tracers)
        tr_row.addWidget(QtWidgets.QLabel("size"))
        tr_row.addWidget(self.sp_size)
        form.addRow("Field", self.cb_field)
        form.addRow("Rendering", self.cb_mode)
        form.addRow("Colormap", self.cb_cmap)
        form.addRow("Scale", scale_row)
        form.addRow("Iso level", self.sl_iso)
        form.addRow("Tracers", tr_row)
        form.addRow(btn_cam)
        hint = QtWidgets.QLabel("Mouse: drag = orbit, shift+drag = pan, wheel = zoom. "
                                "Keys (click the 3D view first): arrows/WASD orbit, +/- zoom.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 10px;")
        form.addRow(hint)
        return g

    def _stats_group(self):
        g = QtWidgets.QGroupBox("Live diagnostics")
        lay = QtWidgets.QVBoxLayout(g)
        self.stats = QtWidgets.QLabel("")
        self.stats.setStyleSheet("font-family: monospace; font-size: 11px;")
        self.stats.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(self.stats)
        return g

    # =====================================================
    # control callbacks
    # =====================================================

    def _on_live(self, name, value):
        self.client.send("live", dataclasses.asdict(self.live))
        self._update_prediction()

    def _on_setup(self, name, value):
        self._update_prediction()
        self.btn_reset.setText("Reset  (apply new setup)")
        self.btn_reset.setStyleSheet("font-weight: bold; color: #e8a33d;")

    def _set_running(self, running):
        self.running = running
        self.client.send("run", running)
        self.btn_run.setText("Pause  [Space]" if running else "Resume  [Space]")

    def _toggle_run(self):
        if self.geom is not None:
            self._set_running(not self.running)

    def _step_once(self):
        if self.geom is not None and not self.running:
            self.client.send("step", 1)

    def _reset(self):
        self.running = False
        self.geom = None
        self.client.send("rebuild", dataclasses.asdict(self.setup), dataclasses.asdict(self.live))
        self.status.setText("Building initial state...")
        self.btn_run.setText("Start  [Space]")
        self.btn_reset.setText("Reset")
        self.btn_reset.setStyleSheet("")

    def _reset_defaults(self):
        self.cb_preset.setCurrentIndex(0)
        self._load_preset(self.cb_preset.currentText())

    def _load_preset(self, name):
        apply_preset(name, self.setup, self.live)
        self.cb_preset.setCurrentText(name)
        self.cb_textbook.setCurrentIndex(0)
        self._sync_controls()
        self._reset()

    def _sync_controls(self):
        for key, value in dataclasses.asdict(self.setup).items():
            self.setup_controls[key].set_value(value)
        for key, value in dataclasses.asdict(self.live).items():
            self.live_controls[key].set_value(value)
        self._update_prediction()

    def _load_textbook(self, eid):
        """A sweep run's exact settings (library/examples.json), paused at its end time."""
        ex = self.examples.get(eid)
        if ex is None:
            return
        apply_preset(next(iter(PRESETS)), self.setup, self.live)      # all defaults first
        n_tracers = self.setup.n_tracers
        for obj, values in ((self.setup, ex["setup"]), (self.live, ex["live"])):
            for key, value in values.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
        # the sweep saved no tracers; they are passive markers with their own
        # random numbers (pinch.py _init_tracers), so the physics is unchanged
        self.setup.n_tracers = n_tracers
        self.cb_textbook.setCurrentIndex(max(0, self.cb_textbook.findData(eid)))
        self.cb_preset.setCurrentIndex(-1)      # blank: no preset is in use, don't show one
        self.chk_stop.setChecked(True)
        self.sp_stop.setValue(round(ex["t_end"], 2))
        self._sync_controls()
        self._reset()
        self.statusBar().showMessage(
            f"Textbook run loaded: {ex['title']} (sweep run {ex['run']}). Press Start: it pauses at "
            f"t = {self.sp_stop.value():g} and opens the report.")

    def _send_stop_at(self):
        self.client.send("stop_at", self.sp_stop.value() if self.chk_stop.isChecked() else None)

    def _on_field(self, name):
        self.client.send("field", name)
        self.chk_log.blockSignals(True)
        self.chk_log.setChecked(name in LOG_DEFAULT)
        self.chk_log.blockSignals(False)
        self._clim = None

    def _restyle(self, **kw):
        self.view.set_style(**kw)
        self._force_redraw()

    def _invalidate_clim(self):
        self._clim = None
        self._force_redraw()

    def _force_redraw(self):
        if self._last_data is not None:
            self._show_field(self._last_data)
            self._show_tracers()

    def _export(self):
        if self.geom is None:
            return
        if self.running:
            self._set_running(False)
        t = self.latest_snap["latest"]["t"] if self.latest_snap else 0.0
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export diagnostics", f"zpinch_t{t:.2f}.zip", "Zip archive (*.zip)")
        if path:
            self.client.send("export", path)
            self.statusBar().showMessage(f"Exporting to {path} ...")

    def _analyse(self):
        if self.geom is None:
            return
        if self.running:
            self._set_running(False)
        self.client.send("analyse")
        self.statusBar().showMessage("Analysing the run ...")

    def _show_report(self, b):
        from ..analysis.report import body
        self.statusBar().clearMessage()
        self.report = b
        self._n_reports += 1
        # a fresh name per report: QTextDocument caches images by URL
        prefix = f"report{self._n_reports}/"
        images = {prefix + name: QtGui.QImage.fromData(png) for name, png in b["images"].items()}
        self.report_view.show_report(body(b["report"], b["meta"], img=lambda n: prefix + n, standalone=False),
                                     images)
        w = b["report"].get("writeup") or {}
        ex = self.examples.get(w.get("id"))
        self.btn_textbook.setEnabled(ex is not None)
        self.btn_textbook.setProperty("entry", w.get("id"))
        self.btn_textbook.setToolTip(
            f"Load sweep run {ex['run']}, the run this write-up was checked on, and pause at t = 3."
            if ex else "This write-up has no textbook run.")
        preset = w.get("preset")
        self.btn_preset.setEnabled(preset in PRESETS)
        self.btn_preset.setProperty("preset", preset)
        self.btn_preset.setText(f"Load preset: {preset}" if preset in PRESETS else "Load preset")
        for btn in (self.btn_save_report, self.btn_copy_report):
            btn.setEnabled(True)
        if self.report_dock.isHidden():
            self.report_dock.show()
            self.resizeDocks([self.report_dock], [600], QtCore.Qt.Horizontal)
        self.report_dock.raise_()

    def _save_report(self):
        if not self.report:
            return
        r = self.report["report"]
        name = f"report_{r['label']}_t{r['features']['t_final']:.2f}.html"
        path, chosen = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save run report", name, "HTML report (*.html);;Plain text (*.txt)")
        if not path:
            return
        if not path.lower().endswith((".html", ".htm", ".txt")):
            path += ".txt" if chosen.startswith("Plain") else ".html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.report["text"] if path.lower().endswith(".txt") else self.report["html"])
        self.statusBar().showMessage(f"Saved report to {path}", 8000)

    # =====================================================
    # worker messages
    # =====================================================

    def _tick(self):
        for msg in self.client.poll():
            kind = msg[0]
            if kind == "ready":
                self._on_ready(msg[1])
            elif kind == "snapshot":
                self._on_snapshot(msg[1], msg[2])
            elif kind == "error":
                self._on_error(msg[1])
            elif kind == "analysis":
                self._show_report(msg[1])
            elif kind == "stopped_at":
                self.running = False
                self.btn_run.setText("Resume  [Space]")
                self._analyse()
                self.statusBar().showMessage(f"Paused at t = {msg[1]:.2f}: analysing the run ...")
            elif kind == "analysis_failed":
                self.statusBar().clearMessage()
                QtWidgets.QMessageBox.warning(self, "Analysis failed", msg[1].strip().splitlines()[-1])
            elif kind == "exported":
                self.statusBar().showMessage(f"Exported to {msg[1]}", 8000)
            elif kind == "export_failed":
                self.statusBar().clearMessage()
                QtWidgets.QMessageBox.warning(self, "Export failed", msg[1].strip().splitlines()[-1])
        if not self.client.proc.is_alive():
            self.timer.stop()
            QtWidgets.QMessageBox.critical(self, "Worker died", "The physics process exited unexpectedly.")

    def _on_ready(self, geom):
        self.geom = geom
        self.history = {k: [] for k in HISTORY_KEYS}
        self._plotted_n = -1
        self._clim = None
        self.view.set_geometry(geom["lo"], geom["hi"], geom["dx"], geom["shape"])
        self._tracer_colors = mpl_colormaps["cool"](geom["tracer_tag"])
        self._tracer_colors[:, 3] = 0.85

    def _on_snapshot(self, snap, rows):
        self.client.send("ack")
        for k, v in rows.items():
            self.history[k].extend(v)
        if self.geom is None:
            return
        self.latest_snap = snap
        self._show_field(snap["field"])
        self._show_tracers()
        self._update_status()

    def _on_error(self, text):
        self.running = False
        self.btn_run.setText("Resume  [Space]")
        self.status.setText("Simulation stopped - see error dialog.")
        QtWidgets.QMessageBox.critical(
            self, "Simulation error",
            "The solver stopped:\n\n" + text.strip().splitlines()[-1]
            + "\n\nTry a lower drive current, a higher background density, "
              "or the HLL solver, then Reset.")

    # =====================================================
    # drawing
    # =====================================================

    def _show_field(self, field):
        self._last_data = field
        data = np.log10(np.maximum(field, 1e-12)) if self.chk_log.isChecked() else field
        if not (self.chk_lock.isChecked() and self._clim is not None):
            sample = data[::2, ::2, ::2]
            # volume: background level -> transparent; slice: show the full range
            lo = float(sample.min()) if self.view.is_slice else float(np.percentile(sample, 40.0))
            hi = float(sample.max())
            if self._clim is None:
                self._clim = [lo, hi]
            else:
                # snap up immediately, relax down slowly (avoids flicker)
                self._clim[0] = lo
                self._clim[1] = hi if hi > self._clim[1] else 0.9 * self._clim[1] + 0.1 * hi
        self.view.set_field(data, self._clim)
        self.view.canvas.update()

    def _show_tracers(self):
        if self.latest_snap is None or self._tracer_colors is None:
            return
        pos = self.latest_snap["tracers"]
        colors = self._tracer_colors[:len(pos)]
        self.view.set_tracers(pos, colors, self.sp_size.value(), self.chk_tracers.isChecked())
        self.view.canvas.update()

    def _update_status(self):
        snap, g = self.latest_snap, self.geom
        L = snap["latest"]
        state = "running" if snap["running"] else "paused"
        nx, ny, nz = g["shape"]
        self.status.setText(
            f"t = {L['t']:.3f}  ({L['t'] / g['t_alfven']:.1f} t_A)   step {snap['steps']}   "
            f"dt = {L['dt']:.2e}   {snap['steps_per_second']:.1f} steps/s "
            f"({snap['steps_per_second'] * L['dt']:.3f} t/s)   "
            f"grid {nx}x{ny}x{nz}   [{state}]   "
            f"showing: {snap['field_name']}  range {self._clim[0]:.3g} .. {self._clim[1]:.3g}"
            f"{' (log10)' if self.chk_log.isChecked() else ''}")
        rows = [
            ("drive current I/I_B", L["current_drive"], "{:.3f}"),
            ("Ampere-law current", L["current_measured"], "{:.3f}"),
            ("Bennett ratio", L["bennett_ratio"], "{:.3f}"),
            ("pinch radius / a0", L["radius"] / g["a"], "{:.3f}"),
            ("core temperature", L["core_temperature"], "{:.3f}"),
            ("peak temperature", L["peak_temperature"], "{:.3f}"),
            ("peak density", L["peak_density"], "{:.3f}"),
            ("m=0 sausage amp", L["m0"], "{:.2e}"),
            ("m=1 kink amp", L["m1"], "{:.2e}"),
            ("bulk offset (n=0)", L["shift"], "{:.2e}"),
            ("kinetic energy", L["kinetic"], "{:.4e}"),
            ("magnetic energy", L["magnetic"], "{:.4e}"),
            ("thermal energy", L["thermal"], "{:.4e}"),
            ("circuit energy in", L["injected"], "{:+.3e}"),
            ("radiated energy", L["radiated"], "{:.3e}"),
            ("vacuum-floor energy", L["floor"], "{:.3e}"),
            ("energy budget err", L["energy_error"], "{:+.1e}"),
            ("mass error", L["mass_error"], "{:+.1e}"),
            ("max |divB| dx/|B|", L["divb"], "{:.1e}"),
        ]
        self.stats.setText("\n".join(f"{name:<21s}{fmt.format(v):>12s}" for name, v, fmt in rows))

    def _update_plots(self):
        if self.geom is None or not self.isVisible():
            return
        n = len(self.history["t"])
        if n == self._plotted_n or n == 0:
            return
        self._plotted_n = n
        draw_live(self.fig, self.history, self.geom["a"])
        self.plot_canvas.draw_idle()

    def closeEvent(self, event):
        self.client.close()
        super().closeEvent(event)


def run():
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    qapp.exec_()
