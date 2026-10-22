"""SEPPACT_parameters, the parameters of the analysis, with their defaults and checks"""
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from typing import ClassVar

from .shocks import SHOCK_SOURCES


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


# Removed parameters: {name: (version, what to use instead)}
REMOVED_PARAMETERS = {
    "dir_inputs": ("0.2.0", "Give the event list and the shock list as paths, in file_events and file_shocks."),
    "bg_start_before_onset": ("0.2.0", "The event list has a Reference Time instead of an Onset Time: the data start "
                                       "start_before_reference before it, and the default background starts "
                                       "bg_start_after_start after the Start Time."),
    "bg_end_before_onset": ("0.2.0", "The default background ends bg_end_after_start after the Start Time."),
    "end_after_onset": ("0.2.0", "The event list has a Reference Time instead of an Onset Time: the data end "
                                 "end_after_reference after it."),
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
    SHOCK_SOURCES: ClassVar[tuple] = tuple(SHOCK_SOURCES)

    # Files and folders
    # event list: Event No, then Reference Time, or Start Time and End Time with optionally BG Start and BG End, and
    # optionally Particle and Sensor for the rows of the background windows of particles and sensors;
    # without an event list (""), the events are date_ranges
    file_events: str = "inputs/events_example.csv"
    # onset corrections saved by save_corrections(), applied to the chosen onsets; "" for none
    file_corrections: str = ""
    dir_data: str = "data"                     # downloaded EPD files
    dir_saves: str = "intermediate_states"     # cached flux DataFrames
    dir_plots: str = "plots"                   # one figure per event
    dir_outputs: str = "outputs"               # result tables

    # Events without an event list: [(start, end)] of each event, as datetime
    date_ranges: list[tuple] = field(default_factory=list)

    # Shocks: the analysis of a channel group ends at the first shock after its onset. The shocks are those of the
    # shock list online, of the shock list file and the custom ones, without the removed ones
    shock_source: str | None = "SODA"          # shock list online: "SODA", "IRFU" or None (see shocks.SHOCK_SOURCES)
    file_shocks: str = ""                      # ipshocks list (.dat), IRFU list (.txt) or CSV with Shock Time; "" for none
    shock_times: list[datetime] = field(default_factory=list)
    removed_shocks: list[datetime] = field(default_factory=list)

    # Event windows
    # the data of an event with a Reference Time start and end this long before and after it
    start_before_reference: timedelta = timedelta(hours=2)
    end_after_reference: timedelta = timedelta(hours=48)
    # the default background window, of the events without one, starts and ends this long after the Start Time
    bg_start_after_start: timedelta = timedelta(0)
    bg_end_after_start: timedelta = timedelta(hours=1, minutes=55)
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
    panel_height: float = 2.5                  # height of the panel of each channel group, in inches (1 to 10)

    def __setattr__(self, name: str, value) -> None:
        # catches removed parameters and typos, which would otherwise be silently ignored
        if name in REMOVED_PARAMETERS:
            version, replacement = REMOVED_PARAMETERS[name]
            raise AttributeError(f"The {name} parameter was removed in {version}. {replacement}")
        names = [f.name for f in fields(self)]
        if name not in names:
            raise AttributeError(f"SEPPACT_parameters has no parameter {name!r}. The parameters are: {', '.join(names)}.")
        check = self.VALUE_CHECKS.get(name)
        if check is not None:
            getattr(self, check)(name, value)
        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        self.check()

    # Check of the value of each parameter that has one, independently of the other parameters
    VALUE_CHECKS: ClassVar[dict] = {
        **{name: "_check_timedelta" for name in ("start_before_reference", "end_after_reference", "bg_start_after_start",
                                                 "bg_end_after_start", "min_plot_window", "reference_onset_window",
                                                 "peak_window_min")},
        "date_ranges": "_check_date_ranges",
        "shock_source": "_check_shock_source",
        **{name: "_check_times" for name in ("shock_times", "removed_shocks")},
        **{name: "_check_count" for name in ("onset_points", "fluence_points", "download_tries")},
        "viewings": "_check_viewings",
        "fallback_viewing": "_check_fallback_viewing",
        "resample_freqs": "_check_resample_freqs",
        "fluence_peak_fraction": "_check_fraction",
        "group_options": "_check_group_options",
        "panel_height": "_check_panel_height",
    }

    @staticmethod
    def _check_timedelta(name: str, value) -> None:
        if not isinstance(value, timedelta):
            raise TypeError(f"{name} must be a datetime.timedelta, e.g. timedelta(hours=2), not {value!r}.")

    @staticmethod
    def _check_date_ranges(name: str, value) -> None:
        for i, date_range in enumerate(value, start=1):
            if not (isinstance(date_range, (tuple, list)) and len(date_range) == 2
                    and all(isinstance(t, datetime) for t in date_range)):
                raise TypeError(f"{name} must be a list of (start, end) datetime pairs; event {i} is {date_range!r}.")
            if date_range[0] >= date_range[1]:
                raise ValueError(f"Event {i} of {name}: the start ({date_range[0]}) must be before the end "
                                 f"({date_range[1]}).")

    def _check_shock_source(self, name: str, value) -> None:
        if value is not None and value not in self.SHOCK_SOURCES:
            raise ValueError(f"{name} must be one of {', '.join(self.SHOCK_SOURCES)}, or None, not {value!r}.")

    @staticmethod
    def _check_times(name: str, value) -> None:
        if not all(isinstance(t, datetime) for t in value):
            raise TypeError(f"{name} must be a list of datetime, not {value!r}.")

    @staticmethod
    def _check_count(name: str, value) -> None:
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be an integer of at least 1, not {value!r}.")

    # the panel heights (inches) that are accepted, and those that are recommended: below 2 the labels in a panel
    # overlap, and above 4 the plots of several channel groups are hard to view on a screen
    PANEL_HEIGHTS: ClassVar[tuple] = (1, 10)
    RECOMMENDED_PANEL_HEIGHTS: ClassVar[tuple] = (2, 4)

    def _check_panel_height(self, name: str, value) -> None:
        low, high = self.PANEL_HEIGHTS
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ValueError(f"{name} must be a number of inches from {low} to {high}, not {value!r}.")

    @staticmethod
    def _check_fraction(name: str, value) -> None:
        if not 0 < value <= 1:
            raise ValueError(f"{name} must be in (0, 1], not {value!r}.")

    def _check_viewings(self, name: str, value) -> None:
        invalid = [v for v in value if v not in self.VIEWINGS]
        if invalid or not value:
            raise ValueError(f"{name} must be a non-empty list of {', '.join(self.VIEWINGS)}; invalid: {invalid}.")

    def _check_fallback_viewing(self, name: str, value) -> None:
        if value not in self.VIEWINGS:
            raise ValueError(f"{name} must be one of {', '.join(self.VIEWINGS)}, not {value!r}.")

    @staticmethod
    def _check_resample_freqs(name: str, value) -> None:
        if not value or not all(isinstance(f, timedelta) for f in value):
            raise TypeError(f"{name} must be a non-empty list of datetime.timedelta.")
        if list(value) != sorted(value):
            raise ValueError(f"{name} must be in ascending order, not {value}.")

    def _check_group_options(self, name: str, group_options: dict) -> None:
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
        if self.bg_start_after_start >= self.bg_end_after_start:
            raise ValueError(f"bg_start_after_start ({self.bg_start_after_start}) must be before bg_end_after_start "
                             f"({self.bg_end_after_start}).")
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
