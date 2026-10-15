"""
Toy example 2 - what a slope limiter buys you (the idea inside v2's solver).

Same moving block as toy_advection.py, now with second-order accuracy:
each cell is drawn as a sloped line instead of a flat step, and time is
advanced with two-stage Runge-Kutta, exactly like v2 (in 1D, one variable).

After 200 steps at CFL 0.5 the block has gone once around the ring, so
the exact answer is the starting shape.

Run:  ../.venv/bin/python toy_muscl.py
"""
import numpy as np

N = 100
dx = 1.0 / N
c = 1.0
x = (np.arange(N) + 0.5) * dx
q0 = np.where((x > 0.2) & (x < 0.4), 1.0, 0.0)


def vanleer(dl, dr):
    """Slope limiter: harmonic mean of the two one-sided slopes, 0 at peaks/valleys."""
    return np.where(dl * dr > 0, 2 * dl * dr / (dl + dr + 1e-300), 0.0)


def rate_of_change(q, limited):
    dl = q - np.roll(q, 1)                 # slope looking left
    dr = np.roll(q, -1) - q                # slope looking right
    slope = vanleer(dl, dr) if limited else 0.5 * (dl + dr)
    q_face = q + 0.5 * slope               # value at the right face (from the upwind cell)
    flux = c * q_face
    return -(flux - np.roll(flux, 1)) / dx


def run(limited, cfl=0.5, steps=200):
    dt = cfl * dx / c
    q = q0.copy()
    for _ in range(steps):
        q1 = q + dt * rate_of_change(q, limited)                     # RK2 stage 1 (predict)
        q = 0.5 * q + 0.5 * (q1 + dt * rate_of_change(q1, limited))  # RK2 stage 2 (correct)
    return q


def first_order(cfl=0.5, steps=200):
    dt = cfl * dx / c
    q = q0.copy()
    for _ in range(steps):
        q = q - dt / dx * (c * q - np.roll(c * q, 1))
    return q


for name, q in [("1st-order upwind", first_order()),
                ("2nd order, NO limiter", run(False)),
                ("2nd order, van Leer limiter", run(True))]:
    err = np.abs(q - q0).sum() * dx
    print(f"{name:28s} max={q.max():.4f}  min={q.min():+.4f}  error={err:.4f}  total={q.sum() * dx:.15f}")
