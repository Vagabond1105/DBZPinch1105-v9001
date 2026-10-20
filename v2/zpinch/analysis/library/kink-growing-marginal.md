---
id: kink-growing-marginal
class: kink_growing
title: Kink still growing, close to the Kruskal-Shafranov line
regime: nq_seed 0.5..1.5
compare: nq_seed 0.5..1.5; gravity 0..0.3; cooling 0..0.3
preset: Saturated kink (Bz = 0.6)
reviewed: data-checked
---
## What happened
When you analysed, a corkscrew kink was still growing exponentially: {m1_final:.2f} radii at t = {t_final:.2f}, growing at {late_rate:.2f} per time unit. The outcome is not decided yet.

## Why
The helix the seed started had n q = {nq_seed:.2f}, close to the Kruskal-Shafranov limit of 1. As the helix deepens it stretches the axial field lines (B_z = {axial_field:.2f}), so the growth will most likely stop and leave a bent column. In the overnight sweep, the {regime_runs} runs like this (n q from 0.5 to 1.5, little gravity or cooling) ended at t = 3 as: {regime_mix}.

## Try next
Resume the run and analyse again near t = 3; expect the kink amplitude to level off.
