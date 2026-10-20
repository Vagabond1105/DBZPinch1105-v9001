---
id: saturated-kink-above-limit
class: saturated_kink
title: Small kink above the Kruskal-Shafranov line
regime: nq_seed 1.0..inf
compare: nq_seed 1.0..inf; gravity 0..0.3; cooling 0..0.3
example: r00868
reviewed: data-checked
---
## What happened
A small corkscrew grew and stopped at about {m1_sat:.2f} radii (t = {t_sat:.2f}); the column stayed whole. The kink peaked at {m1_peak:.2f} radii and ended at {m1_final:.2f}.

## Why
The helix the seed started had n q = {nq_seed:.2f}, above the Kruskal-Shafranov limit of 1, so the simple edge criterion says it should be stable. A kink can grow anyway, because q is not the same everywhere. In a Bennett column q falls to half its edge value on the axis ({q_axis:.2f} here), so the inner part of the column sits below the line and can still kink. {helix} The kink stays small, because only part of the column is unstable. In the overnight sweep, the {regime_runs} runs above the line (little gravity or cooling) ended as: {regime_mix}.

## Try next
Raise B_z to {bz_stable:.2f} (n q = {nq_stable:.2f}) to suppress it, or rerun on the Fast (48 x 48 x 72) grid: this close to the line, the grid can decide whether the small kink grows.
