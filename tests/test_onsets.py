"""Tests of the onsets: detection, data quality, and the choice of one onset per event and channel group"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from spearhead.sep_pact.analysis import onset_detection_sigma, quality_analysis, reference_iter
from tests.helpers import T0, VIEWINGS, synthetic_tool

MINUTE = timedelta(minutes=1)


def series(values, start=T0, step=MINUTE) -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=step), dtype=float)


def test_onset_is_the_start_of_the_rise():
    s = series([1, 1, 1, 1, 1, 3, 10, 10, 10, 10])
    onset, levels = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    # 3 is the first point above the threshold, and the walk back stops at the last background point
    assert onset == s.index[4]
    assert levels == {"bg_level": 1.0, "threshold": 1.0}


def test_no_onset_below_the_threshold():
    s = series([1, 2, 1, 2, 1, 2, 1, 2, 1, 2])
    onset, levels = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset is None
    assert levels["bg_level"] == pytest.approx(1.5)
    assert levels["threshold"] == pytest.approx(1.5 + 2 * np.std([1, 2, 1, 2], ddof=1))


def test_onset_needs_n_consecutive_points():
    s = series([1, 1, 1, 1, 10, 10, 1, 1, 10, 10, 10, 10])
    onset, _ = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset == s.index[7]


def test_onset_walk_back_stops_at_the_end_of_the_background():
    s = series([0.5, 0.5, 0.5, 1, 2, 3, 4, 5])
    onset, _ = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset == s.index[3]


def test_onset_with_background_given_as_positions():
    s = series([1, 1, 1, 1, 1, 3, 10, 10, 10, 10])
    onset, _ = onset_detection_sigma(s, s=2, n=3, bg_start=0, bg_end=3)
    assert onset == s.index[4]


def test_quality_ratio_of_transitions_to_zero_or_nan():
    s = series([1, 0, 0, 1, np.nan, 1, 1, 1, 1, 1])
    qualified, length, n_zeroes, ratio = quality_analysis(s, tolerance=0.3, adjustable_tolerance=False)
    assert (qualified, length, n_zeroes, ratio) == (True, 10, 3, pytest.approx(0.2))
    assert not quality_analysis(s, tolerance=0.1, adjustable_tolerance=False)[0]


def test_quality_needs_more_valid_values_than_zeros():
    s = series([1, 0, 0, 0, 0, 0, 0, 0, 0, 1])
    assert not quality_analysis(s, tolerance=0.5, adjustable_tolerance=False)[0]


def test_quality_of_a_single_point():
    qualified, length, n_zeroes, ratio = quality_analysis(series([1]), tolerance=0.1, adjustable_tolerance=False)
    assert (qualified, length, n_zeroes) == (False, 1, 0) and np.isnan(ratio)


def test_adjustable_quality_tolerance_grows_with_the_resolution():
    s = series([1, 0] + [1] * 7, step=timedelta(minutes=30))  # ratio 1/9
    assert not quality_analysis(s, tolerance=0.1, adjustable_tolerance=False)[0]
    assert quality_analysis(s, tolerance=0.1, adjustable_tolerance=True)[0]  # tolerance 0.1 * 1.5


def test_reference_iter_puts_the_reference_first():
    reference = {"particle": "electrons", "mev": "5 MeV", "sensor": "HET"}
    assert reference_iter(["protons", "electrons"], reference) == ["electrons", "protons"]
    assert reference_iter(["1 MeV", "5 MeV"], reference) == ["5 MeV", "1 MeV"]
    assert reference_iter(["8 MeV"], reference) == ["8 MeV"]
    assert reference_iter(["protons", "electrons"], None) == ["protons", "electrons"]


def onset(tool, particle, group, field="Onset Time"):
    """Returns a field of the chosen onset of the synthetic event"""
    return tool.df_optimals.loc[1, (particle, "HET", group, "Onset Time", field)]


def test_onset_of_the_finest_resolution_and_earliest_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 + timedelta(minutes=10) for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises[("electrons", "north")] = T0
    rises[("protons", "south")] = T0 + timedelta(minutes=4)
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.run_onsets()
    assert onset(tool, "electrons", "1 MeV") == pd.Timestamp(T0 - timedelta(minutes=2))
    assert onset(tool, "electrons", "1 MeV", "Resolution") == timedelta(minutes=2)
    assert onset(tool, "electrons", "1 MeV", "Viewing") == "north"
    assert onset(tool, "protons", "8 MeV") == pd.Timestamp(T0 + timedelta(minutes=2))
    assert onset(tool, "protons", "8 MeV", "Viewing") == "south"
    assert not onset(tool, "protons", "8 MeV", "Onset Copied")
    assert not onset(tool, "protons", "8 MeV", "Onset at BG End")


def test_onsets_outside_the_reference_window_are_ignored(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.run_onsets()
    assert pd.isna(onset(tool, "protons", "8 MeV"))
    assert pd.isna(onset(tool, "protons", "8 MeV", "Resolution"))


def test_onset_copied_from_the_reference_channel(tmp_path, monkeypatch):
    rises = {("electrons", viewing): T0 for viewing in VIEWINGS}  # flat protons
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.run_onsets()
    assert onset(tool, "protons", "8 MeV") == onset(tool, "electrons", "1 MeV")
    assert onset(tool, "protons", "8 MeV", "Onset Copied")
    assert not onset(tool, "electrons", "1 MeV", "Onset Copied")


def test_onset_at_the_end_of_the_background(tmp_path, monkeypatch):
    events = {1: {"Onset Time": T0, "BG End": T0 - timedelta(minutes=2)}}
    tool = synthetic_tool(tmp_path, monkeypatch, events=events)
    tool.run_onsets()
    assert onset(tool, "electrons", "1 MeV") == pd.Timestamp(T0 - timedelta(minutes=2))
    assert onset(tool, "electrons", "1 MeV", "Onset at BG End")


def test_quality_of_the_chosen_onset(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    quality = {field: tool.df_ts_quality.loc[1, ("electrons", "HET", "1 MeV", field)]
               for field in ("Length", "Zeroes", "Ratio")}
    assert quality["Zeroes"] == 0 and quality["Ratio"] == 0
    # from the onset (T0 - 2 min) to the last bin of the data (end time - 2 min), every 2 minutes
    assert quality["Length"] == 48 * 60 // 2 + 1


def test_onset_after_a_shock_ends_at_the_shock(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(hours=6)])
    tool.run_onsets()
    assert tool.df_ts_quality.loc[1, ("electrons", "HET", "1 MeV", "Length")] == (6 * 60 + 2) // 2 + 1
