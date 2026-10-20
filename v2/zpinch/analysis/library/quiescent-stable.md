---
id: quiescent-stable
class: quiescent
title: Kink-stable screw pinch
regime: nq_seed 1.5..inf
compare: nq_seed 1.5..inf; gravity 0..0.3; cooling 0..0.3
example: r00533
preset: Stable screw pinch
reviewed: data-checked
---
## What happened
The column stayed straight and round for the whole run: the kink never got past {m1_peak:.2f} radii and necking never past {m0_peak:.2f}. This is the textbook stable screw pinch, a current along the column plus a strong axial field (B_z = {axial_field:.2f}). The only change was slow spreading: the core density ended at {core_density_final:.2f} times its start.

## Why
The seed tried to start a helix that winds {seed_n} times along the column. With your axial field the safety factor at the column's edge is q = {q_a:.2f}, so that helix has n q = {nq_seed:.2f}, well above the Kruskal-Shafranov limit of 1. To bend into it, the column would have to stretch the axial field lines by more than the bend releases from the wrapped field, so it does not bend. Inside the column q is lower: for the Bennett profile it falls to half the edge value on the axis ({q_axis:.2f} here). That is one reason the real stability line sits a little above n q = 1. In the overnight sweep, the {regime_runs} runs in this band without strong gravity or cooling ended as: {regime_mix}. The spreading is diffusion (resistivity eta = {resistivity:.2g}, plus the grid's own).

## Try next
Lower B_z to {bz_saturate:.2f} (n q = {nq_saturate:.2f}) to watch the same column develop a saturated kink, or raise the resistivity to {eta_diffuse:.3g} to see the column diffuse away instead.
