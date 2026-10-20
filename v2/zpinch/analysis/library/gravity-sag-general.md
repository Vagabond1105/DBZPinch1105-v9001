---
id: gravity-sag-general
class: gravity_sag
title: Gravity sag
compare: gravity 0.5..inf; nq_seed 1.0..inf
example: r00141
reviewed: data-checked
---
## What happened
The whole column fell sideways, toward -y, without bending: it moved {shift_peak:.2f} radii off the axis by t = {shift_t_peak:.2f} and ended {shift_final:.2f} radii off. No kink grew past {m1_peak:.2f} radii.

## Why
Gravity (g = {gravity:.2f}) pulls on the plasma's mass, and the column's own field moves with it. What holds it back is the magnetic field anchored at the walls: as the column moves toward the lower wall, the field between them is squeezed and pushes back, so the column stops and can swing back. This is a bulk shift (the whole column moves at once; axial wavenumber n = 0), not an instability growing from a small nudge, and the kink diagnostic does not count it. The energy came from the gravitational store ({e_potential:+.1f} % of the starting energy over the run). In the overnight sweep, the {regime_runs} runs with g of at least 0.5 and a kink-stable axial field (n q of at least 1) ended as: {regime_mix}.

## Try next
Turn gravity off to see what the column does on its own, or keep it on with B_z = 0 to watch a kink take over from the sag.
