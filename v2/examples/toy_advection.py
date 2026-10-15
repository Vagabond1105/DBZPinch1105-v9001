"""
Toy example 1 - why v1 blew up, and what a CFL condition is.

A block of "stuff" (think: dye in a river) moves to the right at speed
c = 1 along a ring of 100 cells. The exact answer is simple: the block
just slides along unchanged. We try two update rules:

  FTCS   (forward in time, central in space) - what v1 used
  upwind (finite volume, take the flux from the cell the flow comes from)

Run:  ../.venv/bin/python toy_advection.py
"""
import numpy as np

N = 100                        # number of cells
dx = 1.0 / N                   # cell width
c = 1.0                        # speed of the flow
x = (np.arange(N) + 0.5) * dx  # cell centres
q0 = np.where((x > 0.2) & (x < 0.4), 1.0, 0.0)   # the block: height 1, width 0.2


def run(scheme, cfl, steps):
    dt = cfl * dx / c          # CFL number = how many cells the flow crosses per step
    q = q0.copy()
    for _ in range(steps):
        if scheme == "ftcs":
            # rate of change from the average slope of BOTH neighbours
            q = q - c * dt / (2 * dx) * (np.roll(q, -1) - np.roll(q, 1))
        else:
            # finite volume: flux through each cell's right face, taken from
            # the upwind cell; each cell gains what enters on the left and
            # loses what leaves on the right
            flux = c * q
            q = q - dt / dx * (flux - np.roll(flux, 1))
    return q


for scheme, cfl, steps in [("ftcs", 0.5, 20), ("ftcs", 0.5, 100), ("ftcs", 0.5, 200),
                           ("ftcs", 0.05, 2000),
                           ("upwind", 0.5, 100), ("upwind", 0.5, 200),
                           ("upwind", 1.5, 20), ("upwind", 1.5, 40)]:
    q = run(scheme, cfl, steps)
    print(f"{scheme:6s} CFL={cfl:<4} steps={steps:4d}: max={q.max():10.4g} "
          f"min={q.min():10.4g} total={q.sum() * dx:.15f}")
print("exact answer: max = 1, min = 0, total = 0.2 forever")
