"""
Z-Pinch MHD v2 - entry point.

    python main.py                         # interactive GUI
    python main.py --headless --t-end 2    # run without GUI, print diagnostics
    python main.py --headless --t-end 3 --preset "Saturated kink (Bz = 0.6)"
    python main.py --headless --t-end 2 --export run.zip --set current=1.5 resolution="Medium (64 x 64 x 96)"
    python main.py --headless --t-end 3 --analyse      # then label and explain the run (v3 phase 1)
    python main.py --headless --t-end 3 --report run.html   # ... and save the HTML report (phase 5)
"""

import argparse
import dataclasses
import os
import sys
import time
import warnings

# numba: use OpenMP threads (falls back automatically if unavailable)
os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")
warnings.filterwarnings("ignore", message=".*TBB.*")


def ensure_own_venv():
    """
    If launched by an interpreter that lacks the dependencies (e.g. an IDE
    still pointing at v1/.venv), re-exec this script with v2/.venv instead.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    venv = os.path.join(here, ".venv")
    venv_python = os.path.join(venv, "bin", "python")
    if os.path.realpath(sys.prefix) == os.path.realpath(venv) or not os.path.exists(venv_python):
        return
    try:
        import numba, vispy, PyQt5, OpenGL, matplotlib  # noqa: F401
    except ImportError as exc:
        print(f"[main.py] {exc.name} is missing from {sys.executable};\n"
              f"[main.py] relaunching with {venv_python}", file=sys.stderr, flush=True)
        os.execv(venv_python, [venv_python, os.path.abspath(__file__), *sys.argv[1:]])


def parse_assignments(items, setup, live):
    for item in items or []:
        key, _, value = item.partition("=")
        target = setup if hasattr(setup, key) else live if hasattr(live, key) else None
        if target is None:
            sys.exit(f"unknown parameter '{key}'")
        current = getattr(target, key)
        if isinstance(current, bool):
            value = value.lower() in ("1", "true", "yes", "on")
        else:
            value = type(current)(value)
        setattr(target, key, value)


def headless(args):
    from zpinch.params import SetupParams, LiveParams, PRESETS, apply_preset
    from zpinch.pinch import ZPinch

    import numba
    numba.set_parallel_chunksize(4)
    setup, live = SetupParams(), LiveParams()
    if args.preset:
        if args.preset not in PRESETS:
            sys.exit("unknown preset; choose from: " + ", ".join(repr(p) for p in PRESETS))
        apply_preset(args.preset, setup, live)
    parse_assignments(args.set, setup, live)
    print("setup:", dataclasses.asdict(setup))
    print("live: ", dataclasses.asdict(live))
    t_build = time.perf_counter()
    sim = ZPinch(setup, live)
    sv = sim.solver
    print(f"grid {sv.nx}x{sv.ny}x{sv.nz}, I_Bennett = {sim.I_bennett:.4f}, "
          f"t_Alfven = {sim.t_alfven:.4f}  (setup {time.perf_counter() - t_build:.1f} s incl. JIT)")
    t0 = time.perf_counter()
    next_print = 0.0
    while sim.t < args.t_end:
        sim.step()
        if sim.t >= next_print or sim.t >= args.t_end:
            L = sim.latest()
            print(f"t={L['t']:7.3f} step={sv.n_steps:6d} dt={L['dt']:.2e}  "
                  f"m0={L['m0']:.2e} m1={L['m1']:.2e} shift={L['shift']:.2e}  R/a={L['radius'] / sim.a:.3f} "
                  f"Tcore={L['core_temperature']:.3f}  I={L['current_measured']:.3f}  "
                  f"Bennett={L['bennett_ratio']:.3f}  E_err={L['energy_error']:+.1e} "
                  f"divB={L['divb']:.1e}", flush=True)
            next_print += args.print_every
    wall = time.perf_counter() - t0
    print(f"{sv.n_steps} steps in {wall:.1f} s ({1000 * wall / max(sv.n_steps, 1):.1f} ms/step)")
    if args.analyse or args.report:
        from zpinch.analysis import features as FE
        from zpinch.analysis.report import bundle
        b = bundle(*FE.run_from_sim(sim))
        if args.analyse:
            print("\n" + b["text"])
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(b["html"])
            print("report", args.report)
    if args.export:
        from zpinch.diagnostics import export_zip
        export_zip(sim, args.export)
        print("exported", args.export)


def main():
    ensure_own_venv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headless", action="store_true", help="run without the GUI")
    ap.add_argument("--t-end", type=float, default=2.0, help="end time for --headless")
    ap.add_argument("--print-every", type=float, default=0.1)
    ap.add_argument("--export", help="zip file to export to after a headless run")
    ap.add_argument("--analyse", action="store_true",
                    help="after a headless run, print the outcome class, timeline and causes")
    ap.add_argument("--report", metavar="PATH.html",
                    help="after a headless run, save the standalone HTML report (write-up, figures, data)")
    ap.add_argument("--preset", help="start from a named preset (zpinch/params.py PRESETS); "
                                      "--set overrides are applied on top")
    ap.add_argument("--set", nargs="*", metavar="NAME=VALUE",
                    help="override parameters (see zpinch/params.py)")
    args = ap.parse_args()
    if args.headless:
        headless(args)
    else:
        from zpinch.gui.app import run
        run()


if __name__ == "__main__":
    main()
