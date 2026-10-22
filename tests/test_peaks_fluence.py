"""Tests of the peak flux and the fluence: the functions, and the choice of one result per event and channel group"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import spearhead.sep_pact.analysis as analysis
from spearhead.sep_pact.analysis import choose_fluence, choose_peak, fluence_interval, get_peak_flux, peak_search_end
from tests.helpers import PEAK, T0, VIEWINGS, FakeEPD, channel_rows, synthetic_tool

TEN_MINUTES = timedelta(minutes=10)


def series(values) -> pd.Series:
    return pd.Series(values, index=pd.date_range(T0, periods=len(values), freq=TEN_MINUTES), dtype=float)


def test_peak_flux():
    s = series([1, 3, 7, 2])
    assert get_peak_flux(s) == (7, s.index[2])


def test_peak_flux_of_an_empty_series():
    assert get_peak_flux(series([])) == (None, None)


def test_peak_search_end_is_the_middle_if_long_enough():
    assert peak_search_end(T0, T0 + timedelta(hours=30), timedelta(hours=10)) == T0 + timedelta(hours=15)


def test_peak_search_end_is_the_end_if_the_middle_is_too_short():
    assert peak_search_end(T0, T0 + timedelta(hours=16), timedelta(hours=10)) == T0 + timedelta(hours=16)


def test_fluence_interval():
    s = series([1, 1, 2, 6, 10, 6, 2, 1, 1])
    fluence, start, end, threshold = fluence_interval(s, s.index[1], s.index[4], s.index[-1], peak_fraction=0.5, points=2)
    assert threshold == 5
    # the last of 2 points at or below 5 before the peak, and the first of 2 points after it
    assert (start, end) == (s.index[2], s.index[6])
    assert fluence == pytest.approx(600 * (2 / 2 + 6 + 10 + 6 + 2 / 2))


def test_fluence_starts_at_the_onset_at_the_earliest():
    s = series([1, 1, 2, 6, 10, 6, 2, 1, 1])
    _, start, _, _ = fluence_interval(s, s.index[3], s.index[4], s.index[-1], peak_fraction=0.5, points=2)
    assert start == s.index[3]


def test_fluence_interval_with_single_points():
    s = series([3, 6, 10, 6, 3, 6, 6])
    _, start, end, _ = fluence_interval(s, s.index[0], s.index[2], s.index[-1], peak_fraction=0.5, points=2)
    assert (start, end) == (s.index[0], s.index[4])


def test_fluence_ends_at_the_end_without_low_points():
    s = series([1, 1, 10, 9, 8, 7])
    end_time = s.index[-1] + timedelta(hours=1)
    _, _, end, _ = fluence_interval(s, s.index[0], s.index[2], end_time, peak_fraction=0.5, points=2)
    assert end == end_time


def test_fluence_peak_is_the_higher_point_next_to_the_peak_time():
    s = series([1, 1, 8, 10, 1, 1])
    _, _, _, threshold = fluence_interval(s, s.index[0], s.index[2] + timedelta(minutes=5), s.index[-1],
                                          peak_fraction=0.5, points=2)
    assert threshold == 5


def test_fluence_peak_is_the_higher_point_before_the_peak_time():
    s = series([1, 1, 10, 8, 1, 1])
    _, _, _, threshold = fluence_interval(s, s.index[0], s.index[2] + timedelta(minutes=5), s.index[-1],
                                          peak_fraction=0.5, points=2)
    assert threshold == 5


def test_fluence_with_the_peak_time_after_the_series():
    # the peak of another resolution can be after the last point of this one
    s = series([1, 1, 4, 8, 10])
    end_time = s.index[-1] + timedelta(minutes=5)
    fluence, start, end, threshold = fluence_interval(s, s.index[0], end_time, end_time, peak_fraction=0.5, points=2)
    assert threshold == 5 and start == s.index[2] and end == end_time
    assert fluence == pytest.approx(600 * (4 / 2 + 8 + 10 / 2))


def result(tool, particle, group, column):
    return tool.df_results.loc[(1, particle, "HET", group), column]


def series_value(tool, particle, group, minutes, viewing, column):
    return tool.df_series.loc[(1, particle, "HET", group, timedelta(minutes=minutes), viewing), column]


def run(tool):
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


def test_peak_flux_of_the_highest_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FakeEPD(rises, peaks={("electrons", "north"): 3 * PEAK})
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=fake))
    assert result(tool, "electrons", "1 MeV", "Onset Viewing") == "sun"
    assert result(tool, "electrons", "1 MeV", "Peak Flux Viewing") == "north"
    assert result(tool, "electrons", "1 MeV", "Peak Flux Resolution") == timedelta(minutes=2)
    assert result(tool, "electrons", "1 MeV", "Peak Flux") == pytest.approx(3 * PEAK, rel=0.01)
    assert result(tool, "electrons", "1 MeV", "Peak Flux Time") == pd.Timestamp(T0 + timedelta(hours=1))


def test_fluence_of_the_largest_resolution(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    resolution = timedelta(minutes=30)
    assert result(tool, "protons", "8 MeV", "Fluence Resolution") == resolution
    assert result(tool, "protons", "8 MeV", "Fluence Viewing") == "sun"
    start = result(tool, "protons", "8 MeV", "Fluence Start")
    end = result(tool, "protons", "8 MeV", "Fluence End")
    assert (start, end) == (pd.Timestamp(T0), pd.Timestamp(T0 + timedelta(hours=3)))
    flux = tool.dfs_flux["protons"]["HET"][resolution].loc[1, ("sun", "8 MeV")][start:end]
    expected = np.trapezoid(flux.to_numpy(), (flux.index - flux.index[0]).total_seconds())
    assert result(tool, "protons", "8 MeV", "Fluence") == pytest.approx(expected)
    fluences = [series_value(tool, "protons", "8 MeV", minutes, "sun", "Fluence") for minutes in (2, 5, 10, 30)]
    assert result(tool, "protons", "8 MeV", "Fluence") == max(fluences)


def test_fluence_ends_at_a_shock(tmp_path, monkeypatch):
    shock = T0 + timedelta(hours=2, minutes=30)
    tool = run(synthetic_tool(tmp_path, monkeypatch, shocks=[shock]))
    assert result(tool, "protons", "8 MeV", "Fluence End") == pd.Timestamp(shock)


def test_no_fluence_without_points_before_a_shock(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    onset = result(tool, "protons", "8 MeV", "Onset Time")
    # a shock 1 minute after the onset: at 30 minutes, no point from the onset to the shock (on the 30-minute grid)
    assert onset.minute % 30 != 0
    tool.shocktimes = pd.Series([onset + timedelta(minutes=1)])
    tool.run_peaks()
    tool.run_fluences()
    assert np.isnan(series_value(tool, "protons", "8 MeV", 30, "sun", "Fluence"))
    assert pd.isna(series_value(tool, "protons", "8 MeV", 30, "sun", "Fluence End"))


def test_fluence_starting_before_the_onset_is_not_chosen(tmp_path, monkeypatch):
    real = analysis.fluence_interval

    def early_at_two_minutes(ts, onset, peak_time, enddate, peak_fraction, points):
        fluence, start, end, threshold = real(ts, onset, peak_time, enddate, peak_fraction, points)
        if ts.index[1] - ts.index[0] == timedelta(minutes=2):
            return 1e12, onset - timedelta(hours=1), end, threshold
        return fluence, start, end, threshold

    monkeypatch.setattr(analysis, "fluence_interval", early_at_two_minutes)
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    assert result(tool, "protons", "8 MeV", "Fluence Resolution") == timedelta(minutes=30)
    assert result(tool, "protons", "8 MeV", "Fluence") < 1e12


def test_no_peak_flux_or_fluence_without_an_onset(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})
    tool = run(synthetic_tool(tmp_path, monkeypatch, rises))
    for column in ("Peak Flux", "Peak Flux Resolution", "Fluence", "Fluence Resolution"):
        assert pd.isna(result(tool, "protons", "8 MeV", column))
    assert pd.isna(series_value(tool, "protons", "8 MeV", 2, "sun", "Fluence"))


def peak_row(peak_flux, hour=1):
    return {"Peak Flux": peak_flux, "Peak Flux Time": pd.Timestamp(T0 + timedelta(hours=hour))}


def test_choose_peak_of_equal_peaks_keeps_the_first_viewing():
    rows = channel_rows({(2, "sun"): peak_row(5.0), (2, "north"): peak_row(8.0, hour=2), (2, "south"): peak_row(8.0),
                         (5, "sun"): peak_row(100.0)})
    chosen = choose_peak(rows, pd.Timedelta(minutes=2))
    assert chosen == {"Peak Flux": 8.0, "Peak Flux Time": pd.Timestamp(T0 + timedelta(hours=2)),
                      "Peak Flux Resolution": timedelta(minutes=2), "Peak Flux Viewing": "north"}


def test_choose_peak_without_a_resolution_or_peaks():
    rows = channel_rows({(2, "sun"): peak_row(np.nan), (5, "sun"): peak_row(100.0)})
    for resolution in (pd.NaT, pd.Timedelta(minutes=2)):
        chosen = choose_peak(rows, resolution)
        assert pd.isna(chosen["Peak Flux"]) and pd.isna(chosen["Peak Flux Resolution"])
        assert chosen["Peak Flux Viewing"] is None


def fluence_row(fluence, start_minutes=0):
    return {"Fluence": fluence, "Fluence Start": pd.Timestamp(T0 + timedelta(minutes=start_minutes)),
            "Fluence End": pd.Timestamp(T0 + timedelta(hours=3)), "Fluence Threshold": 1.0}


def test_choose_fluence_of_equal_fluences_keeps_the_first_resolution():
    rows = channel_rows({(2, "sun"): fluence_row(5.0), (5, "sun"): fluence_row(9.0, 4), (10, "sun"): fluence_row(9.0),
                         (5, "north"): fluence_row(100.0)})
    chosen = choose_fluence(rows, pd.Timestamp(T0), "sun")
    assert chosen["Fluence"] == 9.0
    assert chosen["Fluence Resolution"] == timedelta(minutes=5)
    assert chosen["Fluence Start"] == pd.Timestamp(T0 + timedelta(minutes=4))
    assert chosen["Fluence Viewing"] == "sun"


def test_choose_fluence_not_starting_before_the_onset():
    rows = channel_rows({(2, "sun"): fluence_row(50.0, -10), (5, "sun"): fluence_row(9.0)})
    assert choose_fluence(rows, pd.Timestamp(T0), "sun")["Fluence Resolution"] == timedelta(minutes=5)
    rows = channel_rows({(2, "sun"): fluence_row(50.0, -10), (5, "sun"): fluence_row(np.nan)})
    chosen = choose_fluence(rows, pd.Timestamp(T0), "sun")
    # the viewing of the peak is kept without a fluence
    assert pd.isna(chosen["Fluence"]) and pd.isna(chosen["Fluence Resolution"]) and chosen["Fluence Viewing"] == "sun"
    chosen = choose_fluence(rows, pd.Timestamp(T0), None)
    assert pd.isna(chosen["Fluence"]) and chosen["Fluence Viewing"] is None
