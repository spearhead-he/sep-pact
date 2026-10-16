"""Helpers of the tests: parameters, input files and EPD-like data without downloads

The synthetic flux is constant (background) and rises linearly at a chosen time to a peak, then decays linearly
back to the background. With a constant background, the threshold equals the background, and the onset detection
(which steps back while the earlier point is lower) gives the last background point before the rise: one resolution
step before the rise time, when the rise time is on a bin boundary.
"""
import functools
from datetime import datetime, timedelta

import matplotlib
import numpy as np
import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT, SEPPACT_parameters

# the baseline images were made with matplotlib 3.11, whose layout differs from older versions by a few pixels
BASELINE_MATPLOTLIB = (3, 11)


def image_compare(test):
    """Compares the figure returned by the test with its baseline image (with --mpl), with matplotlib 3.11 or newer

    With an older matplotlib, the test runs without the comparison.
    """
    if tuple(matplotlib.__version_info__[:2]) >= BASELINE_MATPLOTLIB:
        return pytest.mark.mpl_image_compare(tolerance=5, style="default")(test)

    @functools.wraps(test)
    def without_comparison(*args, **kwargs) -> None:
        test(*args, **kwargs)
    return without_comparison


STEP = timedelta(minutes=1)                         # cadence of the synthetic data
OFFSET = timedelta(seconds=3, microseconds=240000)  # sub-second timestamps, as in the EPD data
BACKGROUND = 1.0
PEAK = 100.0
RISE = timedelta(hours=1)
DECAY = timedelta(hours=4)
N_CHANNELS = {"protons": 36, "electrons": 4}        # HET channels


def make_params(tmp_path, **parameters) -> SEPPACT_parameters:
    """Returns parameters with all the folders in tmp_path (the inputs folder is created)"""
    folders = {name: str(tmp_path / name) for name in ("inputs", "data", "intermediate_states", "plots", "outputs")}
    (tmp_path / "inputs").mkdir(exist_ok=True)
    defaults = {"dir_inputs": folders["inputs"], "dir_data": folders["data"], "dir_saves": folders["intermediate_states"],
                "dir_plots": folders["plots"], "dir_outputs": folders["outputs"], "file_events": "events.xlsx"}
    defaults.update(parameters)
    return SEPPACT_parameters(**defaults)


def write_events(folder, rows: dict, name: str = "events.xlsx") -> str:
    """Writes an event list {event_no: {column: time}} as an Excel file, and returns its path"""
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "Event No"
    path = str(folder / name)
    df.to_excel(path)
    return path


def write_shocks(folder, times: list[datetime], name: str = "shocks.dat") -> str:
    """Writes a shock list in the format of ipshocks.helsinki.fi, with comment lines, and returns its path"""
    lines = ["# Interplanetary shocks list from IPShocks.com", "# Columns:", "# Year", "# Month (1-12)"]
    for t in times:
        lines.append(f"{t.year};{t.month:2d};{t.day:2d};{t.hour:2d};{t.minute:2d};{t.second:2d};     SolO;FF;1.50; 29.73")
    path = str(folder / name)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def profile(index: pd.DatetimeIndex, rise_at: datetime | None, peak: float = PEAK) -> np.ndarray:
    """Returns the synthetic flux at the times of index: the background, with a linear rise at rise_at and a linear decay"""
    flux = np.full(len(index), BACKGROUND)
    if rise_at is None:
        return flux
    t = (index - pd.Timestamp(rise_at)) / pd.Timedelta(RISE)
    rising = (t >= 0) & (t < 1)
    flux[rising] = BACKGROUND + (peak - BACKGROUND) * t[rising]
    d = (index - pd.Timestamp(rise_at) - pd.Timedelta(RISE)) / pd.Timedelta(DECAY)
    decaying = (d >= 0) & (d < 1)
    flux[decaying] = peak - (peak - BACKGROUND) * d[decaying]
    return flux


def epd_energies(proton_prefix: str = "H") -> dict:
    """Returns channel energies as epd_load does, with the widths 0.1, 0.2, ... MeV"""
    energies = {}
    for prefix, n in ((proton_prefix, N_CHANNELS["protons"]), ("Electron", N_CHANNELS["electrons"])):
        energies[f"{prefix}_Bins_Width"] = np.arange(1, n + 1) * 0.1
        energies[f"{prefix}_Bins_Low_Energy"] = np.arange(1, n + 1) * 1.0
        energies[f"{prefix}_Bins_Text"] = np.array([f"channel {c}" for c in range(n)])
    return energies


def epd_frame(index: pd.DatetimeIndex, prefix: str, n_channels: int, flux: np.ndarray) -> pd.DataFrame:
    """Returns the data of one particle as epd_load does: flux and uncertainty columns under two column levels"""
    columns = pd.MultiIndex.from_tuples([(f"{prefix}_Flux", f"{prefix}_Flux_{c}") for c in range(n_channels)]
                                        + [(f"{prefix}_Uncertainty", f"{prefix}_Uncertainty_{c}") for c in range(n_channels)])
    values = np.column_stack([flux] * n_channels + [flux * 0.1] * n_channels).astype("float32")
    return pd.DataFrame(values, index=index, columns=columns)


class FakeEPD:
    """Replaces solo_epd_loader.epd_load: EPD-like data with a rise at given times, without downloads

    rises: {(particle, viewing): rise time}; the other particles and viewings are flat.
    peaks: {(particle, viewing): peak flux}, PEAK by default.
    spikes: {(particle, viewing): {time: factor}}; the flux of the point at time (a whole minute) is multiplied by factor.
    fail: the number of calls that raise ValueError ("no data") before data are returned.
    The data cover the whole days of the requested period, every STEP, shifted by OFFSET.
    """

    def __init__(self,
                 rises: dict | None = None,
                 peaks: dict | None = None,
                 spikes: dict | None = None,
                 proton_prefix: str = "H",
                 fail: int = 0) -> None:
        self.rises = rises or {}
        self.peaks = peaks or {}
        self.spikes = spikes or {}
        self.proton_prefix = proton_prefix
        self.fail = fail
        self.calls = []

    def __call__(self, sensor, level, startdate, enddate, viewing, path, autodownload) -> tuple:
        self.calls.append({"sensor": sensor, "level": level, "startdate": startdate, "enddate": enddate, "viewing": viewing})
        if self.fail > 0:
            self.fail -= 1
            raise ValueError("No data found")
        start = pd.Timestamp(startdate).normalize()
        end = pd.Timestamp(enddate).normalize() + pd.Timedelta(days=1)
        index = pd.date_range(start, end, freq=STEP, inclusive="left") + pd.Timedelta(OFFSET)
        frames = {}
        for particle, prefix in (("protons", self.proton_prefix), ("electrons", "Electron")):
            key = (particle, viewing)
            flux = profile(index, self.rises.get(key), self.peaks.get(key, PEAK))
            for time, factor in self.spikes.get(key, {}).items():
                flux[index == pd.Timestamp(time) + pd.Timedelta(OFFSET)] *= factor
            frames[particle] = epd_frame(index, prefix, N_CHANNELS[particle], flux)
        return frames["protons"], frames["electrons"], epd_energies(self.proton_prefix)


T0 = datetime(2021, 1, 1, 12, 0)  # onset time of the synthetic event in the event list
VIEWINGS = ("sun", "asun", "north", "south")


def synthetic_tool(tmp_path,
                   monkeypatch,
                   rises: dict | None = None,
                   events: dict | None = None,
                   shocks: list | None = None,
                   fake: FakeEPD | None = None,
                   **parameters) -> SEPPACT:
    """Returns a SEPPACT on one synthetic event (number 1, onset T0), with the fake loader, after run_data()

    By default all the electron and proton viewings rise at T0. A FakeEPD given as fake replaces the one
    built from rises.
    """
    import spearhead.sep_pact.data as data
    if rises is None:
        rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    monkeypatch.setattr(data, "epd_load", fake or FakeEPD(rises))
    params = make_params(tmp_path, **parameters)
    write_events(tmp_path / "inputs", events or {1: {"Onset Time": T0}})
    write_shocks(tmp_path / "inputs", shocks or [datetime(2000, 1, 1)])
    tool = SEPPACT(params)
    tool.run_inputs()
    tool.run_data()
    return tool
