"""SEPPACT_parameters, the parameters of the analysis, with their defaults and checks"""
from dataclasses import dataclass, field, fields
from datetime import timedelta
from typing import ClassVar


def default_group_options() -> dict:
    """Returns the default energy channel groups of HET, per particle"""
    return {
        "electrons": {
            "1 MeV": {
                "sensor": "HET",
                "channels": [0, 1],
                "reference_channel": True
            },
            "5.9930 - 18.8300 MeV": {
                "sensor": "HET",
                "channels": [3]
            }
        },
        "protons": {
            "8 MeV": {
                "sensor": "HET",
                "channels": [1, 2, 3]
            },
            "25 MeV": {
                "sensor": "HET",
                "channels": [18, 19]},
            "50 MeV": {
                "sensor": "HET",
                "channels": [27]
            }
        }
    }


def default_spike_thresholds() -> dict:
    """Returns the default spike threshold of each default resolution"""
    return {
        timedelta(minutes=2): 2.0,
        timedelta(minutes=5): 2.0,
        timedelta(minutes=10): 2.5,
        timedelta(minutes=30): 3.0
    }


@dataclass
class SEPPACT_parameters:
    """Parameters of the analysis

    Unknown parameter names raise an AttributeError, and invalid values a ValueError or TypeError.
    The checks between parameters (e.g. a spike threshold for each resolution) are done by check(),
    which the analysis calls before it starts.
    """
    VIEWINGS: ClassVar[tuple] = ("sun", "asun", "north", "south")
    PARTICLES: ClassVar[tuple] = ("electrons", "protons")
    SENSORS: ClassVar[tuple] = ("HET",)

    # Files and folders
    dir_inputs: str = "inputs"                 # event list and shock list
    dir_data: str = "data"                     # downloaded EPD files
    dir_saves: str = "intermediate_states"     # cached flux DataFrames
    dir_plots: str = "plots"                   # one figure per event
    dir_outputs: str = "outputs"               # result tables
    # event list in dir_inputs: Event No, Onset Time and optionally BG Start, BG End, End Time
    file_events: str = "example.xlsx"
    file_shocks: str = "shocks.dat"            # interplanetary shock list from ipshocks.helsinki.fi, in dir_inputs

    # Event windows, used where the event list leaves them empty
    bg_start_before_onset: timedelta = timedelta(hours=2)
    bg_end_before_onset: timedelta = timedelta(minutes=5)
    end_after_onset: timedelta = timedelta(hours=48)
    min_plot_window: timedelta = timedelta(days=2)    # shorter events are extended equally on both sides

    # Data
    level: str = "l2"
    viewings: list[str] = field(default_factory=lambda: ["sun", "asun", "north", "south"])
    # in ascending order
    resample_freqs: list[timedelta] = field(default_factory=lambda: [timedelta(minutes=m) for m in (2, 5, 10, 30)])
    group_options: dict = field(default_factory=default_group_options)
    download_tries: int = 2                    # the tries after the first load only the background start to the end time

    # Onset
    onset_sigma: float = 2                     # threshold = background mean + onset_sigma * background standard deviation
    onset_points: int = 3                      # consecutive points above the threshold
    # onsets further than this from the onset of the reference channel are ignored
    reference_onset_window: timedelta = timedelta(hours=2.5)

    # Data quality
    # allowed transitions from valid to zero or NaN values after the onset, as a fraction of the points
    quality_tolerance: float = 0.1
    quality_adjustable: bool = False           # if True, the tolerance grows with the resampling period

    # Spikes, peak and fluence
    # smallest difference, in orders of magnitude, of a spike from both its neighbours, per resolution
    spike_thresholds: dict = field(default_factory=default_spike_thresholds)
    # spikes and peaks are searched in the first half of onset to end, if that is at least this long
    peak_window_min: timedelta = timedelta(hours=10)
    # the fluence interval is bounded where the flux falls below this fraction of the peak
    fluence_peak_fraction: float = 0.5
    fluence_points: int = 2                    # consecutive points below the threshold that bound the fluence interval

    # Plots
    fallback_viewing: str = "sun"              # viewing shown, at the coarsest resolution, for channels without an onset

    def __setattr__(self, name: str, value) -> None:
        names = [f.name for f in fields(self)]
        if name not in names:
            raise AttributeError(f"SEPPACT_parameters has no parameter {name!r}. The parameters are: {', '.join(names)}.")
        self._check_value(name, value)
        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        self.check()

    def _check_value(self, name: str, value) -> None:
        """Checks the value of one parameter, independently of the others"""
        timedeltas = ["bg_start_before_onset", "bg_end_before_onset", "end_after_onset", "min_plot_window",
                      "reference_onset_window", "peak_window_min"]
        if name in timedeltas and not isinstance(value, timedelta):
            raise TypeError(f"{name} must be a datetime.timedelta, e.g. timedelta(hours=2), not {value!r}.")
        if name == "viewings":
            invalid = [v for v in value if v not in self.VIEWINGS]
            if invalid or not value:
                raise ValueError(f"viewings must be a non-empty list of {', '.join(self.VIEWINGS)}; invalid: {invalid}.")
        if name == "fallback_viewing" and value not in self.VIEWINGS:
            raise ValueError(f"fallback_viewing must be one of {', '.join(self.VIEWINGS)}, not {value!r}.")
        if name == "resample_freqs":
            if not value or not all(isinstance(f, timedelta) for f in value):
                raise TypeError("resample_freqs must be a non-empty list of datetime.timedelta.")
            if list(value) != sorted(value):
                raise ValueError(f"resample_freqs must be in ascending order, not {value}.")
        if name in ("onset_points", "fluence_points", "download_tries") and (not isinstance(value, int) or value < 1):
            raise ValueError(f"{name} must be an integer of at least 1, not {value!r}.")
        if name == "fluence_peak_fraction" and not 0 < value <= 1:
            raise ValueError(f"fluence_peak_fraction must be in (0, 1], not {value!r}.")
        if name == "group_options":
            self._check_group_options(value)

    def _check_group_options(self, group_options: dict) -> None:
        """Checks the particles, sensors and reference channel of the energy channel groups"""
        for particle, groups in group_options.items():
            if particle not in self.PARTICLES:
                raise ValueError(f"group_options has the particle {particle!r}; "
                                 f"the particles are {', '.join(self.PARTICLES)}.")
            for label, spec in groups.items():
                if spec.get("sensor") not in self.SENSORS:
                    raise ValueError(f"The group {label!r} of {particle} has the sensor {spec.get('sensor')!r}; "
                                     f"the sensors are {', '.join(self.SENSORS)}.")
                if not spec.get("channels"):
                    raise ValueError(f"The group {label!r} of {particle} has no channels.")
        references = [(particle, label) for particle, groups in group_options.items()
                      for label, spec in groups.items() if "reference_channel" in spec]
        if len(references) > 1:
            raise ValueError(f"More than one reference channel found: {references}. "
                             "Mark at most one group with \"reference_channel\".")

    def check(self) -> None:
        """Checks the parameters that depend on each other"""
        missing_thresholds = [freq for freq in self.resample_freqs if freq not in self.spike_thresholds]
        if missing_thresholds:
            raise ValueError(f"spike_thresholds has no threshold for the resolutions {missing_thresholds}. "
                             "Add one for each resolution in resample_freqs.")

    @property
    def reference_channel(self) -> dict | None:
        """Returns the reference channel as {"particle", "mev", "sensor"}, or None if there is none"""
        for particle, groups in self.group_options.items():
            for label, spec in groups.items():
                if "reference_channel" in spec:
                    return {"particle": particle, "mev": label, "sensor": spec["sensor"]}
        return None
