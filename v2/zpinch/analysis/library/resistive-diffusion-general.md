---
id: resistive-diffusion-general
class: resistive_diffusion
title: Resistive diffusion
compare: resistivity 0.0035..inf; nq_seed 1.0..inf; gravity 0..0.3; cooling 0..0.3
example: r00591
reviewed: data-checked
---
## What happened
Nothing went unstable (the kink peaked at {m1_peak:.2f} radii), but the column did not stay put: it spread out and heated. Its core density fell to {core_density_final:.2f} times the start, and its heat rose by {d_thermal_pct:.0f} % of the starting energy.

## Why
With resistivity eta = {resistivity:.2g}, magnetic field lines are not perfectly frozen into the plasma: they slip through it. The current that holds the column together spreads out on the resistive time a^2 / eta = {t_resistive:.2f} time units, shorter than the run ({t_final:.2f}). As the current spreads, the squeeze weakens and the column expands. The current's resistance turns field energy into heat (Ohmic heating), which is where the extra heat came from. Over the run the magnetic energy changed by {e_magnetic:+.0f} % of the starting energy, and the circuit's net input was {e_injected:+.0f} %. The Lundquist number S = {lundquist:.0f} measures how ideal the plasma is (large S: field lines stay frozen in); laboratory plasmas usually have a far larger S. The axial field (n q = {nq_seed:.2f}) kept a kink from growing first. In the overnight sweep, the {regime_runs} runs with eta of at least 0.0035 and n q of at least 1 (little gravity or cooling) ended as: {regime_mix}.

## Try next
Lower eta to 0.0003 (the default) and the column should stay compact. The slow spreading that remains is then mostly the grid's own numerical diffusion.
