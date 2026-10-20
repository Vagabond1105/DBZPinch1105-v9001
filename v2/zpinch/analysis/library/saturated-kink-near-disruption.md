---
id: saturated-kink-near-disruption
class: saturated_kink
title: Saturated kink that nearly disrupted
regime: nq_seed 0..0.5
compare: nq_seed 0..0.5; gravity 0..0.3; cooling 0..0.3
example: r00835
reviewed: data-checked
---
## What happened
The column bent into a large corkscrew, peaking at {m1_peak:.2f} radii, then stopped growing and survived ({m1_final:.2f} radii at the end). Kinks this unstable usually tear the column apart; this one did not.

## Why
The helix the seed started had n q = {nq_seed:.2f}, well below the Kruskal-Shafranov limit of 1, so the axial field (B_z = {axial_field:.2f}) is weak compared with the wrapped field. Columns this far below the line usually disrupt: in the overnight sweep, the {regime_runs} runs with n q below 0.5 (little gravity or cooling) ended as: {regime_mix}. Here the weak axial field held just enough. As the helix deepened it stretched the axial field lines, and growth stopped before the column was torn. This run sits near the boundary between a saturated kink and a disruption, so a small change (another random seed, a finer grid) could tip it.

## Try next
Raise B_z to {bz_saturate:.2f} (n q = {nq_saturate:.2f}) for a comfortably saturated kink, or keep these settings with another random seed to see how often it disrupts instead.
