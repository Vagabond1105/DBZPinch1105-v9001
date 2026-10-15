# Z-Pinch MHD v2

Interactive 3D resistive-MHD simulation of a Z-pinch plasma column: a Bennett
equilibrium driven by an external circuit, with live controls, GPU volume
rendering, tracer particles and exact energy bookkeeping.

Full documentation (Obsidian notes) lives in `../docs/`:
`01 - Vision`, `02 - V1 and Why It Failed`, `03 - V2 Changes and Fixes`, `04 - V2 Complete Guide`.

## Run

```bash
./run.sh                    # GUI
./run.sh --headless --t-end 2 --set current=1.5 axial_field=0.8 --export run.zip
./run.sh --headless --t-end 3 --preset "Saturated kink (Bz = 0.6)"
./test.sh                   # physics validation suite (27 tests, ~20-30 s)
```

First launch compiles the numba kernels (~20-40 s, cached afterwards).

## Setup from scratch

```bash
python3 -m venv .venv            # needs python3-venv; see docs if ensurepip is missing
.venv/bin/python -m pip install -r requirements.txt
```

## Layout

```
main.py                 entry point (GUI / --headless)
zpinch/constants.py     units, variable slots, floors, CFL, BC codes
zpinch/kernels.py       numba kernels: HLLD/HLL, PLM, GLM, resistive+viscous fluxes, diagnostics, tracers
zpinch/solver.py        generic 3D MHD solver (SSP-RK2, ghost cells, dt, energy/mass budget)
zpinch/pinch.py         Z-pinch problem: Bennett equilibrium, drive circuit, tracers, diagnostics
zpinch/params.py        setup + live parameters (metadata drives the GUI)
zpinch/diagnostics.py   plots + zip export
zpinch/gui/             Qt window, vispy 3D view, controls, physics worker process
tests/                  Sod, Alfven wave, diffusion, energy budget, equilibrium, kink growth
examples/               toy_advection.py, toy_muscl.py - tiny NumPy demos used in the docs
```
