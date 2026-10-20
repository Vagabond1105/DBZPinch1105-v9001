# Z-Pinch MHD

An interactive 3D magnetohydrodynamics simulator of a Z-pinch plasma column that labels, explains and
forecasts each run: physics rules say what happened, a curated library writes it up in plain language, and
two models trained on an overnight sweep of 2902 simulations cross-check the label and predict the outcome
before the run starts (94.3 % on held-out runs, against 67.6 % for the Kruskal-Shafranov number alone).

![GUI with the run report](v2/screenshots/gui_report.png)

- `v2/` is the current program (v2 solver and GUI, plus the v3 analysis). Start with
  [v2/README.md](v2/README.md) for results, screenshots and how to run it.
- `docs/` holds the notes. [06 - V3 Technical Overview](docs/06%20-%20V3%20Technical%20Overview.md)
  explains all of it from zero.
- `v1/` is the first attempt, kept for the record (see `docs/02 - V1 and Why It Failed.md`).
