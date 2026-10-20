"""
Physics worker process.

The solver runs in its own process so it never competes with the UI for
Python's GIL: the window stays smooth and the physics runs at headless
speed. Communication is message passing:

  UI -> worker : ("rebuild", setup_dict, live_dict), ("live", live_dict),
                 ("run", bool), ("step", n), ("field", name), ("ack",), ("threads", n),
                 ("export", path), ("analyse",), ("stop_at", t or None), ("quit",)
  worker -> UI : ("ready", geometry_dict), ("snapshot", snap_dict, history_rows),
                 ("error", text), ("exported", path), ("export_failed", text),
                 ("analysis", report_bundle), ("analysis_failed", text), ("stopped_at", t)

report_bundle is zpinch.analysis.report.bundle(): the analysis, its text
and HTML forms and the figure PNGs. ("stop_at", t) pauses the run once when
the time first passes t (the sweep and the outcome predictor stop at t = 3).

Snapshots are flow-controlled: a new one is only sent after the UI has
acknowledged the previous one, so a slow UI never builds up a backlog.
"""

import math
import multiprocessing as mp
import os
import queue
import time
import traceback
import warnings

SNAPSHOT_HZ = 30.0


def default_threads():
    # leave headroom for the UI / GL driver: measured on a 12-thread laptop,
    # 8 physics threads ran the GUI 2.5x faster than 12 (oversubscription)
    if os.environ.get("ZPINCH_THREADS"):
        return max(1, int(os.environ["ZPINCH_THREADS"]))
    n = os.cpu_count() or 2
    return max(1, n - 4) if n > 6 else max(1, n - 1)


def worker_main(cmd_q, out_q, n_threads):
    os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")
    warnings.filterwarnings("ignore", message=".*TBB.*")
    import numba
    numba.set_num_threads(min(n_threads, numba.config.NUMBA_NUM_THREADS))
    # small dynamic chunks: a preempted or slow (efficiency-core) thread no
    # longer stalls every parallel loop, which removes 3x timing spikes
    numba.set_parallel_chunksize(4)

    from dataclasses import fields
    from ..params import SetupParams, LiveParams
    from ..pinch import ZPinch, HISTORY_KEYS
    from ..diagnostics import export_zip
    from ..analysis import features as FE
    from ..analysis.report import bundle

    sim = None
    running = False
    step_requests = 0
    stop_at = None
    field_name = "Density"
    acked = True
    force_snapshot = False
    last_snap = 0.0
    snap_steps = -1
    sent_hist = 0
    version = 0
    rate_t, rate_n, rate = time.perf_counter(), 0, 0.0

    def history_rows():
        nonlocal sent_hist
        n = min(len(sim.history[k]) for k in HISTORY_KEYS)
        rows = {k: sim.history[k][sent_hist:n] for k in HISTORY_KEYS}
        sent_hist = n
        return rows

    while True:
        idle = sim is None or not (running or step_requests)
        try:
            msg = cmd_q.get(timeout=0.02) if idle else cmd_q.get_nowait()
        except queue.Empty:
            msg = None
        while msg is not None:
            kind = msg[0]
            if kind == "quit":
                return
            try:
                if kind == "rebuild":
                    running = False
                    step_requests = 0
                    sim = ZPinch(SetupParams(**msg[1]), LiveParams(**msg[2]))
                    sv = sim.solver
                    sent_hist = 0
                    out_q.put(("ready", dict(
                        lo=sv.lo, hi=sv.hi, dx=sv.dx, shape=(sv.nx, sv.ny, sv.nz),
                        a=sim.a, t_alfven=sim.t_alfven, I_bennett=sim.I_bennett,
                        tracer_tag=sim.tracer_tag)))
                    force_snapshot = True
                    acked = True
                elif kind == "live" and sim is not None:
                    for f in fields(LiveParams):
                        setattr(sim.live, f.name, msg[1][f.name])
                elif kind == "threads":
                    numba.set_num_threads(max(1, min(int(msg[1]), numba.config.NUMBA_NUM_THREADS)))
                elif kind == "run":
                    running = bool(msg[1]) and sim is not None
                elif kind == "step":
                    step_requests += int(msg[1])
                elif kind == "field":
                    field_name = msg[1]
                    force_snapshot = True
                elif kind == "ack":
                    acked = True
                elif kind == "export" and sim is not None:
                    export_zip(sim, msg[1])
                    out_q.put(("exported", msg[1]))
                elif kind == "analyse" and sim is not None:
                    out_q.put(("analysis", bundle(*FE.run_from_sim(sim))))
                elif kind == "stop_at":
                    stop_at = None if msg[1] is None else float(msg[1])
            except Exception:
                if kind in ("export", "analyse"):
                    failed = "export_failed" if kind == "export" else "analysis_failed"
                    out_q.put((failed, traceback.format_exc()))
                else:
                    out_q.put(("error", traceback.format_exc()))
                    running = False
            try:
                msg = cmd_q.get_nowait()
            except queue.Empty:
                msg = None

        if sim is None:
            continue

        if running or step_requests:
            try:
                t_before = sim.t
                sim.step()
                rate_n += 1
                if stop_at is not None and t_before < stop_at <= sim.t:
                    running = False
                    step_requests = 0
                    force_snapshot = True
                    out_q.put(("stopped_at", sim.t))
                step_requests = max(0, step_requests - 1)
                if not math.isfinite(sim.history["total"][-1]) or not math.isfinite(sim.solver.dt):
                    raise FloatingPointError("the solution became non-finite (NaN/Inf)")
            except Exception:
                out_q.put(("error", traceback.format_exc()))
                running = False
                step_requests = 0

        now = time.perf_counter()
        if now - rate_t >= 1.0:
            rate = rate_n / (now - rate_t)
            rate_t, rate_n = now, 0

        new_data = sim.solver.n_steps != snap_steps
        if acked and (force_snapshot or (new_data and now - last_snap >= 1.0 / SNAPSHOT_HZ)):
            version += 1
            snap = dict(version=version, field_name=field_name, field=sim.field(field_name),
                        tracers=sim.tracers.astype("float32"), latest=sim.latest(),
                        steps=sim.solver.n_steps, steps_per_second=rate if running else 0.0,
                        running=running)
            out_q.put(("snapshot", snap, history_rows()))
            acked = False
            force_snapshot = False
            last_snap = now
            snap_steps = sim.solver.n_steps


class SimClient:
    """UI-side handle on the worker process."""

    def __init__(self, n_threads=None):
        ctx = mp.get_context("spawn")
        self.cmd_q = ctx.Queue()
        self.out_q = ctx.Queue()
        self.proc = ctx.Process(target=worker_main, daemon=True,
                                args=(self.cmd_q, self.out_q, n_threads or default_threads()))
        self.proc.start()

    def send(self, *msg):
        self.cmd_q.put(msg)

    def poll(self):
        msgs = []
        while True:
            try:
                msgs.append(self.out_q.get_nowait())
            except queue.Empty:
                return msgs

    def close(self):
        try:
            self.send("quit")
            self.proc.join(timeout=2.0)
        finally:
            if self.proc.is_alive():
                self.proc.terminate()
