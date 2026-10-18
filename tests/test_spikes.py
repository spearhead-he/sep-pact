"""Tests of the spikes: their detection with the threshold of each resolution, and their removal"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from spearhead.sep_pact.analysis import detect_spikes, remove_spikes
from tests.helpers import T0, VIEWINGS, FakeEPD, synthetic_tool

MINUTE = timedelta(minutes=1)


def series(values) -> pd.Series:
    return pd.Series(values, index=pd.date_range(T0, periods=len(values), freq=MINUTE), dtype=float)


def test_spike_above_the_threshold():
    s = series([1, 1, 1, 1000, 1, 1, 1])
    assert detect_spikes(s, threshold=2.0) == [s.index[3]]
    assert detect_spikes(s, threshold=3.5) == []


def test_spike_must_differ_from_both_neighbours():
    s = series([1, 1, 1, 1000, 1000, 1, 1])
    assert detect_spikes(s, threshold=2.0) == []


def test_spike_at_the_edge_is_not_detected():
    s = series([1000, 1, 1, 1, 1000])
    assert detect_spikes(s, threshold=2.0) == []


def test_zero_and_nan_values_are_left_out():
    s = series([1, 1, 0, 1000, np.nan, 1, 1])
    assert detect_spikes(s, threshold=2.0) == [s.index[3]]


def test_detect_spikes_without_warnings():
    s = series([0, 0, 1, 1000, 1, 0])
    with np.errstate(all="raise"):
        detect_spikes(s, threshold=2.0)


def test_remove_spikes_with_the_mean_of_the_neighbours():
    s = series([1, 2, 1000, 4, 5])
    removed = remove_spikes(s, [s.index[2]], MINUTE)
    assert removed[s.index[2]] == 3
    assert s[s.index[2]] == 1000  # the input is unchanged


def test_remove_spikes_with_a_nan_neighbour():
    s = series([1, np.nan, 1000, 4, 5])
    assert remove_spikes(s, [s.index[2]], MINUTE)[s.index[2]] == 4


def test_spike_without_valid_neighbours_is_left_unchanged():
    s = series([1, np.nan, 1000, np.nan, 5])
    assert remove_spikes(s, [s.index[2]], MINUTE)[s.index[2]] == 1000


def test_spike_at_the_edge_takes_its_only_neighbour():
    s = series([1000, 2, 3])
    assert remove_spikes(s, [s.index[0]], MINUTE)[s.index[0]] == 2


def test_spike_outside_the_series_is_ignored():
    s = series([1, 2, 3])
    pd.testing.assert_series_equal(remove_spikes(s, [s.index[0] - MINUTE], MINUTE), s)


def spiky_tool(tmp_path, monkeypatch, **parameters):
    """Synthetic event with two spikes in the decay of the sun electrons: a large one and a small one

    At 2 minutes, the large spike differs from its neighbours by about 3.7 orders of magnitude, and the small one by 2.2.
    """
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    large, small = T0 + timedelta(hours=2), T0 + timedelta(hours=3)
    fake = FakeEPD(rises, spikes={("electrons", "sun"): {large: 1e4, small: 300}})
    tool = synthetic_tool(tmp_path, monkeypatch, fake=fake, **parameters)
    tool.run_onsets()
    tool.run_spikes()
    return tool, large, small


def spike_times(tool, viewing):
    """Returns the spike times of the 1 MeV electrons of the synthetic event at 2 minutes, in a viewing"""
    spikes = tool.df_spikes.reset_index()
    spikes = spikes[(spikes["Energy Label"] == "1 MeV") & (spikes["Resolution"] == timedelta(minutes=2))
                    & (spikes["Viewing"] == viewing)]
    return list(spikes["Spike Time"])


def test_spikes_use_the_threshold_of_the_resolution(tmp_path, monkeypatch):
    thresholds = {timedelta(minutes=m): 3.0 for m in (2, 5, 10, 30)}
    tool, large, small = spiky_tool(tmp_path, monkeypatch, spike_thresholds=thresholds)
    assert spike_times(tool, "sun") == [pd.Timestamp(large)]
    assert spike_times(tool, "north") == []


def test_peak_flux_without_the_spikes(tmp_path, monkeypatch):
    tool, large, small = spiky_tool(tmp_path, monkeypatch)  # threshold 2.0 at 2 minutes: both spikes
    assert spike_times(tool, "sun") == [pd.Timestamp(large), pd.Timestamp(small)]
    tool.run_peaks()
    peak = tool.df_series.loc[(1, "electrons", "HET", "1 MeV", timedelta(minutes=2), "sun"), "Peak Flux"]
    assert peak == pytest.approx(99.77, abs=0.01)
