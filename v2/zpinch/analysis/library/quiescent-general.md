---
id: quiescent-general
class: quiescent
title: Quiescent column
reviewed: data-checked
---
## What happened
Nothing grew. The largest kink (the column bending into a corkscrew) was {m1_peak:.2f} radii and the largest necking {m0_peak:.2f} radii, about the size of the small random nudge every run starts with. At t = {t_final:.2f} the column was still {shift_final:.2f} radii from the axis and its core density was {core_density_final:.2f} times its starting value.

## Why
The column is held together by the magnetic field its own current wraps around it, balanced against the plasma's pressure (the Bennett equilibrium). That balance is usually unstable: if the column bends, the wrapped field lines crowd together on the inside of the bend and squeeze it further (the kink). An axial field B_z resists bending, because bending stretches its field lines. The Kruskal-Shafranov rule says a helix that winds n times along the column can grow only if n q < 1, where the safety factor q compares the twist of the field lines with the length of the column. Here the helix the seed started had n q = {nq_seed:.2f}. The slow spreading that remains is diffusion: the resistivity and viscosity you set, plus the grid's own. In the overnight sweep, {class_runs} of the {sweep_runs} runs stayed quiet like this.

## Try next
Set the axial field to B_z = {bz_saturate:.2f} (n q = {nq_saturate:.2f}) and the same column should bend into a saturated kink; set it to 0 for a pure Z-pinch, which disrupts.
