---
id: radiative-collapse-general
class: radiative_collapse
title: Radiative collapse
compare: cooling 0.9..inf; nq_seed 0.5..inf
example: r00235
reviewed: data-checked
---
## What happened
The core cooled and collapsed. Radiation drained its heat until the core temperature fell to {core_temp_min:.2f} times its start, and the cold core was squeezed to {core_density_max:.2f} times its starting density. By the end, radiation had carried away {radiated_pct:.0f} % of the starting energy.

## Why
The plasma radiates (bremsstrahlung, P = C rho^2 sqrt(T), here C = {cooling:.2f}), so it loses its heat on a cooling time of about {t_cooling:.2f} time units, shorter than the run. Cooler plasma has less pressure, so the magnetic field squeezes it harder. Squeezed plasma is denser, and denser plasma radiates faster, because P grows as the density squared. That runaway is radiative collapse: the core crossed the line (below {collapse_t:g} of its starting temperature and {collapse_rho:g} times denser) at t = {t_hit:.2f}. Real pinches have the same competition between Ohmic heating and radiation; the current at which they balance is known as the Pease-Braginskii current. The column also has to survive long enough to collapse, and your axial field did that: the helix the seed started had n q = {nq_seed:.2f}. In the overnight sweep, the {regime_runs} runs with strong cooling (C of at least 0.9) and n q of at least 0.5 ended as: {regime_mix}. With n q below 0.5 the kink usually tears the column apart before it can collapse.

## Try next
Halve the cooling (C = {cooling_half:.2f}) to see the core hold its heat, or turn on Spitzer resistivity: cold plasma then resists the current more, so Ohmic heating rises where the plasma cools and works against the collapse.
