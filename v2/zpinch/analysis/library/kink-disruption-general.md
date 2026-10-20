---
id: kink-disruption-general
class: kink_disruption
title: Kink -> disruption
reviewed: data-checked
---
## What happened
The column bent into a corkscrew (a helical kink) that kept growing until it tore the column apart. The kink passed {nonlinear:g} radii at t = {t_nonlinear:.2f}, and by t = {t_mixed:.2f} the plasma had spread most of the way to the wall ({wall_a:.1f} radii from the axis). The flow peaked at {kinetic_max_pct:.0f} % of the starting energy, at t = {kinetic_t_max:.2f}.

## Why
A Z-pinch is held in by the magnetic field its own current wraps around it. If the column bends, the wrapped field lines crowd together on the inside of the bend and spread apart on the outside, so the inside is squeezed harder and the bend deepens: the kink instability. An axial field B_z resists bending, but only if it is strong enough. The Kruskal-Shafranov rule says a helix that winds n times along the column grows when n q < 1, and the helix the seed started here had n q = {nq_seed:.2f}. Once the kink was large, the column broke up. Over the whole run, as % of the starting energy: magnetic {e_magnetic:+.0f}, put in by the circuit {e_injected:+.0f}, heat {e_thermal:+.0f}, flow {e_kinetic:+.0f}.

## Try next
Add an axial field. B_z = {bz_saturate:.2f} (n q = {nq_saturate:.2f}) should turn this into a saturated kink, and B_z = {bz_stable:.2f} (n q = {nq_stable:.2f}) should keep the column straight.
