---
id: quiescent-marginal
class: quiescent
title: Quiet, just above the Kruskal-Shafranov line
regime: nq_seed 1.0..1.5
compare: nq_seed 1.0..1.5; gravity 0..0.3; cooling 0..0.3
example: r00396
reviewed: data-checked
---
## What happened
The column stayed close to its starting state: the kink peaked at {m1_peak:.2f} radii and necking at {m0_peak:.2f}, both about the size of the starting nudge.

## Why
The helix the seed started (n = {seed_n} turns along the column) had n q = {nq_seed:.2f}, just above the Kruskal-Shafranov limit of 1, so the edge criterion says it is stable. But this is the transition band. In a Bennett column q falls to half its edge value on the axis ({q_axis:.2f} here), so the inner part of the column sits below the line. Whether a small kink grows there depends on details: dissipation, the drive, the grid. In the overnight sweep, the {regime_runs} runs in this band (1 to 1.5, without strong gravity or cooling) ended as: {regime_mix}. This one stayed quiet.

## Try next
This band is the place to experiment: rerun with another random seed, or on the Fast (48 x 48 x 72) grid, and see whether a small kink appears. For a clear saturated kink, lower B_z to {bz_saturate:.2f} (n q = {nq_saturate:.2f}).
