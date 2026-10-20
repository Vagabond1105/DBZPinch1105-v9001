---
id: sausage-general
class: sausage
title: Sausage-dominated column
reviewed: data-checked
---
## What happened
The column necked like a string of sausages: necking (m = 0) reached {m0_peak:.2f} radii, more than the kink ({m1_peak:.2f}) or any sideways shift ({shift_peak:.2f}).

## Why
At a neck the same current flows through a narrower column, so the wrapped field is stronger there and squeezes the neck further: the sausage instability. An axial field resists it, because squeezing the column also compresses its axial field lines. Kadomtsev's criterion says the edge is stable when B_z^2 > B_theta^2 / 2, a margin of {kadomtsev_margin:.2f} here (above 1 is stable). If the margin is above 1, this is probably not the ideal sausage: cold, dense blobs condensing along a cooling column look the same to this diagnostic. In this simulator the sausage is rare, because it grows slowly in a Bennett column and the kink usually wins. It named {class_runs} of the {sweep_runs} overnight runs.

## Try next
Set the seed perturbation to Sausage (m = 0) to start only necking, then raise B_z to 1.0 to watch it decay instead (tutorial T2).
