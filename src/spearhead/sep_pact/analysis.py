"""The analysis: SEPPACT, which runs the steps and keeps their results, and the functions of each step"""
import os
from datetime import datetime, timedelta
from os.path import join as pjoin

import numpy as np
import pandas as pd

from .background import BGWindow, key_label, window_points
from .conf import SEPPACT_parameters
from .data import channel_layout, download_data, load_energies, resample_flux
from .inputs import CORRECTION_COLUMNS, load_events, load_shocks, read_corrections, shock_warnings


# the index of df_series, one row per series, and of df_results, one row per channel group of an event
SERIES_INDEX = ["Event No", "Particle", "Sensor", "Energy Label", "Resolution", "Viewing"]
CHANNEL_INDEX = SERIES_INDEX[:4]
FLUENCE_COLUMNS = ["Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"]
QUALITY_COLUMNS = ["Quality Length", "Quality Zeroes", "Quality Ratio"]
# the columns of df_results in results.csv
RESULT_COLUMNS = ["Onset Time", "Onset Resolution", "Onset Viewing", "Onset Copied", "Onset at BG End", "Onset Corrected",
                  "Peak Flux", "Peak Flux Time", "Peak Flux Resolution", "Peak Flux Viewing",
                  "Fluence", "Fluence Start", "Fluence End", "Fluence Threshold", "Fluence Resolution", "Fluence Viewing"]
# the fewest points of a background window without a warning
MIN_BG_POINTS = 3


def shocks_in_range(shocktimes: pd.Series, start: datetime, end: datetime) -> list[datetime]:
    """Returns the shock times from start to end"""
    shocks = shocktimes[(shocktimes >= start) & (shocktimes <= end)]
    return shocks.tolist()


def peak_search_end(onset: datetime, enddate: datetime, peak_window_min: timedelta) -> datetime:
    """Returns the end of the spike and peak search: the middle of onset to end, if that leaves at least peak_window_min"""
    middle = onset + abs(enddate - onset)/2
    return middle if abs(middle - onset) >= peak_window_min else enddate


def _bg_times(series: pd.Series, bg_start, bg_end) -> tuple:
    """The background start and end as times, also when given as point indices"""
    if isinstance(bg_start, (int, np.integer)):
        bg_start = series.index[bg_start]
    if isinstance(bg_end, (int, np.integer)):
        bg_end = series.index[bg_end]
    return bg_start, bg_end


def _first_run_above(series: pd.Series, threshold: float, n: int):
    """Returns the time of the first of n consecutive points above the threshold, or None"""
    streak = 0
    start = None
    for index, value in series.items():
        if value > threshold:
            streak += 1
            if start is None:
                start = index
            if streak >= n:
                return start
        else:
            streak = 0
            start = None
    return None


def _walk_back(series: pd.Series, onset_time):
    """Returns the earliest time before onset_time reached while each earlier point is lower than the next one"""
    onset_value = series.loc[onset_time]
    for index, value in series.loc[:onset_time - timedelta(milliseconds=1)].iloc[::-1].items():
        if value < onset_value:
            onset_time = index
            onset_value = value
        else:
            break
    return onset_time


def onset_detection_sigma(series: pd.Series,
                          s: float,
                          n: int,
                          bg_start: int | datetime,
                          bg_end: int | datetime) -> tuple:
    """Returns the onset time (None if no event is detected), the background start and end, and a dict with the
    background level and the threshold

    The threshold is the background mean plus s standard deviations. After the background, the first of n consecutive
    points above the threshold is found, and the onset is moved back to earlier points while each one is lower than
    the next, but not before the end of the background.
    """
    bg_start, bg_end = _bg_times(series, bg_start, bg_end)
    bg_level = (bg_series := series[bg_start:bg_end]).mean()
    threshold = bg_level + s * bg_series.std()
    data_series = series[bg_end:]
    onset_time = _first_run_above(data_series, threshold, n)
    if onset_time is not None:
        onset_time = _walk_back(data_series, onset_time)
    return (
        onset_time,
        bg_start,
        bg_end,
        {"bg_level": bg_level, "threshold": threshold},
    )


def quality_analysis(timeseries: pd.Series,
                     tolerance: float,
                     adjustable_tolerance: bool) -> tuple[bool, int, int, float]:
    """Returns whether the series qualifies, its length, its number of zero or NaN values and its ratio of transitions
    to them"""
    n_zeroes = len(timeseries[(timeseries == 0) | pd.isna(timeseries)])
    if len(timeseries) < 2:
        return False, len(timeseries), n_zeroes, np.nan
    n_changes = 0
    during_streak = False
    for point in timeseries:
        if point == 0 or pd.isna(point):
            if not during_streak:
                during_streak = True
                n_changes += 1
        else:
            during_streak = False
    ratio = n_changes / len(timeseries)
    resolution = timeseries.index[1] - timeseries.index[0]
    rate_adjustment_multiplier = 1 + resolution.total_seconds() / timedelta(minutes=60).total_seconds()
    qualified = ratio < tolerance * (rate_adjustment_multiplier if adjustable_tolerance else 1) \
        and n_zeroes < len(timeseries) - n_zeroes
    return qualified, len(timeseries), n_zeroes, ratio


def reference_iter(items, reference_channel: dict | None) -> list:
    """Returns the items with the one of the reference channel (particle, group or sensor) first"""
    if reference_channel is None:
        return items
    for v in reference_channel.values():
        if v in items:
            return [v] + [i for i in items if i != v]
    return items


def detect_spikes(series: pd.Series, threshold: float) -> list[datetime]:
    """Returns the times of the points that differ from both neighbours by more than threshold orders of magnitude"""
    log_flux = np.log10(series.where(series > 0)).replace(np.inf, np.nan).dropna()
    prev_abs_diff = log_flux.diff(periods=1).abs()
    next_abs_diff = log_flux.diff(periods=-1).abs()
    min_abs_diff = prev_abs_diff.combine(next_abs_diff, min)
    min_abs_diff = min_abs_diff.iloc[1:-1]
    return min_abs_diff[min_abs_diff > threshold].index.tolist()


def remove_spikes(ts: pd.Series, spike_times: list[datetime], resample_freq: timedelta) -> pd.Series:
    """Returns a copy of the series with each spike replaced by the mean of its valid neighbours

    The neighbours are the points one resolution step before and after. A spike without a valid neighbour is left unchanged.
    """
    ts = ts.copy()
    for spike_time in spike_times:
        neighbours = [ts[t] for t in (spike_time - resample_freq, spike_time + resample_freq) if t in ts.index]
        if spike_time in ts.index and not all(pd.isna(neighbours)):
            ts[spike_time] = np.nanmean(neighbours)
    return ts


def get_peak_flux(series: pd.Series) -> tuple[float, datetime]:
    """Returns the maximum of the series and its time, or None and None if the series has no values"""
    try:
        peak_time = series.idxmax()
        peak_flux = series.max()
    except ValueError:
        peak_time = None
        peak_flux = None
    return peak_flux, peak_time


def _peak_point(ts: pd.Series, peak_time: datetime) -> tuple:
    """Returns the flux and time of the higher of the points just before and after peak_time"""
    before = ts.loc[:peak_time]
    after = ts.loc[peak_time:]
    if before.empty:
        return after.values[0], after.index[0]
    if after.empty or before.values[-1] > after.values[0]:
        return before.values[-1], before.index[-1]
    return after.values[0], after.index[0]


def _interval_start(ts: pd.Series, peak_time: datetime, threshold: float, points: int):
    """Returns the last of the nearest run of points consecutive points at or below the threshold before the peak,
    with fewer points if there is none, or None"""
    for needed_points in range(points, 0, -1):
        n = 0
        for j in range(len(ts.loc[:peak_time]) - 1, -1, -1):
            if ts.iloc[j] <= threshold:
                n += 1
                if n == needed_points:
                    return ts.index[j + (needed_points - 1)]
            else:
                n = 0
    return None


def _interval_end(ts: pd.Series, peak_time: datetime, threshold: float, points: int):
    """Returns the first of the nearest run of points consecutive points at or below the threshold after the peak,
    with fewer points if there is none, or None"""
    after = ts.loc[peak_time:]
    if after.empty:
        # due to resolution differences, the peak flux point can be beyond the end of the series
        return None
    first = list(ts.index).index(after.index[0])
    for needed_points in range(points, 0, -1):
        n = 0
        for j, v in enumerate(after, start=first):
            if v <= threshold:
                n += 1
                if n == needed_points:
                    return ts.index[j - (needed_points - 1)]
            else:
                n = 0
    return None


def fluence_interval(ts: pd.Series,
                     onset: datetime,
                     peak_time: datetime,
                     enddate: datetime,
                     peak_fraction: float,
                     points: int) -> tuple[float, datetime, datetime, float]:
    """Returns the fluence, the start and end of its interval and the flux threshold that bounds it

    The peak is the point next to peak_time (the higher of the points just before and after it), and the threshold
    is peak_fraction of its flux. The interval is bounded by the nearest runs of points consecutive points at or
    below the threshold (or of single points) before and after the peak, and starts at the onset at the earliest.
    The fluence is the integral of the flux over the interval, over time in seconds.
    """
    peak_flux, peak_time = _peak_point(ts, peak_time)
    threshold = peak_flux * peak_fraction
    fluence_start = _interval_start(ts, peak_time, threshold, points)
    if fluence_start is None or fluence_start < onset:
        fluence_start = onset
    fluence_end = _interval_end(ts, peak_time, threshold, points)
    if fluence_end is None or fluence_end > ts.index[-1]:
        fluence_end = enddate

    ts = ts.loc[fluence_start:fluence_end].dropna()
    fluence = np.trapezoid(ts.values, ts.index).astype("timedelta64[s]").astype("float")
    return fluence, fluence_start, fluence_end, threshold


def _rows_at(rows: pd.DataFrame, level: str, value) -> pd.DataFrame:
    """Returns the rows of a channel group (indexed by resolution and viewing) at a resolution or viewing, indexed by
    the other level"""
    return rows[rows.index.get_level_values(level) == value].droplevel(level)


def choose_onset(rows: pd.DataFrame, reference_onset, reference_onset_window: timedelta, bg_end: datetime) -> dict:
    """Returns the chosen onset of a channel group, from its rows of df_series indexed by (resolution, viewing) in the
    order of the parameters

    The onset is the earliest of the viewings at the finest resolution with a usable series, and within
    reference_onset_window of reference_onset if that is given. Of equal onsets, the first viewing is chosen.
    """
    usable = rows[rows["Usable"]]
    if not pd.isna(reference_onset):
        usable = usable[(usable["Onset Time"] - reference_onset).abs() <= reference_onset_window]
    if usable.empty:
        return _no_onset()
    resolution = usable.index.get_level_values("Resolution")[0]
    at_resolution = _rows_at(usable, "Resolution", resolution)
    viewing = at_resolution["Onset Time"].idxmin()
    return _onset_of(at_resolution.loc[viewing], resolution, viewing, bg_end)


def _no_onset() -> dict:
    """The onset columns of df_results of a channel group without an onset"""
    return {"Onset Time": pd.NaT, "Onset Resolution": pd.NaT, "Onset Viewing": None, "Onset Copied": None,
            "Onset at BG End": None, **{column: np.nan for column in QUALITY_COLUMNS}}


def _onset_of(row: pd.Series, resolution, viewing: str, bg_end: datetime) -> dict:
    """The onset columns of df_results of a channel group, from the row of df_series of the chosen series"""
    # an onset at the end of the background may have started inside it
    return {"Onset Time": row["Onset Time"], "Onset Resolution": resolution, "Onset Viewing": viewing,
            "Onset Copied": bool(row["Onset Copied"]), "Onset at BG End": bool(row["Onset Time"] <= bg_end),
            **{column: row[column] for column in QUALITY_COLUMNS}}


def corrected_onset(rows: pd.DataFrame, correction: tuple | None, bg_end: datetime) -> dict:
    """Returns the onset of a channel group set by a correction, (resolution, viewing) of one of its series with an
    onset or None for no onset, from its rows of df_series indexed by (resolution, viewing)"""
    if correction is None:
        return _no_onset()
    return _onset_of(rows.loc[correction], *correction, bg_end)


def choose_peak(rows: pd.DataFrame, resolution) -> dict:
    """Returns the chosen peak flux of a channel group, from its rows of df_series indexed by (resolution, viewing):
    the highest of the viewings at the resolution of the chosen onset. Of equal peaks, the first viewing is chosen."""
    none = {"Peak Flux": np.nan, "Peak Flux Time": pd.NaT, "Peak Flux Resolution": pd.NaT, "Peak Flux Viewing": None}
    if pd.isna(resolution):
        return none
    peaks = _rows_at(rows, "Resolution", resolution)["Peak Flux"].dropna()
    if peaks.empty:
        return none
    viewing = peaks.idxmax()
    return {"Peak Flux": peaks[viewing],
            "Peak Flux Time": rows.loc[(resolution, viewing), "Peak Flux Time"],
            "Peak Flux Resolution": resolution,
            "Peak Flux Viewing": viewing}


def choose_fluence(rows: pd.DataFrame, onset, viewing) -> dict:
    """Returns the chosen fluence of a channel group, from its rows of df_series indexed by (resolution, viewing):
    the largest of the resolutions in the viewing of the chosen peak, among those that do not start before the onset.
    Of equal fluences, the first resolution is chosen."""
    none = {"Fluence": np.nan, "Fluence Start": pd.NaT, "Fluence End": pd.NaT, "Fluence Threshold": np.nan,
            "Fluence Resolution": pd.NaT, "Fluence Viewing": None}
    if pd.isna(viewing) or pd.isna(onset):
        return none
    in_viewing = _rows_at(rows, "Viewing", viewing)
    valid = in_viewing[in_viewing["Fluence"].notna() & ~(in_viewing["Fluence Start"] < onset)]
    if valid.empty:
        return {**none, "Fluence Viewing": viewing}
    resolution = valid["Fluence"].idxmax()
    return {**{column: valid.loc[resolution, column] for column in FLUENCE_COLUMNS},
            "Fluence Resolution": resolution, "Fluence Viewing": viewing}


class SEPPACT:
    """Onset time, peak flux and fluence of the events of an event list

    Run the steps in order: run_inputs(), run_data(), run_onsets(), run_spikes(), run_peaks(), run_fluences(),
    then plot_events() and save_results(). Background windows (of an event, or of a particle, or a particle and sensor
    in it) and end times can be changed with set_bg_window() and set_end_time() after run_data(), before the onsets.
    After the onsets, set_onset() replaces the chosen onset of a
    channel group by another detected one, or by no onset (corrections, applied again when the steps run again, and
    saved by save_corrections()). The results stay available as attributes:
    - events: the event list, one row per event, with the times filled in, the background window of the event, and
      where the window and the end time come from (BG Window Source, End Time Source)
    - bg_windows: the background windows of the events and of their particles and sensors (see bg_window())
    - shocks: the shocks (Shock Time, Source), and shocktimes their times
    - dfs_flux: the flux of the channel groups, per particle, sensor and resolution
    - df_series: the onset, data quality, peak flux and fluence of every series, one row per event, particle, sensor,
      group label, resolution and viewing
    - df_spikes: the spike times, one row per spike, with the index of its series
    - df_results: the chosen onset, peak flux and fluence, one row per event and channel group
    - corrections: {(event number, particle, sensor, group label): (resolution, viewing) of the onset, or None for no
      onset}
    """

    def __init__(self, params: SEPPACT_parameters | None = None) -> None:
        self.params = params if params is not None else SEPPACT_parameters()
        self.params.check()
        self.particles, self.sensors, self.channels, self.sensors_all = channel_layout(self.params.group_options)
        self.reference_channel = self.params.reference_channel
        self.shocks = None
        self.shocktimes = None
        self.events = None
        self.bg_windows = None
        self._input_end_times = None
        self.energies = None
        self.dfs_flux = None
        self.df_series = None
        self.df_spikes = None
        self.df_results = None
        self.corrections = {}
        # the onset times of the corrections of file_corrections, compared with the onsets when they are applied
        self._correction_times = {}

    def _analysis_end(self, event_no: int, onset: datetime) -> datetime:
        """Returns the end of the analysis of an onset: the end time, or the first shock after the onset"""
        enddate = self.events.loc[event_no, "End Time"]
        if len(shocks := shocks_in_range(self.shocktimes, onset, self.events.loc[event_no, "End Time"])) > 0:
            enddate = shocks[0]
        return enddate

    def _groups(self, particle: str) -> list[str]:
        """Returns the labels of the channel groups of a particle"""
        return list(self.params.group_options[particle].keys())

    def _iter_channels(self):
        """Yields (particle, sensor, group label) of the channel groups"""
        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for mevlbl in self._groups(particle):
                    yield particle, sensor, mevlbl

    def _iter_series_keys(self):
        """Yields the index of each row of df_series: (event number, particle, sensor, group label, resolution,
        viewing), with the resolutions and viewings in the order of the parameters"""
        for event_no in self.events.index:
            for particle, sensor, mevlbl in self._iter_channels():
                for resample_freq in self.params.resample_freqs:
                    for viewing in self.params.viewings:
                        yield event_no, particle, sensor, mevlbl, resample_freq, viewing

    def _series_keys(self, event_no: int | None = None) -> pd.MultiIndex:
        """Returns the index of df_series, of all the events or of one"""
        index = self.df_series.index
        return index if event_no is None else index[index.get_level_values("Event No") == event_no]

    def _iter_channel_rows(self, event_no: int | None = None):
        """Yields (event number, particle, sensor, group label) and the rows of df_series of each channel group (of all
        the events or of one), indexed by (resolution, viewing) in the order of the parameters"""
        series = self.df_series if event_no is None else self.df_series.loc[self._series_keys(event_no)]
        for key, rows in series.groupby(level=CHANNEL_INDEX, sort=False):
            yield key, rows.droplevel(CHANNEL_INDEX)

    def _flux(self, event_no: int, particle: str, sensor: str, mevlbl: str, resample_freq: timedelta,
              viewing: str) -> pd.Series:
        """Returns the flux of an event and channel group at a resolution and viewing, indexed by time"""
        return self.dfs_flux[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl)]

    def _chosen(self, event_no: int, particle: str, sensor: str, mevlbl: str, column: str):
        """Returns a column of df_results of an event and channel group"""
        return self.df_results.loc[(event_no, particle, sensor, mevlbl), column]

    def _onset(self, event_no: int, particle: str, sensor: str, mevlbl: str):
        """Returns the chosen onset of an event and channel group"""
        return self._chosen(event_no, particle, sensor, mevlbl, "Onset Time")

    def _set_series(self, columns: dict, keys: pd.MultiIndex | None = None) -> None:
        """Sets columns of df_series from {column: values in the order of its rows}, or of the rows of keys only"""
        for column, values in columns.items():
            if keys is None:
                self.df_series[column] = values
            else:
                self.df_series.loc[keys, column] = values

    def _set_results(self, rows: dict) -> None:
        """Sets the columns of df_results from {(event number, particle, sensor, group label): {column: value}}; the
        first call (select_onsets()) creates df_results, with its rows in the order of the event list and channel groups"""
        df = pd.DataFrame.from_dict(rows, orient="index")
        df.index = pd.MultiIndex.from_tuples(df.index, names=CHANNEL_INDEX)
        if self.df_results is None:
            self.df_results = df.reindex(pd.MultiIndex.from_tuples(
                [(event_no, *channel) for event_no in self.events.index for channel in self._iter_channels()],
                names=CHANNEL_INDEX))
        elif len(df) == len(self.df_results):
            for column in df.columns:
                self.df_results[column] = df[column]
        else:
            # the channel groups of one event, with the column types of a run of all the events: the flags are bool
            # without a channel group without an onset, and objects with None otherwise
            for column in df.columns:
                values = self.df_results[column].copy()
                if values.dtype == bool:
                    values = values.astype(object)
                # an empty column (e.g. no onset in all the channel groups) has no type, and fits all
                values.loc[df.index] = None if df[column].isna().all() else df[column].values
                if values.dtype == object and values.map(lambda value: isinstance(value, bool)).all():
                    values = values.astype(bool)
                self.df_results[column] = values

    def _spike_lists(self) -> dict:
        """Returns {index of a row of df_series: its spike times}, for the rows with spikes"""
        return {key: list(spikes) for key, spikes in self.df_spikes.groupby(level=SERIES_INDEX, sort=False)["Spike Time"]}

    def run_inputs(self) -> None:
        """Reads the events (the event list, or the date ranges without one) and the shocks; prints the warnings about
        the shocks"""
        p = self.params
        self.events, self.bg_windows = load_events(p)
        self.shocks, warnings = load_shocks(p)
        self.shocktimes = self.shocks["Shock Time"]
        for warning in warnings + shock_warnings(self.shocks, self.events):
            print(warning)
        self.corrections, self._correction_times = read_corrections(p.file_corrections) if p.file_corrections else ({}, {})
        self._input_end_times = self.events[["End Time", "End Time Source"]].copy()

    def run_data(self, redownload: bool = False) -> None:
        """Loads the flux of the channel groups (from the cache, or downloads it), and resamples it"""
        p = self.params
        os.makedirs(p.dir_saves, exist_ok=True)
        self.energies = load_energies(self.sensors_all,
                                      p.level,
                                      self.events.iloc[0]["Plot Start"],
                                      self.events.iloc[0]["Plot End"],
                                      p.viewings[0],
                                      p.dir_data)
        dfs_flux = download_data(self.events,
                                 p.level,
                                 p.viewings,
                                 p.group_options,
                                 self.energies,
                                 p.dir_data,
                                 p.dir_saves,
                                 p.download_tries,
                                 redownload=redownload)
        self.dfs_flux = resample_flux(dfs_flux, p.resample_freqs)

    def bg_window(self, event_no: int, particle: str = "", sensor: str = "") -> BGWindow:
        """Returns the background window of the series of a particle and sensor in an event, (start, end, source,
        particle, sensor): the window of the particle and sensor, else of the particle, else of the event (particle and
        sensor "" in the result); without a particle, the window of the event"""
        return self.bg_windows.window(event_no, particle, sensor)

    def _check_series_names(self, particle: str, sensor: str) -> None:
        """Raises an error if the particle, or the particle and sensor, are not of the channel groups"""
        if particle and (particle not in self.particles or (sensor and sensor not in self.sensors[particle])):
            pairs = "; ".join(f"{p}: {', '.join(sorted(self.sensors[p]))}" for p in self.particles)
            raise ValueError(f"There are no channel groups of {particle} {sensor}".rstrip()
                             + f". The particles and their sensors are: {pairs}.")

    def _update_event_window(self, event_no: int) -> None:
        """Writes the background window of the event in events"""
        window = self.bg_window(event_no)
        self.events.loc[event_no, ["BG Start", "BG End", "BG Window Source"]] = [window.start, window.end, window.source]

    def set_bg_window(self, event_no: int, start, end, particle: str = "", sensor: str = "") -> None:
        """Sets the background window of an event, or of a particle, or a particle and sensor, in it (source "set"),
        used instead of the one of the event list or the default one; run the onsets and the next steps again
        afterwards"""
        self._check_series_names(particle, sensor)
        self.bg_windows.set(event_no, start, end, particle, sensor)
        self._update_event_window(event_no)

    def reset_bg_window(self, event_no: int, particle: str = "", sensor: str = "") -> None:
        """Sets the background window of an event back to the one of the event list or the default one; the window of
        a particle (and sensor) back to the one of the event list, or else to the window of the event"""
        self._check_series_names(particle, sensor)
        self.bg_windows.reset(event_no, particle, sensor)
        self._update_event_window(event_no)

    def _set_end(self, event_no: int, end, source: str) -> None:
        """Sets the end time of an event, after all its background windows and within its data (up to Plot End)"""
        end = pd.Timestamp(end)
        self.bg_windows.set_end_time(event_no, end)
        self.events.loc[event_no, ["End Time", "End Time Source"]] = [end, source]

    def set_end_time(self, event_no: int, end) -> None:
        """Sets the end time of an event (End Time Source "set"), within its data (up to Plot End); run the onsets and the
        next steps again afterwards"""
        if pd.Timestamp(end) > self.events.loc[event_no, "Plot End"]:
            raise ValueError(f"The end time of event {event_no} ({pd.Timestamp(end)}) is after the end of its data "
                             f"({self.events.loc[event_no, 'Plot End']}). To extend it, change the event list and run "
                             "the data step again.")
        self._set_end(event_no, end, "set")

    def reset_end_time(self, event_no: int) -> None:
        """Sets the end time of an event back to the one of the event list or the default one"""
        self._set_end(event_no, *self._input_end_times.loc[event_no, ["End Time", "End Time Source"]])

    def _series_pairs(self, particle: str = "", sensor: str = "") -> list[tuple]:
        """Returns the (particle, sensor) of the channel groups, of all of them or of a particle (and sensor)"""
        return [(p, s) for p in self.particles for s in sorted(self.sensors[p])
                if (not particle or p == particle) and (not sensor or s == sensor)]

    def bg_window_points(self, event_no: int, particle: str = "", sensor: str = "") -> dict:
        """Returns {resolution: points} of the background windows of an event: the fewest points with data in the
        window of each series, among the series of the event, or of a particle (and sensor), at each resolution"""
        points = {}
        for resample_freq in self.params.resample_freqs:
            points[resample_freq] = min(window_points(self.dfs_flux[p][s][resample_freq].loc[event_no],
                                                      *self.bg_window(event_no, p, s)[:2])
                                        for p, s in self._series_pairs(particle, sensor))
        return points

    def bg_window_series(self, event_no: int) -> dict:
        """Returns {(particle, sensor) of each background window of an event used by a series, ("", "") for the window
        of the event: the (particle, sensor) of the series that use it}"""
        users = {}
        for p, s in self._series_pairs():
            window = self.bg_window(event_no, p, s)
            users.setdefault((window.particle, window.sensor), []).append((p, s))
        return users

    def bg_window_warnings(self, event_no: int) -> list[str]:
        """Returns a warning for each background window of an event, and each resolution, at which a series has fewer
        than MIN_BG_POINTS points in it"""
        warnings = []
        for key, pairs in self.bg_window_series(event_no).items():
            counts = [self.bg_window_points(event_no, p, s) for p, s in pairs]
            for resample_freq in self.params.resample_freqs:
                points = min(count[resample_freq] for count in counts)
                if points < MIN_BG_POINTS:
                    warnings.append(f"The background window of {key_label(event_no, *key)} has {points} "
                                    f"point{'s' if points != 1 else ''} at the {resample_freq.total_seconds() / 60:g} "
                                    f"min resolution in a series (fewer than {MIN_BG_POINTS}).")
        return warnings

    def save_events(self, path: str) -> None:
        """Writes the events with their times and background windows as a CSV event list (Event No, Start Time, BG
        Start, BG End, End Time, and Particle and Sensor if there are windows of particles and sensors), which can be
        given as file_events to use the same times again"""
        rows = self.bg_windows.event_list(self.events[["Start Time", "End Time"]])
        rows.to_csv(path, date_format="%Y-%m-%d %H:%M:%S")

    def run_onsets(self) -> None:
        """Detects the onsets of every resolution and viewing, and chooses one per event and channel group"""
        self.calculate_onsets()
        self.select_onsets()

    def calculate_onsets(self) -> None:
        """Detects the onset of every series (df_series), copies the onset of the reference channel to the series of the
        other particles without one, and checks the data quality after the onsets"""
        p = self.params
        rows = []
        for event_no, particle, sensor, mevlbl, resample_freq, viewing in self._iter_series_keys():
            flux = self._flux(event_no, particle, sensor, mevlbl, resample_freq, viewing)
            window = self.bg_window(event_no, particle, sensor)
            onset_time, _, _, levels = onset_detection_sigma(flux.loc[:self.events.loc[event_no, "End Time"]],
                                                             s=p.onset_sigma,
                                                             n=p.onset_points,
                                                             bg_start=window.start,
                                                             bg_end=window.end)
            rows.append({"Onset Time": onset_time, "BG Level": levels["bg_level"], "Threshold": levels["threshold"]})
        index = pd.MultiIndex.from_tuples(list(self._iter_series_keys()), names=SERIES_INDEX)
        self.df_series = pd.DataFrame(rows, index=index)
        self.df_series["Onset Time"] = self.df_series["Onset Time"].astype("datetime64[ns]")
        self._copy_reference_onsets()
        self._check_quality()

    def _copy_reference_onsets(self) -> None:
        """Gives the series of the other particles without an onset the onset of the reference channel at the same
        resolution and viewing ("Onset Copied")"""
        self.df_series["Onset Copied"] = False
        if self.reference_channel is None:
            return
        index = self.df_series.index
        reference = self.df_series["Onset Time"][(index.get_level_values("Particle") == self.reference_channel["particle"])
                                                 & (index.get_level_values("Sensor") == self.reference_channel["sensor"])
                                                 & (index.get_level_values("Energy Label") == self.reference_channel["mev"])]
        reference = reference.droplevel(["Particle", "Sensor", "Energy Label"])
        reference_onsets = reference.reindex(index.droplevel(["Particle", "Sensor", "Energy Label"])).values
        copied = (self.df_series["Onset Time"].isna().values
                  & (index.get_level_values("Particle") != self.reference_channel["particle"])
                  & ~pd.isna(reference_onsets))
        self.df_series.loc[copied, "Onset Time"] = reference_onsets[copied]
        self.df_series.loc[copied, "Onset Copied"] = True

    def _check_quality(self) -> None:
        """Checks the data quality of each series from its onset to the end of the analysis ("Usable"): the number of
        points, of zero or NaN values, and the ratio of transitions to them"""
        p = self.params
        quality = {"Quality Length": [], "Quality Zeroes": [], "Quality Ratio": [], "Usable": []}
        for key, onset in self.df_series["Onset Time"].items():
            if pd.isna(onset):
                values = (False, None, None, np.nan)
            else:
                flux = self._flux(*key)
                values = quality_analysis(flux[onset:self._analysis_end(key[0], onset)], p.quality_tolerance,
                                          p.quality_adjustable)
            for column, value in zip(("Usable", "Quality Length", "Quality Zeroes", "Quality Ratio"), values):
                quality[column].append(value)
        quality["Quality Length"] = pd.array(quality["Quality Length"], dtype="Int64")
        quality["Quality Zeroes"] = pd.array(quality["Quality Zeroes"], dtype="Int64")
        self._set_series(quality)

    def select_onsets(self, event_no: int | None = None) -> None:
        """Chooses the onset of each event and channel group (df_results), of all the events or of one, the reference
        channel first; the corrected channel groups get the onset of their correction"""
        if event_no is None:
            self.df_results = None
        chosen = {}
        reference_onsets = {}
        channel_rows = list(self._iter_channel_rows(event_no))
        self._check_corrections(dict(channel_rows))
        # the onset of the reference channel limits the onsets of the other channel groups of the event
        is_reference = [self._is_reference(key[1:]) for key, _ in channel_rows]
        for reference_first in (True, False):
            for (key, rows), reference in zip(channel_rows, is_reference):
                if reference != reference_first:
                    continue
                bg_end = self.bg_window(*key[:3]).end
                if key in self.corrections:
                    chosen[key] = corrected_onset(rows, self.corrections[key], bg_end)
                else:
                    chosen[key] = choose_onset(rows, reference_onsets.get(key[0], pd.NaT),
                                               self.params.reference_onset_window, bg_end)
                chosen[key]["Onset Corrected"] = key in self.corrections
                if reference:
                    reference_onsets[key[0]] = chosen[key]["Onset Time"]
        self._set_results(chosen)
        self.df_results[["Quality Length", "Quality Zeroes"]] = self.df_results[["Quality Length", "Quality Zeroes"]] \
            .astype("Int64")

    def _correction_error(self, key: tuple, correction: tuple | None, rows: pd.DataFrame | None) -> str | None:
        """Returns why a correction cannot be applied to the channel group of key, whose rows of df_series are rows
        (None if it is not a channel group of the events), or None"""
        if rows is None:
            return f"event {key[0]} has no channel group {key[3]} {key[1]}/{key[2]}"
        if correction is None:
            return None
        resolution, viewing = correction
        if correction not in rows.index:
            return f"there is no series at the {resolution.total_seconds() / 60:g} min resolution in the {viewing} viewing"
        if pd.isna(rows.loc[correction, "Onset Time"]):
            return (f"the series at the {resolution.total_seconds() / 60:g} min resolution in the {viewing} viewing has no "
                    "onset")
        return None

    def _check_corrections(self, channel_rows: dict) -> None:
        """Leaves out the corrections of the channel groups of channel_rows that cannot be applied, and notes the
        corrections of file_corrections whose onset has changed, with a message"""
        for key in [key for key in self.corrections if key in channel_rows or key[0] not in self.events.index]:
            label = f"The onset correction of event {key[0]}, {key[3]} {key[1]}/{key[2]}"
            if error := self._correction_error(key, self.corrections[key], channel_rows.get(key)):
                print(f"{label} is left out: {error}.")
                del self.corrections[key]
                continue
            if key in self._correction_times and self.corrections[key] is not None:
                onset = channel_rows[key].loc[self.corrections[key], "Onset Time"]
                if onset != self._correction_times[key]:
                    print(f"{label}: the onset of its series is now {onset}, not {self._correction_times[key]}.")
            self._correction_times.pop(key, None)

    def set_onset(self, event_no: int, particle: str, sensor: str, mevlbl: str, resolution=None,
                  viewing: str | None = None) -> None:
        """Sets the onset of a channel group of an event to the detected onset of its series at a resolution
        (timedelta, or minutes) and viewing, or to no onset without them, and runs the steps that have run again for
        this event"""
        if self.df_series is None:
            raise ValueError("There are no onsets: run the onsets first.")
        key = (event_no, particle, sensor, mevlbl)
        if (resolution is None) != (viewing is None):
            raise ValueError("Give both the resolution and the viewing of the onset, or neither for no onset.")
        correction = None
        if resolution is not None:
            resolution = resolution if isinstance(resolution, timedelta) else timedelta(minutes=resolution)
            correction = (pd.Timedelta(resolution), viewing)
        rows = dict(self._iter_channel_rows(event_no)).get(key) if event_no in self.events.index else None
        if error := self._correction_error(key, correction, rows):
            raise ValueError(f"The onset of event {event_no}, {mevlbl} {particle}/{sensor} cannot be set: {error}.")
        self.corrections[key] = correction
        self._run_event(event_no)

    def reset_onset(self, event_no: int, particle: str, sensor: str, mevlbl: str) -> None:
        """Gives a corrected channel group of an event its automatically chosen onset again, and runs the steps that
        have run again for this event"""
        self.corrections.pop((event_no, particle, sensor, mevlbl), None)
        self._run_event(event_no)

    def _run_event(self, event_no: int) -> None:
        """Chooses the onsets of an event again, and runs the next steps that have run for this event"""
        self.select_onsets(event_no)
        if self.df_spikes is not None:
            self.run_spikes(event_no)
        if "Peak Flux" in self.df_series:
            self.calculate_peaks(event_no)
            self.select_peaks(event_no)
        if "Fluence" in self.df_series:
            self.calculate_fluences(event_no)
            self.select_fluences(event_no)

    def save_corrections(self, path: str) -> None:
        """Writes the onset corrections, which can be given as file_corrections to apply them again: one row per
        corrected channel group, with the resolution (minutes), viewing and time of its onset, empty for no onset"""
        rows = []
        for key, correction in self.corrections.items():
            resolution, viewing = correction if correction is not None else (None, None)
            rows.append([*key, None if resolution is None else resolution.total_seconds() / 60, viewing,
                         self.df_results.loc[key, "Onset Time"]])
        pd.DataFrame(rows, columns=CORRECTION_COLUMNS).to_csv(path, index=False, date_format="%Y-%m-%d %H:%M:%S")

    def _is_reference(self, channel: tuple) -> bool:
        """Returns whether (particle, sensor, group label) is the reference channel"""
        rc = self.reference_channel
        return rc is not None and channel == (rc["particle"], rc["sensor"], rc["mev"])

    def run_spikes(self, event_no: int | None = None) -> None:
        """Finds the spikes of every series (of all the events or of one) after the chosen onset of its channel group
        (df_spikes)"""
        p = self.params
        rows = []
        for key in self._series_keys(event_no):
            n, particle, sensor, mevlbl, resample_freq, viewing = key
            onset = self._onset(n, particle, sensor, mevlbl)
            if pd.isna(onset):
                continue
            enddate = peak_search_end(onset, self._analysis_end(n, onset), p.peak_window_min)
            ts = self._flux(*key)[onset:enddate]
            rows += [(*key, spike_time) for spike_time in detect_spikes(ts, threshold=p.spike_thresholds[resample_freq])]
        df_spikes = pd.DataFrame(rows, columns=SERIES_INDEX + ["Spike Time"]).set_index(SERIES_INDEX)
        if event_no is None:
            self.df_spikes = df_spikes
            return
        if df_spikes.empty:
            # without its datetime type, the concatenation would make the spike times objects
            df_spikes = df_spikes.astype(self.df_spikes.dtypes.to_dict())
        # the spikes of the other events stay, in the order of the events
        positions = {n: i for i, n in enumerate(self.events.index)}
        position = self.df_spikes.index.get_level_values("Event No").map(positions)
        self.df_spikes = pd.concat([self.df_spikes[position < positions[event_no]], df_spikes,
                                    self.df_spikes[position > positions[event_no]]])

    def run_peaks(self) -> None:
        """Finds the peak flux of every resolution and viewing, and chooses one per event and channel group"""
        self.calculate_peaks()
        self.select_peaks()

    def calculate_peaks(self, event_no: int | None = None) -> None:
        """Finds the peak flux of every series (df_series, of all the events or of one), from the chosen onset of its
        channel group, without the spikes"""
        spikes = self._spike_lists()
        peaks = {"Peak Flux": [], "Peak Flux Time": []}
        keys = self._series_keys(event_no)
        for key in keys:
            n, particle, sensor, mevlbl, resample_freq, viewing = key
            onset = self._onset(n, particle, sensor, mevlbl)
            pf, pft = None, None
            if not pd.isna(onset):
                enddate = peak_search_end(onset, self._analysis_end(n, onset), self.params.peak_window_min)
                ts = self._flux(*key)[onset:enddate]
                pf, pft = get_peak_flux(remove_spikes(ts, spikes.get(key, []), resample_freq))
            peaks["Peak Flux"].append(pf)
            peaks["Peak Flux Time"].append(pft)
        peaks["Peak Flux"] = pd.array(peaks["Peak Flux"], dtype="float64")
        peaks["Peak Flux Time"] = pd.to_datetime(pd.Series(peaks["Peak Flux Time"], dtype=object)).values
        self._set_series(peaks, None if event_no is None else keys)

    def select_peaks(self, event_no: int | None = None) -> None:
        """Chooses the peak flux of each event (or of one) and channel group (df_results): the highest of the viewings
        at the resolution of the chosen onset"""
        self._set_results({key: choose_peak(rows, self._chosen(*key, "Onset Resolution"))
                           for key, rows in self._iter_channel_rows(event_no)})

    def run_fluences(self) -> None:
        """Calculates the fluence of every resolution in the viewing of the chosen peak, and chooses one per event and
        channel group"""
        self.calculate_fluences()
        self.select_fluences()

    def calculate_fluences(self, event_no: int | None = None) -> None:
        """Calculates the fluence of every series (df_series, of all the events or of one) of the channel groups with a
        peak flux, from the chosen onset to the end of the analysis, without the spikes"""
        p = self.params
        spikes = self._spike_lists()
        fluences = {column: [] for column in FLUENCE_COLUMNS}
        keys = self._series_keys(event_no)
        for key in keys:
            n, particle, sensor, mevlbl, resample_freq, viewing = key
            values = (None, None, None, None)
            if not pd.isna(self._chosen(n, particle, sensor, mevlbl, "Peak Flux")):
                onset = self._onset(n, particle, sensor, mevlbl)
                enddate = self._analysis_end(n, onset)
                ts = remove_spikes(self._flux(*key)[onset:enddate], spikes.get(key, []), resample_freq)
                # a series without points from the onset to the end, e.g. at a coarse resolution with a shock soon
                # after the onset, has no fluence
                if not ts.empty:
                    values = fluence_interval(ts, onset, self._chosen(n, particle, sensor, mevlbl, "Peak Flux Time"),
                                              enddate, p.fluence_peak_fraction, p.fluence_points)
            for column, value in zip(FLUENCE_COLUMNS, values):
                fluences[column].append(value)
        for column in ("Fluence", "Fluence Threshold"):
            fluences[column] = pd.array(fluences[column], dtype="float64")
        for column in ("Fluence Start", "Fluence End"):
            fluences[column] = pd.to_datetime(pd.Series(fluences[column], dtype=object)).values
        self._set_series(fluences, None if event_no is None else keys)

    def select_fluences(self, event_no: int | None = None) -> None:
        """Chooses the fluence of each event (or of one) and channel group (df_results): the largest of the resolutions
        in the viewing of the chosen peak, among those that do not start before the onset"""
        self._set_results({key: choose_fluence(rows, self._onset(*key), self._chosen(*key, "Peak Flux Viewing"))
                           for key, rows in self._iter_channel_rows(event_no)})

    def plot_events(self) -> None:
        """Writes the plot of each event to dir_plots"""
        from matplotlib import pyplot as plt

        from .views import event_plot_filename, plot_event
        os.makedirs(self.params.dir_plots, exist_ok=True)
        for event_no in self.events.index:
            fig = plot_event(self, event_no, filename=pjoin(self.params.dir_plots, event_plot_filename(self, event_no)))
            plt.close(fig)

    def group_energies(self, particle: str, sensor: str, mevlbl: str) -> tuple[float, float]:
        """Returns the low and high energy (MeV) of a channel group: the low energy of its first channel and the high
        energy of its last channel"""
        channels = self.params.group_options[particle][mevlbl]["channels"]
        energies = self.energies[sensor][particle]
        low = energies.loc[channels[0], "Low Energy"]
        high = energies.loc[channels[-1], "Low Energy"] + energies.loc[channels[-1], "Bin Width"]
        # the shortest decimal form of the energies, which are float32 in EPD (23.12, not 23.1200008)
        return float(str(low)), float(str(high))

    def results_table(self) -> pd.DataFrame:
        """Returns df_results as the table of results.csv: one row per event and channel group, with the energy range
        of the group, the background window of its series (BG Start, BG End), where it and the end time of the event
        come from (BG Window Source, End Time Source), and the resolutions in minutes"""
        table = self.df_results[RESULT_COLUMNS].reset_index()
        channels = zip(table["Particle"], table["Sensor"], table["Energy Label"])
        energies = [self.group_energies(*channel) for channel in channels]
        table.insert(4, "Low Energy", [low for low, _ in energies])
        table.insert(5, "High Energy", [high for _, high in energies])
        windows = [self.bg_window(*key) for key in zip(table["Event No"], table["Particle"], table["Sensor"])]
        columns = {"BG Start": [window.start for window in windows], "BG End": [window.end for window in windows],
                   "BG Window Source": [window.source for window in windows],
                   "End Time Source": self.events.loc[table["Event No"], "End Time Source"].values}
        for i, (column, values) in enumerate(columns.items(), start=1):
            table.insert(table.columns.get_loc("Onset Corrected") + i, column, values)
        for column in ("Onset Resolution", "Peak Flux Resolution", "Fluence Resolution"):
            # a column without any resolution (no onset in any channel group) has no timedelta type
            table[column] = np.nan if table[column].isna().all() \
                else pd.to_timedelta(table[column]).dt.total_seconds() / 60
        return table

    def save_results(self) -> None:
        """Writes results.csv, the long table of results_table(), to dir_outputs"""
        p = self.params
        os.makedirs(p.dir_outputs, exist_ok=True)
        self.results_table().to_csv(pjoin(p.dir_outputs, "results.csv"), index=False, date_format="%Y-%m-%d %H:%M:%S")
