"""The analysis: SEPPACT, which runs the steps and keeps their results, and the functions of each step"""
import os
from datetime import datetime, timedelta
from os.path import join as pjoin

import numpy as np
import pandas as pd

from .conf import SEPPACT_parameters
from .data import channel_layout, download_data, load_energies, resample_flux
from .inputs import read_events, read_shocks


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


class SEPPACT:
    """Onset time, peak flux and fluence of the events of an event list

    Run the steps in order: run_inputs(), run_data(), run_onsets(), run_spikes(), run_peaks(), run_fluences(),
    then plot_events() and save_results(). The results stay available as attributes:
    - events: the event list, with the windows filled in
    - shocktimes: the times of the shocks
    - dfs_flux: the flux of the channel groups, per particle, sensor and resolution
    - dfs_events: the onset, peak flux and fluence of every resolution and viewing, per particle, sensor and resolution
    - spikes: the spike times, per particle, sensor, resolution, viewing, channel group and event
    - df_optimals: the chosen onset, peak flux and fluence of each event and channel group
    - df_ts_quality: the data quality of the chosen onset of each event and channel group
    """

    def __init__(self, params: SEPPACT_parameters | None = None) -> None:
        self.params = params if params is not None else SEPPACT_parameters()
        self.params.check()
        self.particles, self.sensors, self.channels, self.sensors_all = channel_layout(self.params.group_options)
        self.reference_channel = self.params.reference_channel
        self.shocktimes = None
        self.events = None
        self.energies = None
        self.dfs_flux = None
        self.dfs_events = None
        self.df_optimals = None
        self.df_ts_quality = None
        self.spikes = None

    def _analysis_end(self, event_no: int, onset: datetime) -> datetime:
        """Returns the end of the analysis of an onset: the end time, or the first shock after the onset"""
        enddate = self.events.loc[event_no, "End Time"]
        if len(shocks := shocks_in_range(self.shocktimes, onset, self.events.loc[event_no, "End Time"])) > 0:
            enddate = shocks[0]
        return enddate

    def _groups(self, particle: str) -> list[str]:
        """Returns the labels of the channel groups of a particle"""
        return list(self.params.group_options[particle].keys())

    def _iter_particle_sensors(self):
        """Yields (particle, sensor) of the channel groups"""
        for particle in self.particles:
            for sensor in self.sensors[particle]:
                yield particle, sensor

    def _iter_series(self):
        """Yields (particle, sensor, resolution) of the tables of dfs_flux and dfs_events"""
        for particle, sensor in self._iter_particle_sensors():
            for resample_freq in self.params.resample_freqs:
                yield particle, sensor, resample_freq

    def _iter_channels(self):
        """Yields (particle, sensor, group label) of the channel groups"""
        for particle, sensor in self._iter_particle_sensors():
            for mevlbl in self._groups(particle):
                yield particle, sensor, mevlbl

    def _iter_event_series(self, particle: str, sensor: str, resample_freq: timedelta):
        """Yields (event number, viewing, group label, flux of the event) of a table of dfs_flux"""
        for i, df_flux in self.dfs_flux[particle][sensor][resample_freq].groupby(level="Event No"):
            for viewing in self.params.viewings:
                for mevlbl in self._groups(particle):
                    yield i, viewing, mevlbl, df_flux

    def _empty_table(self, fields: list[tuple]) -> pd.DataFrame:
        """Returns a table indexed by event number with the columns (particle, sensor, group, *field) of every field"""
        columns = [(particle, sensor, mevlbl, *field)
                   for particle, sensor, mevlbl in self._iter_channels() for field in fields]
        return pd.DataFrame(index=self.events.index, columns=pd.MultiIndex.from_tuples(columns))

    def _onset(self, event_no: int, particle: str, sensor: str, mevlbl: str):
        """Returns the chosen onset of an event and channel group"""
        return self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]

    def _series_after_onset(self,
                            df_flux: pd.DataFrame,
                            event_no: int,
                            viewing: str,
                            mevlbl: str,
                            onset,
                            enddate) -> pd.Series:
        """Returns the flux of an event, viewing and group from the onset to enddate"""
        return df_flux.loc[(event_no, slice(onset, enddate)), (viewing, mevlbl)].droplevel(0, axis="index")

    def _without_spikes(self,
                        ts: pd.Series,
                        event_no: int,
                        particle: str,
                        sensor: str,
                        resample_freq: timedelta,
                        viewing: str,
                        mevlbl: str) -> pd.Series:
        """Returns the series with the spikes of its event, viewing and group removed"""
        spike_times = self.spikes[particle][sensor][resample_freq][viewing][mevlbl].get(event_no, [])
        return remove_spikes(ts, spike_times, resample_freq)

    def run_inputs(self) -> None:
        """Reads the shock list and the event list"""
        p = self.params
        self.shocktimes = read_shocks(pjoin(p.dir_inputs, p.file_shocks))
        self.events = read_events(pjoin(p.dir_inputs, p.file_events), p)

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

    def run_onsets(self) -> None:
        """Detects the onsets of every resolution and viewing, and chooses one per event and channel group"""
        self.calculate_onsets()
        self.select_onsets()

    def _onset_detection_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Returns the onset, background level and threshold of every event and column (viewing, group) of a table of
        dfs_flux"""
        p = self.params
        rows = {}
        for i, df_flux in df.groupby(level="Event No"):
            row = {}
            for column, series in df_flux.items():
                timeseries = series.loc[(i, slice(None, self.events.loc[i, "End Time"]))]
                onset_time, _, _, levels = onset_detection_sigma(timeseries.loc[i],
                                                                 s=p.onset_sigma,
                                                                 n=p.onset_points,
                                                                 bg_start=self.events.loc[i, "BG Start"],
                                                                 bg_end=self.events.loc[i, "BG End"])
                row[(*series.name, "Onset Time")] = onset_time
                row[(*series.name, "BG Level")] = levels["bg_level"]
                row[(*series.name, "Threshold")] = levels["threshold"]
            rows[i] = row
        return pd.DataFrame.from_dict(rows, orient="index")

    def _copy_reference_onsets(self) -> None:
        """Marks the missing onsets ("Dirty Onset"), and gives the groups of the other particles without an onset
        the onset of the reference channel at the same resolution and viewing"""
        for particle, sensor, resample_freq in self._iter_series():
            df = self.dfs_events[particle][sensor][resample_freq]
            for viewing in self.params.viewings:
                for mevlbl in self._groups(particle):
                    df.loc[slice(None), (viewing, mevlbl, "Dirty Onset")] = \
                        pd.isna(df.loc[slice(None), (viewing, mevlbl, "Onset Time")])
                    df.sort_index(axis="columns", inplace=True)
        if self.reference_channel is None:
            return
        ref_particle, ref_sensor, ref_mevlbl = (self.reference_channel["particle"], self.reference_channel["sensor"],
                                                self.reference_channel["mev"])
        for particle, sensor, resample_freq in self._iter_series():
            if particle == ref_particle:
                continue
            df = self.dfs_events[particle][sensor][resample_freq]
            reference = self.dfs_events[ref_particle][ref_sensor][resample_freq]
            for viewing in self.params.viewings:
                for mevlbl in self._groups(particle):
                    dirty = df.loc[slice(None), (viewing, mevlbl, "Dirty Onset")]
                    df.loc[dirty, (viewing, mevlbl, "Onset Time")] = reference.loc[dirty, (viewing, ref_mevlbl, "Onset Time")]

    def calculate_onsets(self) -> None:
        """Detects the onsets of every resolution and viewing (dfs_events), with the onsets copied from the reference
        channel"""
        self.dfs_events = {particle: {sensor: {} for sensor in self.sensors[particle]} for particle in self.particles}
        for particle, sensor, resample_freq in self._iter_series():
            self.dfs_events[particle][sensor][resample_freq] = \
                self._onset_detection_df(self.dfs_flux[particle][sensor][resample_freq])
        self._copy_reference_onsets()

    def select_onsets(self) -> None:
        """Chooses the onset of each event and channel group (df_optimals), the reference channel first"""
        col_subsets = {
            "Onset Time": ["Onset Time", "Onset Copied", "Onset at BG End"],
            "Peak Flux": ["Peak Flux", "Peak Flux Time"],
            "Fluence": ["Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"]
        }
        self.df_optimals = self._empty_table([(col1, col2) for col1 in ["Onset Time", "Peak Flux", "Fluence"]
                                              for col2 in col_subsets[col1] + ["Resolution", "Viewing"]])
        self.df_ts_quality = self._empty_table([(col,) for col in ["Length", "Zeroes", "Ratio"]])
        for event_no in self.df_optimals.index:
            for particle in reference_iter(self.particles, self.reference_channel):
                for sensor in reference_iter(self.sensors[particle], self.reference_channel):
                    for mevlbl in reference_iter(self.params.group_options[particle].keys(), self.reference_channel):
                        self._select_onset(event_no, particle, sensor, mevlbl)

    def _usable_series(self, event_no: int, particle: str, sensor: str, mevlbl: str) -> dict:
        """Returns the data quality of the series with an onset that can be used, per resolution: a list of dicts with
        the viewing, the number of points, of zero or NaN values, and the ratio of transitions to them"""
        p = self.params
        # empty until the reference channel, which is processed first, has its onset
        reference_onset = None
        if self.reference_channel is not None:
            reference_onset = self._onset(event_no, self.reference_channel["particle"], self.reference_channel["sensor"],
                                          self.reference_channel["mev"])
        eligible_tss = {resample_freq: [] for resample_freq in p.resample_freqs}
        for resample_freq in p.resample_freqs:
            for viewing in p.viewings:
                onset = self.dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Onset Time")]
                if pd.isna(onset):
                    continue
                if not pd.isna(reference_onset) and abs(onset - reference_onset) > p.reference_onset_window:
                    continue
                timeseries = self.dfs_flux[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl)]
                timeseries = timeseries[onset:self._analysis_end(event_no, onset)]
                qualified, ts_length, n_zeroes, ratio = quality_analysis(timeseries, p.quality_tolerance, p.quality_adjustable)
                if qualified:
                    eligible_tss[resample_freq].append({"viewing": viewing, "ts_length": ts_length, "n_zeroes": n_zeroes,
                                                        "ratio": ratio})
        return eligible_tss

    def _best_resolution_and_viewing(self,
                                     eligible_tss: dict,
                                     event_no: int,
                                     particle: str,
                                     sensor: str,
                                     mevlbl: str) -> tuple:
        """Returns the finest resolution with a usable series, and its viewing with the earliest onset"""
        for resample_freq in self.params.resample_freqs:
            if len(eligible_tss[resample_freq]) == 0:
                continue
            onsets = self.dfs_events[particle][sensor][resample_freq]
            best_viewing = None
            for quality_metrics in eligible_tss[resample_freq]:
                viewing = quality_metrics["viewing"]
                onset = onsets.loc[event_no, (viewing, mevlbl, "Onset Time")]
                if best_viewing is None or onset < onsets.loc[event_no, (best_viewing, mevlbl, "Onset Time")]:
                    best_viewing = viewing
            return resample_freq, best_viewing
        return None, None

    def _select_onset(self, event_no: int, particle: str, sensor: str, mevlbl: str) -> None:
        """Chooses the onset of one event and channel group, with its flags and data quality"""
        eligible_tss = self._usable_series(event_no, particle, sensor, mevlbl)
        best_res, best_viewing = self._best_resolution_and_viewing(eligible_tss, event_no, particle, sensor, mevlbl)
        column = (particle, sensor, mevlbl, "Onset Time")
        self.df_optimals.loc[event_no, (*column, "Resolution")] = best_res
        self.df_optimals.loc[event_no, (*column, "Viewing")] = best_viewing
        if best_res is None:
            self.df_optimals.loc[event_no, (*column, "Onset Time")] = None
            for field in ("Length", "Zeroes", "Ratio"):
                self.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, field)] = None
            return
        onsets = self.dfs_events[particle][sensor][best_res]
        onset_time = onsets.loc[event_no, (best_viewing, mevlbl, "Onset Time")]
        self.df_optimals.loc[event_no, (*column, "Onset Time")] = onset_time
        # an onset is copied when the channel has none and the reference channel has one;
        # an onset at the end of the background may have started inside it
        if not pd.isna(onset_time):
            self.df_optimals.loc[event_no, (*column, "Onset Copied")] = \
                bool(onsets.loc[event_no, (best_viewing, mevlbl, "Dirty Onset")])
            self.df_optimals.loc[event_no, (*column, "Onset at BG End")] = onset_time <= self.events.loc[event_no, "BG End"]
        qties = [x for x in eligible_tss[best_res] if x["viewing"] == best_viewing][0]
        self.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Length")] = qties["ts_length"]
        self.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Zeroes")] = qties["n_zeroes"]
        self.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Ratio")] = qties["ratio"]

    def run_spikes(self) -> None:
        """Finds the spikes of every resolution and viewing after the chosen onset"""
        p = self.params
        self.spikes = {
            particle: {
                sensor: {
                    resample_freq: {viewing: {mevlbl: {} for mevlbl in self._groups(particle)} for viewing in p.viewings}
                    for resample_freq in p.resample_freqs
                }
                for sensor in self.sensors[particle]
            }
            for particle in self.particles
        }
        for particle, sensor, resample_freq in self._iter_series():
            for i, viewing, mevlbl, df_flux in self._iter_event_series(particle, sensor, resample_freq):
                onset = self._onset(i, particle, sensor, mevlbl)
                if pd.isna(onset):
                    continue
                enddate = peak_search_end(onset, self._analysis_end(i, onset), p.peak_window_min)
                ts = self._series_after_onset(df_flux, i, viewing, mevlbl, onset, enddate)
                detected_spikes = detect_spikes(ts, threshold=p.spike_thresholds[resample_freq])
                if len(detected_spikes) > 0:
                    self.spikes[particle][sensor][resample_freq][viewing][mevlbl][i] = detected_spikes

    def run_peaks(self) -> None:
        """Finds the peak flux of every resolution and viewing, and chooses one per event and channel group"""
        self.calculate_peaks()
        self.select_peaks()

    def calculate_peaks(self) -> None:
        """Finds the peak flux of every resolution and viewing (dfs_events), without the spikes"""
        for particle, sensor, resample_freq in self._iter_series():
            df_events = self.dfs_events[particle][sensor][resample_freq]
            for i, viewing, mevlbl, df_flux in self._iter_event_series(particle, sensor, resample_freq):
                onset = self._onset(i, particle, sensor, mevlbl)
                if pd.isna(onset):
                    df_events.loc[i, (viewing, mevlbl, "Peak Flux")] = None
                    df_events.loc[i, (viewing, mevlbl, "Peak Flux Time")] = None
                    continue
                enddate = peak_search_end(onset, self._analysis_end(i, onset), self.params.peak_window_min)
                ts = self._series_after_onset(df_flux, i, viewing, mevlbl, onset, enddate)
                pf, pft = get_peak_flux(self._without_spikes(ts, i, particle, sensor, resample_freq, viewing, mevlbl))
                df_events.loc[i, (viewing, mevlbl, "Peak Flux")] = pf
                df_events.loc[i, (viewing, mevlbl, "Peak Flux Time")] = pft
            df_events.sort_index(axis="columns", inplace=True)

    def select_peaks(self) -> None:
        """Chooses the peak flux of each event and channel group (df_optimals): the highest of the viewings at the
        resolution of the chosen onset"""
        for event_no in self.df_optimals.index:
            for particle, sensor, mevlbl in self._iter_channels():
                self._select_peak(event_no, particle, sensor, mevlbl)

    def _select_peak(self, event_no: int, particle: str, sensor: str, mevlbl: str) -> None:
        """Chooses the peak flux of one event and channel group"""
        column = (particle, sensor, mevlbl, "Peak Flux")
        resample_freq = self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Resolution")]
        max_pf = None
        best_viewing = None
        if not pd.isna(resample_freq):
            for viewing in self.params.viewings:
                pf = self.dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Peak Flux")]
                if not pd.isna(pf) and (pd.isna(max_pf) or pf > max_pf):
                    max_pf = pf
                    best_viewing = viewing
        if pd.isna(max_pf):
            for field in ("Resolution", "Viewing", "Peak Flux", "Peak Flux Time"):
                self.df_optimals.loc[event_no, (*column, field)] = None
            return
        self.df_optimals.loc[event_no, (*column, "Resolution")] = resample_freq
        self.df_optimals.loc[event_no, (*column, "Viewing")] = best_viewing
        self.df_optimals.loc[event_no, (*column, "Peak Flux")] = max_pf
        self.df_optimals.loc[event_no, (*column, "Peak Flux Time")] = \
            self.dfs_events[particle][sensor][resample_freq].loc[event_no, (best_viewing, mevlbl, "Peak Flux Time")]

    def run_fluences(self) -> None:
        """Calculates the fluence of every resolution in the viewing of the chosen peak, and chooses one per event and
        channel group"""
        self.calculate_fluences()
        self.select_fluences()

    def calculate_fluences(self) -> None:
        """Calculates the fluence of every resolution and viewing (dfs_events), without the spikes"""
        p = self.params
        for particle, sensor, resample_freq in self._iter_series():
            df_events = self.dfs_events[particle][sensor][resample_freq]
            for i, viewing, mevlbl, df_flux in self._iter_event_series(particle, sensor, resample_freq):
                pf = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux")]
                if pd.isna(pf):
                    for field in ("Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"):
                        df_events.loc[i, (viewing, mevlbl, field)] = None
                    continue
                onset = self._onset(i, particle, sensor, mevlbl)
                pft = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux Time")]
                enddate = self._analysis_end(i, onset)
                ts = self._series_after_onset(df_flux, i, viewing, mevlbl, onset, enddate)
                ts = self._without_spikes(ts, i, particle, sensor, resample_freq, viewing, mevlbl)
                values = fluence_interval(ts, onset, pft, enddate, p.fluence_peak_fraction, p.fluence_points)
                for field, value in zip(("Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"), values):
                    df_events.loc[i, (viewing, mevlbl, field)] = value
            df_events.sort_index(axis="columns", inplace=True)

    def select_fluences(self) -> None:
        """Chooses the fluence of each event and channel group (df_optimals): the largest of the resolutions in the
        viewing of the chosen peak, among those that do not start before the onset"""
        for event_no in self.df_optimals.index:
            for particle, sensor, mevlbl in self._iter_channels():
                self._select_fluence(event_no, particle, sensor, mevlbl)

    def _select_fluence(self, event_no: int, particle: str, sensor: str, mevlbl: str) -> None:
        """Chooses the fluence of one event and channel group"""
        column = (particle, sensor, mevlbl, "Fluence")
        onset = self._onset(event_no, particle, sensor, mevlbl)
        viewing = self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Viewing")]
        max_fluence = None
        best_res = None
        if not (pd.isna(viewing) or pd.isna(onset)):
            for resample_freq in self.params.resample_freqs:
                df_events = self.dfs_events[particle][sensor][resample_freq]
                fluence = df_events.loc[event_no, (viewing, mevlbl, "Fluence")]
                if pd.isna(fluence) or df_events.loc[event_no, (viewing, mevlbl, "Fluence Start")] < onset:
                    continue
                if pd.isna(max_fluence) or fluence > max_fluence:
                    max_fluence = fluence
                    best_res = resample_freq
        fields = ("Fluence Start", "Fluence End", "Fluence Threshold")
        if best_res is None:
            for field in ("Resolution", "Fluence") + fields:
                self.df_optimals.loc[event_no, (*column, field)] = None
            self.df_optimals.loc[event_no, (*column, "Viewing")] = None if pd.isna(viewing) or pd.isna(onset) else viewing
            return
        self.df_optimals.loc[event_no, (*column, "Resolution")] = best_res
        self.df_optimals.loc[event_no, (*column, "Viewing")] = viewing
        self.df_optimals.loc[event_no, (*column, "Fluence")] = max_fluence
        for field in fields:
            self.df_optimals.loc[event_no, (*column, field)] = \
                self.dfs_events[particle][sensor][best_res].loc[event_no, (viewing, mevlbl, field)]

    def plot_events(self) -> None:
        """Writes the plot of each event to dir_plots"""
        from matplotlib import pyplot as plt

        from .views import event_plot_filename, plot_event
        os.makedirs(self.params.dir_plots, exist_ok=True)
        for event_no in self.df_optimals.index:
            fig = plot_event(self, event_no, filename=pjoin(self.params.dir_plots, event_plot_filename(self, event_no)))
            plt.close(fig)

    def save_results(self) -> None:
        """Writes optimals.xlsx (resolutions in minutes) to dir_outputs"""
        p = self.params
        os.makedirs(p.dir_outputs, exist_ok=True)
        self.df_optimals.map(lambda x: x.total_seconds()/60 if not pd.isna(x) and type(x) is timedelta else x) \
            .to_excel(pjoin(p.dir_outputs, "optimals.xlsx"))
