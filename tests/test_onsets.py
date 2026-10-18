"""Tests of the onsets: detection, data quality, and the choice of one onset per event and channel group"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from spearhead.sep_pact.analysis import choose_onset, onset_detection_sigma, quality_analysis, reference_iter
from tests.helpers import T0, VIEWINGS, channel_rows, synthetic_tool

MINUTE = timedelta(minutes=1)


def series(values, start=T0, step=MINUTE) -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=step), dtype=float)


def test_onset_is_the_start_of_the_rise():
    s = series([1, 1, 1, 1, 1, 3, 10, 10, 10, 10])
    onset, bg_start, bg_end, levels = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    # 3 is the first point above the threshold, and the walk back stops at the last background point
    assert onset == s.index[4]
    assert (bg_start, bg_end) == (s.index[0], s.index[3])
    assert levels == {"bg_level": 1.0, "threshold": 1.0}


def test_no_onset_below_the_threshold():
    s = series([1, 2, 1, 2, 1, 2, 1, 2, 1, 2])
    onset, bg_start, bg_end, levels = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset is None
    assert levels["bg_level"] == pytest.approx(1.5)
    assert levels["threshold"] == pytest.approx(1.5 + 2 * np.std([1, 2, 1, 2], ddof=1))


def test_onset_needs_n_consecutive_points():
    s = series([1, 1, 1, 1, 10, 10, 1, 1, 10, 10, 10, 10])
    onset, _, _, _ = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset == s.index[7]


def test_onset_walk_back_stops_at_the_end_of_the_background():
    s = series([0.5, 0.5, 0.5, 1, 2, 3, 4, 5])
    onset, _, _, _ = onset_detection_sigma(s, s=2, n=3, bg_start=s.index[0], bg_end=s.index[3])
    assert onset == s.index[3]


def test_onset_with_background_given_as_positions():
    s = series([1, 1, 1, 1, 1, 3, 10, 10, 10, 10])
    onset, bg_start, bg_end, _ = onset_detection_sigma(s, s=2, n=3, bg_start=0, bg_end=3)
    assert onset == s.index[4]
    assert (bg_start, bg_end) == (s.index[0], s.index[3])


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


def onset(tool, particle, group, column="Onset Time"):
    """Returns a column of the chosen onset of the synthetic event"""
    return tool.df_results.loc[(1, particle, "HET", group), column]


def test_onset_of_the_finest_resolution_and_earliest_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 + timedelta(minutes=10) for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises[("electrons", "north")] = T0
    rises[("protons", "south")] = T0 + timedelta(minutes=4)
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.run_onsets()
    assert onset(tool, "electrons", "1 MeV") == pd.Timestamp(T0 - timedelta(minutes=2))
    assert onset(tool, "electrons", "1 MeV", "Onset Resolution") == timedelta(minutes=2)
    assert onset(tool, "electrons", "1 MeV", "Onset Viewing") == "north"
    assert onset(tool, "protons", "8 MeV") == pd.Timestamp(T0 + timedelta(minutes=2))
    assert onset(tool, "protons", "8 MeV", "Onset Viewing") == "south"
    assert not onset(tool, "protons", "8 MeV", "Onset Copied")
    assert not onset(tool, "protons", "8 MeV", "Onset at BG End")


def test_onsets_outside_the_reference_window_are_ignored(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.run_onsets()
    assert pd.isna(onset(tool, "protons", "8 MeV"))
    assert pd.isna(onset(tool, "protons", "8 MeV", "Onset Resolution"))


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
    quality = {field: onset(tool, "electrons", "1 MeV", f"Quality {field}") for field in ("Length", "Zeroes", "Ratio")}
    assert quality["Zeroes"] == 0 and quality["Ratio"] == 0
    # from the onset (T0 - 2 min) to the last bin of the data (end time - 2 min), every 2 minutes
    assert quality["Length"] == 48 * 60 // 2 + 1


def test_onset_after_a_shock_ends_at_the_shock(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(hours=6)])
    tool.run_onsets()
    assert onset(tool, "electrons", "1 MeV", "Quality Length") == (6 * 60 + 2) // 2 + 1


def onset_row(minutes_after_t0, usable=True, copied=False):
    return {"Onset Time": pd.Timestamp(T0 + timedelta(minutes=minutes_after_t0)), "Usable": usable,
            "Onset Copied": copied, "Quality Length": 100, "Quality Zeroes": 0, "Quality Ratio": 0.0}


WINDOW = timedelta(hours=2.5)


def test_choose_onset_of_equal_onsets_keeps_the_first_viewing():
    rows = channel_rows({(2, "sun"): onset_row(10), (2, "north"): onset_row(4), (2, "south"): onset_row(4),
                         (5, "sun"): onset_row(0)})
    chosen = choose_onset(rows, pd.NaT, WINDOW, T0 - timedelta(hours=1))
    assert chosen["Onset Resolution"] == timedelta(minutes=2)
    assert chosen["Onset Viewing"] == "north"
    assert chosen["Onset Time"] == pd.Timestamp(T0 + timedelta(minutes=4))


def test_choose_onset_at_the_finest_usable_resolution():
    rows = channel_rows({(2, "sun"): onset_row(0, usable=False), (5, "sun"): onset_row(5), (5, "north"): onset_row(10),
                         (10, "sun"): onset_row(1)})
    chosen = choose_onset(rows, pd.NaT, WINDOW, T0 - timedelta(hours=1))
    assert (chosen["Onset Resolution"], chosen["Onset Viewing"]) == (timedelta(minutes=5), "sun")
    assert chosen["Quality Length"] == 100


def test_choose_onset_within_the_window_of_the_reference_onset():
    rows = channel_rows({(2, "sun"): onset_row(0), (5, "sun"): onset_row(200)})
    chosen = choose_onset(rows, pd.Timestamp(T0 + timedelta(hours=4)), WINDOW, T0 - timedelta(hours=1))
    assert chosen["Onset Resolution"] == timedelta(minutes=5)
    rows = channel_rows({(2, "sun"): onset_row(0)})
    chosen = choose_onset(rows, pd.Timestamp(T0 + timedelta(hours=3)), WINDOW, T0 - timedelta(hours=1))
    assert pd.isna(chosen["Onset Time"]) and pd.isna(chosen["Onset Resolution"]) and chosen["Onset Viewing"] is None
    assert chosen["Onset Copied"] is None and pd.isna(chosen["Quality Length"])


def test_choose_onset_flags():
    rows = channel_rows({(2, "sun"): onset_row(0, copied=True)})
    chosen = choose_onset(rows, pd.NaT, WINDOW, T0)
    assert chosen["Onset Copied"] is True and chosen["Onset at BG End"] is True
    chosen = choose_onset(rows, pd.NaT, WINDOW, T0 - timedelta(minutes=1))
    assert chosen["Onset at BG End"] is False


def test_series_of_other_particles_take_the_reference_onset(tmp_path, monkeypatch):
    rises = {("electrons", viewing): T0 for viewing in VIEWINGS}  # flat protons
    tool = synthetic_tool(tmp_path, monkeypatch, rises)
    tool.calculate_onsets()
    series = tool.df_series.reset_index()
    reference = series[series["Energy Label"] == "1 MeV"].set_index(["Resolution", "Viewing"])["Onset Time"]
    protons = series[series["Particle"] == "protons"]
    assert protons["Onset Copied"].all()
    for _, row in protons.iterrows():
        assert row["Onset Time"] == reference[(row["Resolution"], row["Viewing"])]
    assert not series[series["Particle"] == "electrons"]["Onset Copied"].any()


def test_series_without_an_onset_are_not_usable(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, rises={})  # flat electrons and protons
    tool.run_onsets()
    assert tool.df_series["Onset Time"].isna().all()
    assert not tool.df_series["Usable"].any()
    # without a reference onset, nothing is copied
    assert not tool.df_series["Onset Copied"].any()
    assert tool.df_series["Quality Length"].isna().all()
    assert tool.df_results["Onset Time"].isna().all() and tool.df_results["Onset Viewing"].isna().all()
