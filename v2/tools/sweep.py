"""
Overnight parameter sweep (v3 plan, Phase 2): many headless runs -> dataset/.

Each run starts from the GUI defaults, changes the 8 swept parameters
(current, rise time, B_z, resistivity, viscosity, cooling, gravity, column
length) plus the random seed, and saves its starting parameters and its
full diagnostic history (every HISTORY_KEY, down-sampled to dt = 0.005).
Phase 1 (rules, features) and Phase 3 (models) are built afterwards on the
saved data, so nothing here decides what a run "is" - it only records.

    .venv/bin/python tools/sweep.py plan   DIR --n 8000 --res-check 100
    .venv/bin/python tools/sweep.py bench  DIR            # jobs x threads throughput
    .venv/bin/python tools/sweep.py run    DIR --jobs 6 --threads 2 --hours 10
    .venv/bin/python tools/sweep.py status DIR
    .venv/bin/python tools/sweep.py stop   DIR            # finish running jobs, then exit

Layout of DIR:
    sweep.json        plan settings, code version
    jobs.jsonl        every planned job, in run order (any prefix is a fair sample)
    index.jsonl       one line per finished job: status, stop reason, summary numbers
    runs/<id>.npz     h_<key> arrays (history) + meta (JSON string: params, derived numbers)
    logs/             driver log, one stderr log per worker slot

`run` is resumable: it skips every job already in index.jsonl, so it can be
killed at any time and started again with the same command.

Parallelism: the driver keeps J worker processes alive, each running numba
with T threads and pulling one job at a time over a pipe, so the kernels are
loaded once per worker rather than once per run. `bench` measures which
J x T gives the most runs per hour on this machine.
"""

import argparse
import dataclasses
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime

import numpy as np

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from zpinch.analysis.features import derived_numbers  # noqa: E402  (moved there for v3 phase 1)

GRID_BASE = "Very fast (32 x 32 x 48)"     # the GUI default, see plan section 6.5
GRID_CHECK = "Fast (48 x 48 x 72)"         # resolution check twins (~5x the cost)
T_END = 3.0                                # cap on simulated time (plan section 6.5)
DT_SAVE = 0.005                            # history sample spacing: ~0.03 Alfven times
# wall-clock cap per run at 2 threads, scaled by 2/threads and by the N^4
# cost of the finer grid. In the rehearsal (2026-10-19, 1 thread per run)
# swept 32^3 runs took 37-370 s, the slowest being a fast-rising compression,
# so 720 s at 1 thread stops only runs whose time step has collapsed.
WALL_CAP_BASE = 360.0
COST_FACTOR = {GRID_BASE: 1.0, GRID_CHECK: 5.0}
WORKER_RECYCLE = 200                       # restart a worker after this many jobs (memory hygiene)

# ---- early stop (plan section 6.5: "stop once clearly ended") ----
# Disruption: in the pure Z-pinch the column breaks up once the kink's
# centre displacement passes ~2.4 a (measured health check, plan section 1); the
# wall sits ~4 a from the axis, so 2.5 a means the column is reaching it.
# The bulk offset (n = 0, e.g. a gravity sag) gets the same limit.
DISRUPT_M1 = 2.5
WALL_SHIFT = 2.5
GRACE = 0.3        # keep running this long after the trigger to record the break-up itself
# Settled: nothing changes over the trailing window. A mode amplitude that
# grows by < 15 % in 1.0 time units has a growth rate < 0.14, so from the
# 0.02 seed it could not reach even 0.1 a by t = 3 - stopping loses nothing.
SETTLE_AFTER = 1.5
SETTLE_WINDOW = 1.0
SETTLE_MODE_RATIO = 1.15
SETTLE_REL = 0.02      # radius, drive current: < 2 % change over the window
SETTLE_TEMP_REL = 0.05  # core temperature: < 5 % (ongoing heating/cooling is not "settled")


# =====================================================
# sampling (which runs to do)
# =====================================================

def _logu(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def _round(x):
    return float(f"{x:.4g}")


def _broad(rng):
    """
    The whole swept box. Ranges sit inside the GUI slider ranges
    (zpinch/params.py). Zero is a special value for B_z, cooling and gravity
    (that physics is simply absent), so each is exactly zero part of the time;
    I = 1 is the equilibrium current, so it is kept exactly 30 % of the time.
    """
    return {
        "current": 1.0 if rng.random() < 0.3 else rng.uniform(0.4, 2.8),
        "rise_time": _logu(rng, 0.05, 1.0),
        "axial_field": 0.0 if rng.random() < 0.3 else rng.uniform(0.0, 1.5),
        "resistivity": _logu(rng, 1e-4, 1e-2),
        "viscosity": _logu(rng, 1e-4, 1e-2),
        "cooling": 0.0 if rng.random() < 0.5 else _logu(rng, 0.01, 2.0),
        "gravity": 0.0 if rng.random() < 0.6 else rng.uniform(0.05, 2.0),
        "length": rng.uniform(1.0, 3.0),
    }


# Rare outcome classes are oversampled (plan section 6.5) by drawing part of the
# runs from boxes where they should occur. Each box overrides a few of the
# broad draws; everything else stays random, so these runs still cover the
# rest of parameter space. The stratum is saved with each run, so a model
# can be evaluated on the broad runs alone (a uniform sample).
def _radiative(rng):
    # dense, compressed plasma radiates fastest (P ~ rho^2 sqrt T)
    return {"cooling": _logu(rng, 0.3, 2.0), "current": rng.uniform(1.0, 2.5)}


def _sausage(rng):
    # little B_z (it stiffens against m = 0, Kadomtsev), strong fast drive
    # and a short column (fewer long-wavelength kinks fit in)
    return {"axial_field": rng.uniform(0.0, 0.3), "current": rng.uniform(1.3, 2.8),
            "rise_time": _logu(rng, 0.05, 0.3), "length": rng.uniform(1.0, 1.6)}


def _gravity(rng):
    # strong B_z and a short column suppress the kink, so the n = 0 sag shows clearly
    return {"gravity": rng.uniform(0.3, 2.0), "axial_field": rng.uniform(0.8, 1.5),
            "length": rng.uniform(1.0, 1.5), "current": rng.uniform(0.8, 1.2)}


def _stable(rng):
    # Kruskal-Shafranov: q(a) = 2 pi a B_z / (L B_theta) > 1 needs large B_z, short L
    return {"axial_field": rng.uniform(1.0, 1.5), "length": rng.uniform(1.0, 1.5),
            "current": rng.uniform(0.8, 1.2)}


def _resistive(rng):
    # diffusion time a^2 / eta ~ 1.4-5 at these values: visible before t = 3
    return {"resistivity": _logu(rng, 3e-3, 1e-2), "current": rng.uniform(0.5, 1.2)}


def _compression(rng):
    # well above the Bennett current, fast rise; B_z resists the kink so the bounce shows
    return {"current": rng.uniform(1.5, 2.8), "rise_time": _logu(rng, 0.05, 0.3),
            "axial_field": rng.uniform(0.5, 1.5)}


STRATA = [  # (name, fraction of runs, override box)
    ("broad", 0.55, None),
    ("radiative", 0.10, _radiative),
    ("sausage", 0.10, _sausage),
    ("gravity", 0.10, _gravity),
    ("stable", 0.05, _stable),
    ("resistive", 0.05, _resistive),
    ("compression", 0.05, _compression),
]
SETUP_KEYS = ("axial_field", "length")     # the rest of the swept names are LiveParams


def sample_job(rng, idx):
    names = [s[0] for s in STRATA]
    probs = np.array([s[1] for s in STRATA])
    k = int(rng.choice(len(STRATA), p=probs / probs.sum()))
    params = _broad(rng)
    if STRATA[k][2] is not None:
        params.update(STRATA[k][2](rng))
    params = {key: _round(v) for key, v in params.items()}
    setup = {key: params[key] for key in SETUP_KEYS}
    live = {key: v for key, v in params.items() if key not in SETUP_KEYS}
    setup["seed"] = int(rng.integers(0, 10000))
    setup["resolution"] = GRID_BASE
    return {"id": f"r{idx:05d}", "kind": "base", "twin": None, "stratum": names[k],
            "setup": setup, "live": live, "t_end": T_END}


def make_plan(n, res_check, seed, gap):
    """
    n base runs in random order, with one 48^3 twin (same parameters) of an
    earlier run inserted every `gap` runs until res_check twins are placed.
    So the resolution check finishes early in the night, not at the very end.
    """
    rng = np.random.default_rng(seed)
    base = [sample_job(rng, i) for i in range(n)]
    out, n_twins = [], 0
    for i, job in enumerate(base):
        out.append(job)
        if n_twins < res_check and i % gap == gap - 1:
            src = base[i - gap + 1]
            twin = json.loads(json.dumps(src))
            twin.update(id=f"c{n_twins:04d}", kind="res48", twin=src["id"])
            twin["setup"]["resolution"] = GRID_CHECK
            out.append(twin)
            n_twins += 1
    return out


# =====================================================
# one run (inside a worker)
# =====================================================

class EarlyStop:
    def __init__(self):
        self.trigger_t = None
        self.trigger_reason = None
        self._next_check = 0.0

    def check(self, h):
        t = h["t"][-1]
        if self.trigger_t is not None:
            return self.trigger_reason if t >= self.trigger_t + GRACE else None
        if t < self._next_check:
            return None
        self._next_check = t + 0.02
        if h["m1"][-1] > DISRUPT_M1:
            self.trigger_t, self.trigger_reason = t, "disrupted"
        elif h["shift"][-1] > WALL_SHIFT:
            self.trigger_t, self.trigger_reason = t, "wall_contact"
        elif t >= SETTLE_AFTER and self._settled(h, t):
            return "settled"
        return None

    @staticmethod
    def _settled(h, t):
        tt = np.asarray(h["t"])
        i0 = int(np.searchsorted(tt, t - SETTLE_WINDOW))
        for key in ("m0", "m1"):
            w = np.maximum(np.asarray(h[key][i0:]), 1e-12)
            if w.max() / w.min() > SETTLE_MODE_RATIO:
                return False
        for key, tol in (("radius", SETTLE_REL), ("current_drive", SETTLE_REL),
                         ("core_temperature", SETTLE_TEMP_REL)):
            w = np.asarray(h[key][i0:])
            if (w.max() - w.min()) > tol * max(abs(w.mean()), 1e-12):
                return False
        return True


def downsample(h):
    t = np.asarray(h["t"])
    grid = np.arange(0.0, t[-1], DT_SAVE)
    idx = np.unique(np.append(np.searchsorted(t, grid), len(t) - 1))
    return {key: np.asarray(v)[idx] for key, v in h.items()}


def run_job(job, out_dir, threads, code_version):
    """Run one job, save runs/<id>.npz, return the index line (dict)."""
    from zpinch.params import SetupParams, LiveParams
    from zpinch.pinch import ZPinch

    setup, live = SetupParams(), LiveParams()
    for obj, over in ((setup, job["setup"]), (live, job["live"])):
        for key, value in over.items():
            setattr(obj, key, value)
    setup.n_tracers = 0                 # tracers are passive (display only) - skip their cost
    wall_cap = WALL_CAP_BASE * COST_FACTOR[setup.resolution] * 2.0 / threads

    res = {"id": job["id"], "kind": job["kind"], "twin": job["twin"], "stratum": job["stratum"],
           "status": "ok", "reason": "t_end", "error": None}
    t_wall = time.perf_counter()
    sim = None
    try:
        sim = ZPinch(setup, live)
        sv, h = sim.solver, sim.history
        stop = EarlyStop()
        while sim.t < job["t_end"]:
            sim.step()
            if not (math.isfinite(h["total"][-1]) and math.isfinite(h["m1"][-1])
                    and math.isfinite(sv.dt) and sv.dt > 0.0):
                res.update(status="failed", reason="nan")
                break
            reason = stop.check(h)
            if reason:
                res["reason"] = reason
                break
            if time.perf_counter() - t_wall > wall_cap:
                res.update(status="partial", reason="wall_cap")
                break
        if res["reason"] != "nan":
            # record the final state too (history holds the state at the start of each step)
            sv.flush()
            dm, de = sv.update_primitives()
            sv.floor_mass += dm
            sv.floor_energy += de
            sim._record(sv.W)
    except Exception as exc:  # noqa: BLE001 - any failure is data about the run
        res.update(status="failed", reason="error",
                   error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")
    wall = time.perf_counter() - t_wall

    res.update(wall=round(wall, 2), threads=threads, grid=setup.resolution,
               params={**job["setup"], **job["live"]})
    if sim is None or len(sim.history["t"]) < 2:
        return res

    full = sim.history
    h = downsample(full)
    a = sim.a
    finite = lambda x: float(x) if math.isfinite(x) else None  # noqa: E731
    res["summary"] = {
        "t_final": finite(full["t"][-1]),
        "n_steps": sim.solver.n_steps,
        "dt_min": finite(min(full["dt"][1:] or [math.nan])),
        "m0_max": finite(np.nanmax(full["m0"])), "m1_max": finite(np.nanmax(full["m1"])),
        "shift_max": finite(np.nanmax(full["shift"])),
        "radius_min_over_a": finite(np.nanmin(full["radius"]) / a),
        "radius_final_over_a": finite(full["radius"][-1] / a),
        "energy_error_max": finite(np.nanmax(np.abs(full["energy_error"]))),
        "divb_max": finite(np.nanmax(full["divb"])),
        "radiated_over_E0": finite(full["radiated"][-1] / full["total"][0]),
    }
    meta = {
        "id": job["id"], "kind": job["kind"], "twin": job["twin"], "stratum": job["stratum"],
        "status": res["status"], "reason": res["reason"], "error": res["error"],
        "setup": dataclasses.asdict(setup), "live": dataclasses.asdict(live),
        "swept": {**job["setup"], **job["live"]}, "t_end": job["t_end"],
        "derived": derived_numbers(sim), "summary": res["summary"],
        "wall": wall, "threads": threads, "code_version": code_version,
        "dt_save": DT_SAVE, "n_samples_full": len(full["t"]),
        "units": "mu_0 = 1; length = domain width; rho0 = p0 = T0 = 1 (Bennett peak values)",
    }
    runs = os.path.join(out_dir, "runs")
    tmp = os.path.join(runs, f"{job['id']}.part.npz")
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta)),
                        **{f"h_{k}": v.astype(np.float64) for k, v in h.items()})
    os.replace(tmp, os.path.join(runs, f"{job['id']}.npz"))
    return res


def worker_main(args):
    # stdout is the protocol channel: keep a private copy of it, and send
    # anything else that prints (numba warnings, ...) to the stderr log
    proto = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)

    def send(obj):
        proto.write(json.dumps(obj) + "\n")
        proto.flush()

    import numba
    numba.set_parallel_chunksize(4)
    from zpinch.params import SetupParams
    from zpinch.pinch import ZPinch
    warm = ZPinch(SetupParams(n_tracers=0))     # loads (or compiles) every kernel
    warm.step()
    send({"ready": True, "threads": numba.get_num_threads()})
    for line in sys.stdin:
        job = json.loads(line)
        send(run_job(job, args.dir, args.threads, args.code_version))


# =====================================================
# driver
# =====================================================

def _python():
    venv = os.path.join(V2, ".venv", "bin", "python")
    return venv if os.path.exists(venv) else sys.executable


def code_version():
    try:
        rev = subprocess.run(["git", "-C", V2, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", V2, "status", "--porcelain", "--", "zpinch"],
                               capture_output=True, text=True).stdout.strip()
        return rev + ("+dirty-zpinch" if dirty else "")
    except OSError:
        return "unknown"


class Worker:
    """One persistent worker process; jobs go in on stdin, results come back on stdout."""

    def __init__(self, out_dir, threads, slot, version):
        env = dict(os.environ, NUMBA_NUM_THREADS=str(threads), OMP_NUM_THREADS=str(threads),
                   NUMBA_THREADING_LAYER="omp", PYTHONPATH="", PYTHONUNBUFFERED="1")
        log = open(os.path.join(out_dir, "logs", f"worker-{slot}.log"), "a")
        self.proc = subprocess.Popen(
            [_python(), os.path.abspath(__file__), "_worker", out_dir,
             "--threads", str(threads), "--code-version", version],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1,
            env=env, cwd=V2, start_new_session=True)
        log.close()
        self.lines = queue.Queue()
        self.n_done = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)     # EOF: the process died

    def get(self, timeout):
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            return None
        return json.loads(line) if line else None

    def start(self, timeout=600):
        msg = self.get(timeout)
        return bool(msg and msg.get("ready"))

    def run(self, job, timeout):
        try:
            self.proc.stdin.write(json.dumps(job) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return None
        res = self.get(timeout)
        self.n_done += 1
        return res

    def kill(self):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.proc.wait()

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self.kill()


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def log(out_dir, msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(os.path.join(out_dir, "logs", "driver.log"), "a") as f:
        f.write(line + "\n")


def keep_performance(out_dir, every=300):
    """
    Laptops drop into the 'power-saver' profile on low battery, which halves
    the clock (measured 2026-10-19: 49 vs 20 ms/step). Every few minutes,
    switch back to 'performance' if that happened, and log it.
    """
    while True:
        try:
            prof = subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                                  text=True, timeout=10).stdout.strip()
            if prof and prof != "performance":
                subprocess.run(["powerprofilesctl", "set", "performance"], timeout=10)
                log(out_dir, f"power profile was '{prof}', set back to 'performance'")
        except (OSError, subprocess.SubprocessError):
            return
        time.sleep(every)


def cmd_plan(args):
    os.makedirs(args.dir, exist_ok=True)
    jobs_path = os.path.join(args.dir, "jobs.jsonl")
    if os.path.exists(jobs_path) and not args.force:
        sys.exit(f"{jobs_path} exists (use --force to replace the plan)")
    jobs = make_plan(args.n, args.res_check, args.seed, args.gap)
    with open(jobs_path, "w") as f:
        for job in jobs:
            f.write(json.dumps(job) + "\n")
    cfg = {"created": datetime.now().isoformat(timespec="seconds"), "n_base": args.n,
           "res_check": args.res_check, "seed": args.seed, "t_end": T_END, "dt_save": DT_SAVE,
           "grid_base": GRID_BASE, "grid_check": GRID_CHECK,
           "strata": {s[0]: s[1] for s in STRATA}, "code_version": code_version()}
    with open(os.path.join(args.dir, "sweep.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    counts = {}
    for job in jobs:
        counts[job["stratum"] if job["kind"] == "base" else "res48 twins"] = \
            counts.get(job["stratum"] if job["kind"] == "base" else "res48 twins", 0) + 1
    print(f"planned {len(jobs)} jobs in {args.dir}: {counts}")


def cmd_run(args):
    out = args.dir
    for sub in ("runs", "logs"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    jobs = read_jsonl(os.path.join(out, "jobs.jsonl"))
    if not jobs:
        sys.exit("no jobs.jsonl - run `plan` first")
    done = {r["id"] for r in read_jsonl(os.path.join(out, "index.jsonl"))}
    pending = [j for j in jobs if j["id"] not in done]
    if args.limit:
        pending = pending[:args.limit]
    stop_file = os.path.join(out, "STOP")
    if os.path.exists(stop_file):
        os.remove(stop_file)
    deadline = time.time() + args.hours * 3600 if args.hours else math.inf
    version = code_version()
    log(out, f"run: {len(pending)} pending of {len(jobs)} ({len(done)} done), "
             f"{args.jobs} jobs x {args.threads} threads, "
             f"deadline {datetime.fromtimestamp(deadline):%H:%M} " if args.hours else
             f"run: {len(pending)} pending, {args.jobs} x {args.threads}, no deadline")

    lock = threading.Lock()
    state = {"next": 0, "n_done": 0, "t0": time.time(), "stopping": False}
    workers = {}
    retried = set()     # jobs whose worker died once already (shared by all slots)

    def next_job():
        with lock:
            if state["stopping"] or time.time() > deadline or os.path.exists(stop_file):
                return None
            if state["next"] >= len(pending):
                return None
            job = pending[state["next"]]
            state["next"] += 1
            return job

    def record(res):
        with lock:
            with open(os.path.join(out, "index.jsonl"), "a") as f:
                f.write(json.dumps(res) + "\n")
            state["n_done"] += 1
            el = time.time() - state["t0"]
            rate = state["n_done"] / el * 3600
            s = res.get("summary") or {}
            log(out, f"[{state['n_done']}/{len(pending)}] {res['id']} {res['stratum']:<11} "
                     f"{res['status']}/{res['reason']:<12} t={s.get('t_final') or 0:4.2f} "
                     f"{res.get('wall', 0):6.1f}s  m1max={s.get('m1_max') or 0:.2f}  "
                     f"| {rate:.0f}/h")

    def slot_loop(slot):
        w = None
        while True:
            job = next_job()
            if job is None:
                break
            if w is None or w.n_done >= WORKER_RECYCLE:
                if w is not None:
                    w.close()
                w = Worker(out, args.threads, slot, version)
                workers[slot] = w
                if not w.start():
                    log(out, f"slot {slot}: worker failed to start, see logs/worker-{slot}.log")
                    w.kill()
                    w = None
                    with lock:          # give the job back and retire this slot
                        pending.append(job)
                    return
            cap = WALL_CAP_BASE * COST_FACTOR[job["setup"]["resolution"]] * 2.0 / args.threads
            res = w.run(job, timeout=1.5 * cap + 120)
            if res is None:
                # worker crashed (segfault) or hung past its own wall cap
                crashed = w.proc.poll() is not None
                w.kill()
                w = None
                with lock:
                    first = job["id"] not in retried
                    retried.add(job["id"])
                if first:
                    log(out, f"slot {slot}: worker {'crashed' if crashed else 'hung'} on "
                             f"{job['id']}, retrying once")
                    with lock:
                        pending.append(job)
                    continue
                res = {"id": job["id"], "kind": job["kind"], "twin": job["twin"],
                       "stratum": job["stratum"], "status": "failed",
                       "reason": "worker_crash" if crashed else "worker_hung", "error": None,
                       "params": {**job["setup"], **job["live"]}}
            record(res)
        if w is not None:
            w.close()

    def on_signal(signum, frame):
        log(out, f"signal {signum}: killing workers (unfinished runs are re-done on resume)")
        state["stopping"] = True
        for w in list(workers.values()):
            w.kill()
        os._exit(1)

    if args.keep_performance:
        threading.Thread(target=keep_performance, args=(out,), daemon=True).start()
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    threads = [threading.Thread(target=slot_loop, args=(i,)) for i in range(args.jobs)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    why = ("stop file" if os.path.exists(stop_file) else
           "deadline" if time.time() > deadline else "all jobs done")
    log(out, f"run finished ({why}): {state['n_done']} runs in "
             f"{(time.time() - state['t0']) / 3600:.2f} h")


def cmd_bench(args):
    """Throughput of J jobs x T threads: J identical default runs at once."""
    out = args.dir
    for sub in ("runs", "logs"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    version = code_version()
    job = {"id": "bench", "kind": "bench", "twin": None, "stratum": "bench",
           "setup": {"resolution": GRID_BASE}, "live": {}, "t_end": args.t_end}
    results = []
    for cfg in args.configs:
        J, T = (int(x) for x in cfg.split("x"))
        workers = [Worker(out, T, f"bench{i}", version) for i in range(J)]
        if not all(w.start() for w in workers):
            sys.exit("bench worker failed to start")
        t0 = time.time()
        res = [None] * J

        def go(i):
            res[i] = workers[i].run({**job, "id": f"bench-{cfg}-{i}"}, timeout=1800)

        ths = [threading.Thread(target=go, args=(i,)) for i in range(J)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        wall = time.time() - t0
        for w in workers:
            w.close()
        per_run = float(np.mean([r["wall"] for r in res if r]))
        rate = J / wall * 3600 * (T_END / args.t_end)    # in full t = 3 runs per hour
        results.append({"config": cfg, "jobs": J, "threads": T, "wall": wall,
                        "per_run": per_run, "runs_per_hour_t3": rate})
        print(f"{cfg:>5}: {J} runs to t={args.t_end} in {wall:6.1f} s (each {per_run:5.1f} s) "
              f"-> ~{rate:5.0f} full runs/h", flush=True)
        for f in os.listdir(os.path.join(out, "runs")):
            if f.startswith("bench"):
                os.remove(os.path.join(out, "runs", f))
    with open(os.path.join(out, "bench.json"), "w") as f:
        json.dump(results, f, indent=2)
    best = max(results, key=lambda r: r["runs_per_hour_t3"])
    print(f"best: {best['config']} (~{best['runs_per_hour_t3']:.0f} full runs/h before early stops)")


def cmd_status(args):
    jobs = read_jsonl(os.path.join(args.dir, "jobs.jsonl"))
    idx = read_jsonl(os.path.join(args.dir, "index.jsonl"))
    print(f"{len(idx)} of {len(jobs)} planned jobs finished")
    for field in ("status", "reason", "stratum", "kind"):
        counts = {}
        for r in idx:
            key = r.get(field)
            counts[key] = counts.get(key, 0) + 1
        print(f"  {field:8}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=str)))
    walls = [r["wall"] for r in idx if r.get("wall") and r["kind"] == "base"]
    if walls:
        print(f"  wall per 32^3 run: median {np.median(walls):.1f} s, max {max(walls):.1f} s")
    errs = [r["summary"]["energy_error_max"] for r in idx
            if r.get("summary") and r["summary"].get("energy_error_max") is not None]
    if errs:
        print(f"  |energy budget error| max over runs: median {np.median(errs):.1e}, "
              f"worst {max(errs):.1e}")
    logf = os.path.join(args.dir, "logs", "driver.log")
    if os.path.exists(logf):
        with open(logf) as f:
            tail = f.readlines()[-3:]
        print("  last log lines:\n    " + "    ".join(tail), end="")


def cmd_stop(args):
    open(os.path.join(args.dir, "STOP"), "w").close()
    print("STOP file written: running jobs finish, no new ones start (resume with `run`)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("dir")
    p.add_argument("--n", type=int, default=8000, help="base (32^3) runs to plan")
    p.add_argument("--res-check", type=int, default=100, help="48^3 twins to plan")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--gap", type=int, default=25, help="one 48^3 twin after every GAP base runs")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("dir")
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--hours", type=float, default=0.0, help="stop starting new runs after this")
    p.add_argument("--limit", type=int, default=0, help="only do the next N pending jobs")
    p.add_argument("--keep-performance", action="store_true",
                   help="keep the laptop power profile on 'performance' (powerprofilesctl)")
    p = sub.add_parser("bench")
    p.add_argument("dir")
    p.add_argument("--t-end", type=float, default=1.0)
    p.add_argument("--configs", nargs="*", default=["1x12", "2x6", "3x4", "4x3", "6x2", "12x1"])
    p = sub.add_parser("status")
    p.add_argument("dir")
    p = sub.add_parser("stop")
    p.add_argument("dir")
    p = sub.add_parser("_worker")
    p.add_argument("dir")
    p.add_argument("--threads", type=int, required=True)
    p.add_argument("--code-version", default="unknown")
    args = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "bench": cmd_bench, "status": cmd_status,
     "stop": cmd_stop, "_worker": worker_main}[args.cmd](args)


if __name__ == "__main__":
    main()
