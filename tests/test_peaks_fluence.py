"""Tests of the peak flux and the fluence: the functions, and the choice of one result per event and channel group"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import spearhead.sep_pact.analysis as analysis
from spearhead.sep_pact.analysis import fluence_interval, get_peak_flux, peak_search_end
from tests.helpers import PEAK, T0, VIEWINGS, FakeEPD, synthetic_tool

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


def result(tool, particle, group, quantity, field):
    return tool.df_optimals.loc[1, (particle, "HET", group, quantity, field)]


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
    assert result(tool, "electrons", "1 MeV", "Onset Time", "Viewing") == "sun"
    assert result(tool, "electrons", "1 MeV", "Peak Flux", "Viewing") == "north"
    assert result(tool, "electrons", "1 MeV", "Peak Flux", "Resolution") == timedelta(minutes=2)
    assert result(tool, "electrons", "1 MeV", "Peak Flux", "Peak Flux") == pytest.approx(3 * PEAK, rel=0.01)
    assert result(tool, "electrons", "1 MeV", "Peak Flux", "Peak Flux Time") == pd.Timestamp(T0 + timedelta(hours=1))


def test_fluence_of_the_largest_resolution(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    resolution = timedelta(minutes=30)
    assert result(tool, "protons", "8 MeV", "Fluence", "Resolution") == resolution
    assert result(tool, "protons", "8 MeV", "Fluence", "Viewing") == "sun"
    start = result(tool, "protons", "8 MeV", "Fluence", "Fluence Start")
    end = result(tool, "protons", "8 MeV", "Fluence", "Fluence End")
    assert (start, end) == (pd.Timestamp(T0), pd.Timestamp(T0 + timedelta(hours=3)))
    flux = tool.dfs_flux["protons"]["HET"][resolution].loc[1, ("sun", "8 MeV")][start:end]
    expected = np.trapezoid(flux.to_numpy(), (flux.index - flux.index[0]).total_seconds())
    assert result(tool, "protons", "8 MeV", "Fluence", "Fluence") == pytest.approx(expected)
    fluences = [tool.dfs_events["protons"]["HET"][f].loc[1, ("sun", "8 MeV", "Fluence")] for f in tool.params.resample_freqs]
    assert result(tool, "protons", "8 MeV", "Fluence", "Fluence") == max(fluences)


def test_fluence_ends_at_a_shock(tmp_path, monkeypatch):
    shock = T0 + timedelta(hours=2, minutes=30)
    tool = run(synthetic_tool(tmp_path, monkeypatch, shocks=[shock]))
    assert result(tool, "protons", "8 MeV", "Fluence", "Fluence End") == pd.Timestamp(shock)


def test_fluence_starting_before_the_onset_is_not_chosen(tmp_path, monkeypatch):
    real = analysis.fluence_interval

    def early_at_two_minutes(ts, onset, peak_time, enddate, peak_fraction, points):
        fluence, start, end, threshold = real(ts, onset, peak_time, enddate, peak_fraction, points)
        if ts.index[1] - ts.index[0] == timedelta(minutes=2):
            return 1e12, onset - timedelta(hours=1), end, threshold
        return fluence, start, end, threshold

    monkeypatch.setattr(analysis, "fluence_interval", early_at_two_minutes)
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    assert result(tool, "protons", "8 MeV", "Fluence", "Resolution") == timedelta(minutes=30)
    assert result(tool, "protons", "8 MeV", "Fluence", "Fluence") < 1e12


def test_no_peak_flux_or_fluence_without_an_onset(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})
    tool = run(synthetic_tool(tmp_path, monkeypatch, rises))
    for quantity, field in (("Peak Flux", "Peak Flux"), ("Peak Flux", "Resolution"), ("Fluence", "Fluence"),
                            ("Fluence", "Resolution")):
        assert pd.isna(result(tool, "protons", "8 MeV", quantity, field))
    assert pd.isna(tool.dfs_events["protons"]["HET"][timedelta(minutes=2)].loc[1, ("sun", "8 MeV", "Fluence")])
