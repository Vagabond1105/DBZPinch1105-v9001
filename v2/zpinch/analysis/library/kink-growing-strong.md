---
id: kink-growing-strong
class: kink_growing
title: Kink still growing, far below the Kruskal-Shafranov line
regime: nq_seed 0..0.5
compare: nq_seed 0..0.5; gravity 0..0.3; cooling 0..0.3
preset: Pure Z-pinch: kink -> disruption
reviewed: data-checked
---
## What happened
When you analysed, a corkscrew kink was still growing exponentially: {m1_final:.2f} radii at t = {t_final:.2f}, growing at {late_rate:.2f} per time unit. The outcome is not decided yet.

## Why
The helix the seed started had n q = {nq_seed:.2f}, far below the Kruskal-Shafranov limit of 1, so the axial field (B_z = {axial_field:.2f}) can do little to stop it. Kinks this unstable usually tear the column apart soon after they pass about {nonlinear:g} radii. In the overnight sweep, the {regime_runs} runs like this (n q below 0.5, little gravity or cooling) ended at t = 3 as: {regime_mix}.

## Try next
Resume and watch the Pinch column plot: a disruption shows as the radius shooting up soon after the kink passes {nonlinear:g} radii.
