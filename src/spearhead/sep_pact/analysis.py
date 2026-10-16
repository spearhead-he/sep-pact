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


def onset_detection_sigma(series: pd.Series,
                          s: float,
                          n: int,
                          bg_start: int | datetime,
                          bg_end: int | datetime) -> tuple:
    """Returns the onset time (None if no event is detected) and a dict with the background level and the threshold"""
    if type(bg_start) is int:
        bg_start = series.index[bg_start]
    if type(bg_end) is int:
        bg_end = series.index[bg_end]
    bg_level = (bg_series := series[bg_start:bg_end]).mean()
    threshold = bg_level + s * bg_series.std()
    onset_time = None
    data_series = series[bg_end:]

    streak = 0
    for index, value in data_series.items():
        if value > threshold:
            streak += 1
            if onset_time is None:
                onset_time = index
        else:
            streak = 0
            onset_time = None

        if streak >= n:
            break

    if streak < n:
        onset_time = None

    if onset_time is not None:
        onset_value = data_series.loc[onset_time]
        for index, value in data_series.loc[:onset_time - timedelta(milliseconds=1)].iloc[::-1].items():
            if value < onset_value:
                onset_time = index
                onset_value = value
            else:
                break

    return (
        onset_time,
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
    pft = peak_time
    pf_temp1 = None
    pft_temp1 = None
    pf_temp2 = None
    pft_temp2 = None
    if not ts.loc[:pft].empty:
        pf_temp1 = ts.loc[:pft].values[-1]
        pft_temp1 = ts.loc[:pft].index[-1]
    if not ts.loc[pft:].empty:
        pf_temp2 = ts.loc[pft:].values[0]
        pft_temp2 = ts.loc[pft:].index[0]
    if pf_temp1 is None:
        pf = pf_temp2
        pft = pft_temp2
    elif pf_temp2 is None:
        pf = pf_temp1
        pft = pft_temp1
    else:
        if pf_temp1 > pf_temp2:
            pf = pf_temp1
            pft = pft_temp1
        else:
            pf = pf_temp2
            pft = pft_temp2
    fluence_start = None
    fluence_end = None
    threshold = pf * peak_fraction
    needed_points = points
    while fluence_start is None and needed_points > 0:
        n = 0
        for j in range(len(ts.loc[:pft]) - 1, -1, -1):
            v = ts.iloc[j]
            if v <= threshold:
                n += 1
                if n == needed_points:
                    fluence_start = ts.index[j + (needed_points - 1)]
                    break
            else:
                n = 0
        needed_points -= 1
    if fluence_start is None or fluence_start < onset:
        fluence_start = onset
    needed_points = points
    while fluence_end is None and needed_points > 0:
        n = 0
        try:
            for j, v in enumerate(ts.loc[pft:], start=list(ts.index).index(ts.loc[pft:].index[0])):
                if v <= threshold:
                    n += 1
                    if n == needed_points:
                        fluence_end = ts.index[j - (needed_points - 1)]
                        break
                else:
                    n = 0
            needed_points -= 1
        except IndexError:
            # Due to resolution differences, the peak flux point is beyond the end of the timeseries
            break
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
    - df_means: the mean flux of the background windows
    - dfs_events: the onset, peak flux and fluence of every resolution and viewing, per particle, sensor and resolution
    - spikes: the spike times, per particle, sensor, resolution, viewing, channel group and event
    - df_optimals: the chosen onset, peak flux and fluence of each event and channel group
    - df_latest_onsets: the latest usable onset of each event and channel group
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
        self.df_means = None
        self.dfs_events = None
        self.df_optimals = None
        self.df_ts_quality = None
        self.df_latest_onsets = None
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

    def run_inputs(self) -> None:
        """Reads the shock list and the event list"""
        p = self.params
        self.shocktimes = read_shocks(pjoin(p.dir_inputs, p.file_shocks))
        self.events = read_events(pjoin(p.dir_inputs, p.file_events), p)

    def run_data(self, redownload: bool = False) -> None:
        """Loads the flux of the channel groups (from the cache, or downloads it), resamples it, and calculates the
        background means"""
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

        df_means = self.events[["BG Start", "BG End"]].copy()
        for i in df_means.index:
            for particle in self.particles:
                for sensor in self.sensors[particle]:
                    for mevlbl in self._groups(particle):
                        for resample_freq in p.resample_freqs:
                            for viewing in p.viewings:
                                df_means.loc[i, f"{mevlbl} {particle} {viewing} {int(resample_freq.seconds/60)}m"] = \
                                    self.dfs_flux[particle][sensor][resample_freq].loc[i, (viewing, mevlbl)].mean()
        self.df_means = df_means

    def run_onsets(self) -> None:
        """Detects the onsets of every resolution and viewing, and chooses one per event and channel group"""
        p = self.params
        dfs_events = {
            particle: {
                sensor: {resample_freq: pd.DataFrame([]) for resample_freq in p.resample_freqs}
                for sensor in self.sensors[particle]
            }
            for particle in self.particles
        }
        col_subsets = {
            "Onset Time": ["Onset Time", "Onset Copied", "Onset at BG End"],
            "Peak Flux": ["Peak Flux", "Peak Flux Time"],
            "Fluence": ["Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"]
        }
        columns = [(particle, sensor, mevlbl, col1, col2)
                   for particle in self.particles
                   for sensor in self.sensors[particle]
                   for mevlbl in self._groups(particle)
                   for col1 in ["Onset Time", "Peak Flux", "Fluence"]
                   for col2 in col_subsets[col1] + ["Resolution", "Viewing"]]
        df_optimals = pd.DataFrame(index=self.events.index, columns=pd.MultiIndex.from_tuples(columns))

        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for resample_freq in p.resample_freqs:
                    rows = {}
                    for i, df_flux in self.dfs_flux[particle][sensor][resample_freq].groupby(level="Event No"):
                        row = {}
                        for column, series in df_flux.items():
                            timeseries = series.loc[(i, slice(None, self.events.loc[i, "End Time"]))]
                            onset = onset_detection_sigma(timeseries.loc[i],
                                                          s=p.onset_sigma,
                                                          n=p.onset_points,
                                                          bg_start=self.events.loc[i, "BG Start"],
                                                          bg_end=self.events.loc[i, "BG End"])
                            row[(*series.name, "Onset Time")] = onset[0]
                            row[(*series.name, "BG Level")] = onset[1]["bg_level"]
                            row[(*series.name, "Threshold")] = onset[1]["threshold"]
                        rows[i] = row
                    dfs_events[particle][sensor][resample_freq] = pd.DataFrame.from_dict(rows, orient="index")

        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for resample_freq in p.resample_freqs:
                    df = dfs_events[particle][sensor][resample_freq]
                    for viewing in p.viewings:
                        for mevlbl in self._groups(particle):
                            df.loc[slice(None), (viewing, mevlbl, "Dirty Onset")] = \
                                pd.isna(df.loc[slice(None), (viewing, mevlbl, "Onset Time")])
                            df.sort_index(axis="columns", inplace=True)

        if self.reference_channel is not None:
            ref_particle, ref_sensor, ref_mevlbl = (self.reference_channel["particle"], self.reference_channel["sensor"],
                                                    self.reference_channel["mev"])
            for particle in self.particles:
                if particle == ref_particle:
                    continue
                for sensor in self.sensors[particle]:
                    for resample_freq in p.resample_freqs:
                        for viewing in p.viewings:
                            for mevlbl in self._groups(particle):
                                df = dfs_events[particle][sensor][resample_freq]
                                dirty = df.loc[slice(None), (viewing, mevlbl, "Dirty Onset")]
                                reference = dfs_events[ref_particle][ref_sensor][resample_freq]
                                df.loc[dirty, (viewing, mevlbl, "Onset Time")] = \
                                    reference.loc[dirty, (viewing, ref_mevlbl, "Onset Time")]

        df_ts_quality = pd.DataFrame(index=df_optimals.index,
                                     columns=pd.MultiIndex.from_tuples([(particle, sensor, mevlbl, col)
                                                                        for particle in self.particles
                                                                        for sensor in self.sensors[particle]
                                                                        for mevlbl in self._groups(particle)
                                                                        for col in ["Length", "Zeroes", "Ratio"]]))
        columns = [(particle, sensor, mevlbl, col)
                   for particle in self.particles
                   for sensor in self.sensors[particle]
                   for mevlbl in self._groups(particle)
                   for col in ["Onset Time", "Resolution", "Viewing"]]
        df_latest_onsets = pd.DataFrame(index=df_optimals.index, columns=pd.MultiIndex.from_tuples(columns))

        for event_no in df_optimals.index:
            for particle in reference_iter(self.particles, self.reference_channel):
                for sensor in reference_iter(self.sensors[particle], self.reference_channel):
                    for mevlbl in reference_iter(self.params.group_options[particle].keys(), self.reference_channel):
                        self._choose_onset(event_no, particle, sensor, mevlbl,
                                           dfs_events, df_optimals, df_ts_quality, df_latest_onsets)

        self.dfs_events = dfs_events
        self.df_optimals = df_optimals
        self.df_ts_quality = df_ts_quality
        self.df_latest_onsets = df_latest_onsets

    def _choose_onset(self,
                      event_no: int,
                      particle: str,
                      sensor: str,
                      mevlbl: str,
                      dfs_events: dict,
                      df_optimals: pd.DataFrame,
                      df_ts_quality: pd.DataFrame,
                      df_latest_onsets: pd.DataFrame) -> None:
        """Chooses the onset of one event and channel group, and its latest usable onset"""
        p = self.params
        # empty until the reference channel, which is processed first, has its onset
        reference_onset = None
        if self.reference_channel is not None:
            reference_onset = df_optimals.loc[event_no, (self.reference_channel["particle"],
                                                         self.reference_channel["sensor"],
                                                         self.reference_channel["mev"],
                                                         "Onset Time",
                                                         "Onset Time")]
        eligible_tss = {resample_freq: [] for resample_freq in p.resample_freqs}
        for resample_freq in p.resample_freqs:
            for viewing in p.viewings:
                timeseries = self.dfs_flux[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl)]
                onset = dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Onset Time")]
                if pd.isna(onset):
                    continue
                if not pd.isna(reference_onset) and abs(onset - reference_onset) > p.reference_onset_window:
                    continue
                enddate = self._analysis_end(event_no, onset)
                timeseries = timeseries[onset:enddate]
                qualified, ts_length, n_zeroes, ratio = quality_analysis(timeseries, p.quality_tolerance, p.quality_adjustable)
                if qualified:
                    eligible_tss[resample_freq].append({"viewing": viewing,
                                                        "ts_length": ts_length,
                                                        "n_zeroes": n_zeroes,
                                                        "ratio": ratio})

        best_res = None
        best_viewing = None
        for resample_freq in p.resample_freqs:
            if len(eligible_tss[resample_freq]) == 0:
                continue
            best_res = resample_freq
            for quality_metrics in eligible_tss[resample_freq]:
                viewing = quality_metrics["viewing"]
                if pd.isna(best_viewing):
                    best_viewing = viewing
                    continue
                viewing_ot = dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Onset Time")]
                best_viewing_ot = dfs_events[particle][sensor][best_res].loc[event_no, (best_viewing, mevlbl, "Onset Time")]
                if viewing_ot < best_viewing_ot:
                    best_viewing = viewing
            break
        column = (particle, sensor, mevlbl, "Onset Time")
        df_optimals.loc[event_no, (*column, "Resolution")] = best_res
        df_optimals.loc[event_no, (*column, "Viewing")] = best_viewing
        try:
            df_optimals.loc[event_no, (*column, "Onset Time")] = \
                dfs_events[particle][sensor][best_res].loc[event_no, (best_viewing, mevlbl, "Onset Time")]
        except KeyError:
            df_optimals.loc[event_no, (*column, "Onset Time")] = None
        # an onset is copied when the channel has none and the reference channel has one;
        # an onset at the end of the background may have started inside it
        onset_time = df_optimals.loc[event_no, (*column, "Onset Time")]
        if not pd.isna(onset_time):
            df_optimals.loc[event_no, (*column, "Onset Copied")] = \
                bool(dfs_events[particle][sensor][best_res].loc[event_no, (best_viewing, mevlbl, "Dirty Onset")])
            df_optimals.loc[event_no, (*column, "Onset at BG End")] = onset_time <= self.events.loc[event_no, "BG End"]

        try:
            qties = [x for x in eligible_tss[best_res] if x["viewing"] == best_viewing][0]
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Length")] = qties["ts_length"]
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Zeroes")] = qties["n_zeroes"]
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Ratio")] = qties["ratio"]
        except KeyError:
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Length")] = None
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Zeroes")] = None
            df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Ratio")] = None

        latest_res = None
        latest_viewing = None
        latest_onset = None
        for resample_freq in p.resample_freqs:
            for quality_metrics in eligible_tss[resample_freq]:
                viewing = quality_metrics["viewing"]
                onset = dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Onset Time")]
                if pd.isna(latest_onset) or onset > latest_onset:
                    latest_res = resample_freq
                    latest_viewing = viewing
                    latest_onset = onset
        df_latest_onsets.loc[event_no, (particle, sensor, mevlbl, "Onset Time")] = latest_onset
        df_latest_onsets.loc[event_no, (particle, sensor, mevlbl, "Resolution")] = latest_res
        df_latest_onsets.loc[event_no, (particle, sensor, mevlbl, "Viewing")] = latest_viewing

    def run_spikes(self) -> None:
        """Finds the spikes of every resolution and viewing after the chosen onset"""
        p = self.params
        spikes = {
            particle: {
                sensor: {
                    resample_freq: {
                        viewing: {mevlbl: {} for mevlbl in self._groups(particle)}
                        for viewing in p.viewings
                    }
                    for resample_freq in p.resample_freqs
                }
                for sensor in self.sensors[particle]
            }
            for particle in self.particles
        }
        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for resample_freq in p.resample_freqs:
                    for i, df_flux in self.dfs_flux[particle][sensor][resample_freq].groupby(level="Event No"):
                        for viewing in p.viewings:
                            for mevlbl in self._groups(particle):
                                onset = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]
                                if pd.isna(onset):
                                    continue
                                enddate = peak_search_end(onset, self._analysis_end(i, onset), p.peak_window_min)
                                ts = df_flux.loc[(i, slice(onset, enddate)), (viewing, mevlbl)].droplevel(0, axis="index")
                                detected_spikes = detect_spikes(ts, threshold=p.spike_thresholds[resample_freq])
                                if len(detected_spikes) > 0:
                                    spikes[particle][sensor][resample_freq][viewing][mevlbl][i] = detected_spikes
        self.spikes = spikes

    def run_peaks(self) -> None:
        """Finds the peak flux of every resolution and viewing, and chooses one per event and channel group"""
        p = self.params
        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for resample_freq in p.resample_freqs:
                    df_events = self.dfs_events[particle][sensor][resample_freq]
                    for i, df_flux in self.dfs_flux[particle][sensor][resample_freq].groupby(level="Event No"):
                        for viewing in p.viewings:
                            for mevlbl in self._groups(particle):
                                onset = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]
                                if pd.isna(onset):
                                    df_events.loc[i, (viewing, mevlbl, "Peak Flux")] = None
                                    df_events.loc[i, (viewing, mevlbl, "Peak Flux Time")] = None
                                    continue
                                enddate = peak_search_end(onset, self._analysis_end(i, onset), p.peak_window_min)
                                ts = df_flux.loc[(i, slice(onset, enddate)), (viewing, mevlbl)].droplevel(0, axis="index")
                                spike_times = self.spikes[particle][sensor][resample_freq][viewing][mevlbl].get(i, [])
                                ts = remove_spikes(ts, spike_times, resample_freq)
                                pf, pft = get_peak_flux(ts)
                                df_events.loc[i, (viewing, mevlbl, "Peak Flux")] = pf
                                df_events.loc[i, (viewing, mevlbl, "Peak Flux Time")] = pft
                    df_events.sort_index(axis="columns", inplace=True)

        for event_no in self.df_optimals.index:
            for particle in self.particles:
                for sensor in self.sensors[particle]:
                    for mevlbl in self._groups(particle):
                        column = (particle, sensor, mevlbl, "Peak Flux")
                        resample_freq = self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Resolution")]
                        if pd.isna(resample_freq):
                            for field in ("Resolution", "Viewing", "Peak Flux", "Peak Flux Time"):
                                self.df_optimals.loc[event_no, (*column, field)] = None
                            continue
                        max_pf = None
                        best_viewing = None
                        for viewing in p.viewings:
                            pf = self.dfs_events[particle][sensor][resample_freq].loc[event_no, (viewing, mevlbl, "Peak Flux")]
                            if pd.isna(pf):
                                continue
                            if pd.isna(max_pf) or pf > max_pf:
                                max_pf = pf
                                best_viewing = viewing
                        if pd.isna(max_pf):
                            resample_freq = None
                        self.df_optimals.loc[event_no, (*column, "Resolution")] = resample_freq
                        self.df_optimals.loc[event_no, (*column, "Viewing")] = best_viewing
                        self.df_optimals.loc[event_no, (*column, "Peak Flux")] = max_pf
                        try:
                            df_events = self.dfs_events[particle][sensor][resample_freq]
                            self.df_optimals.loc[event_no, (*column, "Peak Flux Time")] = \
                                df_events.loc[event_no, (best_viewing, mevlbl, "Peak Flux Time")]
                        except KeyError:
                            self.df_optimals.loc[event_no, (*column, "Peak Flux Time")] = None

    def run_fluences(self) -> None:
        """Calculates the fluence of every resolution in the viewing of the chosen peak, and chooses one per event and
        channel group"""
        p = self.params
        for particle in self.particles:
            for sensor in self.sensors[particle]:
                for resample_freq in p.resample_freqs:
                    df_events = self.dfs_events[particle][sensor][resample_freq]
                    for i, df_flux in self.dfs_flux[particle][sensor][resample_freq].groupby(level="Event No"):
                        for viewing in p.viewings:
                            for mevlbl in self._groups(particle):
                                onset = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]
                                pf = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux")]
                                pft = self.df_optimals.loc[i, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux Time")]
                                if pd.isna(pf):
                                    for field in ("Fluence", "Fluence Start", "Fluence End", "Fluence Threshold"):
                                        df_events.loc[i, (viewing, mevlbl, field)] = None
                                    continue
                                enddate = self._analysis_end(i, onset)
                                ts = df_flux.loc[(i, slice(onset, enddate)), (viewing, mevlbl)].droplevel(0, axis="index")
                                spike_times = self.spikes[particle][sensor][resample_freq][viewing][mevlbl].get(i, [])
                                ts = remove_spikes(ts, spike_times, resample_freq)
                                fluence, fluence_start, fluence_end, threshold = fluence_interval(ts, onset, pft, enddate,
                                                                                                  p.fluence_peak_fraction,
                                                                                                  p.fluence_points)
                                df_events.loc[i, (viewing, mevlbl, "Fluence")] = fluence
                                df_events.loc[i, (viewing, mevlbl, "Fluence Start")] = fluence_start
                                df_events.loc[i, (viewing, mevlbl, "Fluence End")] = fluence_end
                                df_events.loc[i, (viewing, mevlbl, "Fluence Threshold")] = threshold
                    df_events.sort_index(axis="columns", inplace=True)

        for event_no in self.df_optimals.index:
            for particle in self.particles:
                for sensor in self.sensors[particle]:
                    for mevlbl in self._groups(particle):
                        column = (particle, sensor, mevlbl, "Fluence")
                        onset = self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]
                        viewing = self.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Viewing")]
                        if pd.isna(viewing) or pd.isna(onset):
                            for field in ("Resolution", "Viewing", "Fluence", "Fluence Start", "Fluence End",
                                          "Fluence Threshold"):
                                self.df_optimals.loc[event_no, (*column, field)] = None
                            continue
                        max_fluence = None
                        best_res = None
                        for resample_freq in p.resample_freqs:
                            df_events = self.dfs_events[particle][sensor][resample_freq]
                            fluence = df_events.loc[event_no, (viewing, mevlbl, "Fluence")]
                            fluence_start = df_events.loc[event_no, (viewing, mevlbl, "Fluence Start")]
                            if pd.isna(fluence) or fluence_start < onset:
                                continue
                            if pd.isna(max_fluence) or fluence > max_fluence:
                                max_fluence = fluence
                                best_res = resample_freq
                        self.df_optimals.loc[event_no, (*column, "Resolution")] = best_res
                        self.df_optimals.loc[event_no, (*column, "Viewing")] = viewing
                        self.df_optimals.loc[event_no, (*column, "Fluence")] = max_fluence
                        try:
                            for field in ("Fluence Start", "Fluence End", "Fluence Threshold"):
                                self.df_optimals.loc[event_no, (*column, field)] = \
                                    self.dfs_events[particle][sensor][best_res].loc[event_no, (viewing, mevlbl, field)]
                        except KeyError:
                            for field in ("Fluence Start", "Fluence End", "Fluence Threshold"):
                                self.df_optimals.loc[event_no, (*column, field)] = None

    def plot_events(self) -> None:
        """Writes the plot of each event to dir_plots"""
        from matplotlib import pyplot as plt

        from .views import plot_event, plot_filename
        os.makedirs(self.params.dir_plots, exist_ok=True)
        for event_no in self.df_optimals.index:
            fig = plot_event(self, event_no, filename=plot_filename(self.params.dir_plots, event_no))
            plt.close(fig)

    def save_results(self) -> None:
        """Writes bg_means.csv, latest_onsets.csv and optimals.xlsx (resolutions in minutes) to dir_outputs"""
        p = self.params
        os.makedirs(p.dir_outputs, exist_ok=True)
        self.df_means.to_csv(pjoin(p.dir_outputs, "bg_means.csv"))
        self.df_latest_onsets.to_csv(pjoin(p.dir_outputs, "latest_onsets.csv"))
        self.df_optimals.map(lambda x: x.total_seconds()/60 if not pd.isna(x) and type(x) is timedelta else x) \
            .to_excel(pjoin(p.dir_outputs, "optimals.xlsx"))
