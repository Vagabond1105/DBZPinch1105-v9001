"""
Diagnostic plots and export. Plot functions draw into a given matplotlib
Axes so the same code serves the live GUI panel and the exported PNGs.
"""

import csv
import io
import json
import zipfile
from dataclasses import asdict

import numpy as np
from matplotlib.figure import Figure

from .pinch import HISTORY_KEYS


def history_arrays(history, max_points=None):
    n = min(len(v) for v in history.values())
    out = {k: np.asarray(v[:n]) for k, v in history.items()}
    if max_points and n > max_points:
        idx = np.linspace(0, n - 1, max_points).astype(int)
        out = {k: v[idx] for k, v in out.items()}
    return out


def _style(ax, title, ylabel, log=False):
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("t", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.3)
    if log:
        ax.set_yscale("log")


def plot_energy(ax, h):
    t = h["t"]
    ax.plot(t, h["kinetic"], label="kinetic")
    ax.plot(t, h["magnetic"], label="magnetic")
    ax.plot(t, h["thermal"], label="thermal")
    if np.any(h["potential"] != 0):
        ax.plot(t, h["potential"], label="potential")
    ax.plot(t, h["total"], "k", lw=1.6, label="total")
    if len(t):
        e0 = h["total"][0]
        ax.plot(t, e0 + h["injected"] - h["radiated"] + h["floor"], ":", color="tab:red", lw=1.4,
                label="E0 + circuit - radiated + floors")
    ax.legend(fontsize=6, loc="best")
    _style(ax, "Energy", "energy")


def plot_modes(ax, h):
    t = h["t"]
    ax.plot(t, np.maximum(h["m0"], 1e-8), label="m=0 sausage")
    ax.plot(t, np.maximum(h["m1"], 1e-8), label="m=1 kink")
    if np.any(h["shift"] > 1e-3):
        ax.plot(t, np.maximum(h["shift"], 1e-8), ":", color="0.4", label="bulk offset (not a kink)")
    ax.legend(fontsize=6, loc="best")
    _style(ax, "Instability amplitude", "relative amplitude", log=True)


def plot_pinch(ax, h, a0):
    t = h["t"]
    ax.plot(t, h["radius"] / a0, label="radius / a0")
    ax.plot(t, h["core_temperature"], label="core T / T0")
    ax.plot(t, h["core_density"], label="core rho / rho0")
    ax.legend(fontsize=6, loc="best")
    _style(ax, "Pinch column", "normalised")


def plot_current(ax, h):
    t = h["t"]
    ax.plot(t, h["current_drive"], label="I circuit / I_B")
    ax.plot(t, h["current_measured"], "--", label="I from Ampere / I_B")
    ax.plot(t, np.clip(h["bennett_ratio"], 0, 5), label="Bennett ratio")
    ax.legend(fontsize=6, loc="best")
    _style(ax, "Current & Bennett relation", "normalised")


def plot_conservation(ax, h):
    t = h["t"]
    ax.plot(t, np.maximum(np.abs(h["energy_error"]), 1e-17), label="|energy budget error|")
    ax.plot(t, np.maximum(np.abs(h["mass_error"]), 1e-17), label="|mass error|")
    ax.plot(t, np.maximum(h["divb"], 1e-17), label="max |div B| dx / |B|")
    ax.legend(fontsize=6, loc="best")
    _style(ax, "Conservation checks", "relative error", log=True)


def draw_live(fig, history, a0):
    h = history_arrays(history, max_points=1500)
    fig.clear()
    axes = fig.subplots(1, 4)
    plot_energy(axes[0], h)
    plot_modes(axes[1], h)
    plot_pinch(axes[2], h, a0)
    plot_current(axes[3], h)
    fig.tight_layout(pad=0.6)


def _json_safe(x):
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    raise TypeError(type(x))


def export_zip(sim, path, include_fields=True):
    """CSV time series, parameters, PNG plots, the run report (HTML, text, JSON, feature CSV) and (optionally) the final 3D fields."""
    h = history_arrays(sim.history)
    plots = {
        "energy.png": lambda ax: plot_energy(ax, h),
        "instability_modes.png": lambda ax: plot_modes(ax, h),
        "pinch_column.png": lambda ax: plot_pinch(ax, h, sim.a),
        "current_bennett.png": lambda ax: plot_current(ax, h),
        "conservation.png": lambda ax: plot_conservation(ax, h),
    }
    meta = {
        "setup": asdict(sim.setup),
        "live_at_export": asdict(sim.live),
        "grid": [sim.solver.nx, sim.solver.ny, sim.solver.nz],
        "dx": sim.solver.dx,
        "time": sim.t,
        "steps": sim.solver.n_steps,
        "bennett_current": sim.I_bennett,
        "alfven_time": sim.t_alfven,
        "units": "mu_0 = 1; length = domain width; rho0 = p0 = T0 = 1 (Bennett peak values)",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(HISTORY_KEYS)
        for row in zip(*(h[k] for k in HISTORY_KEYS)):
            w.writerow([f"{x:.10g}" for x in row])
        zf.writestr("timeseries.csv", buf.getvalue())
        zf.writestr("parameters.json", json.dumps(meta, indent=2))
        try:
            from .analysis import features as FE
            from .analysis.report import bundle
            b = bundle(*FE.run_from_sim(sim))
            zf.writestr("report.html", b["html"])
            zf.writestr("analysis.txt", b["text"])
            zf.writestr("analysis.json", json.dumps(b["report"], indent=1, default=_json_safe))
            zf.writestr("features.csv", b["csv"])
        except Exception as exc:  # noqa: BLE001 - a failed analysis must not lose the data export
            zf.writestr("analysis.txt", f"analysis failed: {type(exc).__name__}: {exc}")
        for name, draw in plots.items():
            fig = Figure(figsize=(7, 4.5), dpi=150)
            draw(fig.add_subplot(111))
            fig.tight_layout()
            png = io.BytesIO()
            fig.savefig(png, format="png")
            zf.writestr(name, png.getvalue())
        if include_fields:
            npz = io.BytesIO()
            np.savez_compressed(npz, **sim.snapshot_arrays(), x=sim.solver.xc[2:-2],
                                y=sim.solver.yc[2:-2], z=sim.solver.zc[2:-2])
            zf.writestr("fields_final.npz", npz.getvalue())
    return path
