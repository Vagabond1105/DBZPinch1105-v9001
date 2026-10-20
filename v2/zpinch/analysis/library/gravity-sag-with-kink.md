---
id: gravity-sag-with-kink
class: gravity_sag
title: Gravity sag with a small kink riding on it
regime: m1_peak 0.1..inf
compare: gravity 0.5..inf; nq_seed 0.5..1.5
example: r00982
reviewed: data-checked
---
## What happened
The whole column fell sideways toward -y, {shift_peak:.2f} radii off the axis by t = {shift_t_peak:.2f}. A small corkscrew also grew on top of the sag (kink peak {m1_peak:.2f} radii). The sag was the bigger motion, so it names the run.

## Why
Gravity (g = {gravity:.2f}) pulls on the plasma's mass. The magnetic field anchored at the walls holds the column back: as it moves toward the lower wall, the field between them is squeezed and pushes back. The kink is a separate effect. The helix the seed started had n q = {nq_seed:.2f}, close enough to the Kruskal-Shafranov line of 1 that a small kink can grow and then stop. The sag (axial wavenumber n = 0, the whole column moving at once) and the kink (a bend that changes along the column) are measured separately, so both show up. In the overnight sweep, the {regime_runs} runs with g of at least 0.5 and n q from 0.5 to 1.5 ended as: {regime_mix}.

## Try next
Turn gravity off to see the kink alone, or raise B_z to {bz_stable:.2f} (n q = {nq_stable:.2f}) so that only the sag remains.
