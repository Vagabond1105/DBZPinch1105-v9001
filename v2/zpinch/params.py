"""
User-facing parameters.

SetupParams take effect on reset (they define the grid and the initial
state). LiveParams are read by the solver every step and can be changed
while the simulation runs. Each field carries its own range/label/help in
`metadata`, which the GUI uses to build its controls.
"""

from dataclasses import dataclass, field, fields, asdict


def _p(default, lo=None, hi=None, label="", help="", log=False, step=None, choices=None):
    return field(default=default, metadata=dict(
        lo=lo, hi=hi, label=label, help=help, log=log, step=step, choices=choices))


RESOLUTIONS = {
    "Very fast (32 x 32 x 48)": 32,
    "Fast (48 x 48 x 72)": 48,
    "Medium (64 x 64 x 96)": 64,
    "High (80 x 80 x 120)": 80,
    "Very high (96 x 96 x 144)": 96,
}


@dataclass
class SetupParams:
    resolution: str = _p("Very fast (32 x 32 x 48)", label="Grid resolution",
                         choices=list(RESOLUTIONS),
                         help="Cells across the domain width. Cost scales as N^4 "
                              "(N^3 cells x N timesteps): Very fast is ~5x quicker than Fast, "
                              "Fast/Medium give finer detail.")
    pinch_radius: float = _p(0.12, 0.06, 0.2, "Pinch radius a",
                             "Bennett radius of the plasma column, in units of the domain width.")
    length: float = _p(1.5, 1.0, 3.0, "Column length / width",
                       "Axial (z, periodic) length of the domain relative to its width.")
    background_density: float = _p(0.05, 0.01, 0.2, "Background density",
                                   "Density of the tenuous plasma outside the pinch, relative to "
                                   "the peak. Lower = more vacuum-like, but faster Alfven waves "
                                   "(smaller timesteps).", log=True)
    axial_field: float = _p(0.0, 0.0, 1.5, "Axial guide field Bz",
                            "Uniform B_z as a fraction of the peak azimuthal field. "
                            "Bz stiffens the column against the sausage (m=0) mode "
                            "(Kadomtsev: stable for Bz^2 > B_theta^2 / 2 at the edge).")
    perturbation: str = _p("Random + m=0 + m=1", label="Seed perturbation",
                           choices=["Random", "Sausage (m=0)", "Kink (m=1)", "Random + m=0 + m=1", "None"],
                           help="What breaks the symmetry of the equilibrium.")
    perturbation_amp: float = _p(0.02, 0.0, 0.2, "Perturbation amplitude",
                                 "Relative amplitude of the seed perturbation.")
    n_tracers: int = _p(15000, 0, 60000, "Tracer particles",
                        "Passive Lagrangian markers advected with the fluid velocity.", step=1000)
    seed: int = _p(1, 0, 9999, "Random seed", "Seed for the random perturbation and tracer placement.", step=1)


@dataclass
class LiveParams:
    current: float = _p(1.0, 0.0, 3.0, "Drive current I / I_Bennett",
                        "Axial current set by the external circuit, relative to the "
                        "current that holds the initial profile in Bennett equilibrium. "
                        ">1 compresses (pinches) the column, <1 lets it expand.")
    rise_time: float = _p(0.2, 0.01, 3.0, "Current rise time",
                          "L/R time constant of the drive circuit: the current relaxes "
                          "exponentially toward the set value with this time constant.", log=True)
    resistivity: float = _p(3e-4, 0.0, 1e-2, "Resistivity eta",
                            "Magnetic diffusivity (eta/mu_0). Lets field lines reconnect and "
                            "slip through the plasma; dissipates current as Ohmic heat.", log=True)
    spitzer: bool = _p(False, label="Spitzer scaling eta ~ T^-3/2",
                       help="Scale resistivity with local temperature like a real plasma "
                            "(hot plasma conducts better). Capped at 10x the base value.")
    viscosity: float = _p(3e-4, 0.0, 1e-2, "Viscosity nu",
                          "Kinematic viscosity. Damps velocity shear; dissipated kinetic "
                          "energy becomes heat.", log=True)
    cooling: float = _p(0.0, 0.0, 2.0, "Radiative cooling",
                        "Optically thin bremsstrahlung, P = C rho^2 sqrt(T). Dense, "
                        "compressed regions radiate fastest.", log=True)
    gravity: float = _p(0.0, 0.0, 2.0, "Gravity (-y)",
                        "Uniform gravitational acceleration along -y.")
    solver: str = _p("HLLD", label="Riemann solver", choices=["HLLD", "HLL"],
                     help="HLLD resolves all MHD waves (sharper); HLL is more diffusive but very robust.")


def defaults_dict(cls):
    return asdict(cls())


def describe(cls):
    """(name, default, metadata) for every field - used to build the GUI."""
    return [(f.name, f.default, f.metadata) for f in fields(cls)]


# Named starting points: (setup overrides, live overrides) on top of the
# defaults. Each one reproduces a measured behaviour from the docs.
PRESETS = {
    "Pure Z-pinch: kink -> disruption": ({}, {}),
    "Saturated kink (Bz = 0.6)": ({"axial_field": 0.6}, {}),
    "Stable screw pinch": ({"axial_field": 1.5, "length": 1.0}, {}),
    "Implosion (snowplow)": ({}, {"current": 2.5, "rise_time": 0.1}),
    "Gravity sag": ({}, {"gravity": 1.0}),
}


def apply_preset(name, setup, live):
    """Reset setup/live to defaults, then apply the preset's overrides."""
    setup_over, live_over = PRESETS[name]
    for obj, cls, over in ((setup, SetupParams, setup_over), (live, LiveParams, live_over)):
        for key, value in {**asdict(cls()), **over}.items():
            setattr(obj, key, value)
