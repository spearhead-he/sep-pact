"""Tests of a whole synthetic run: the result tables and the files written by save_results() and plot_events()"""
import os
from datetime import timedelta

import pandas as pd
import pytest

from spearhead.sep_pact.analysis import RESULT_COLUMNS, SERIES_INDEX
from tests.helpers import T0, VIEWINGS, FailingEPD, FakeEPD, synthetic_tool


@pytest.fixture
def tool(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


def test_every_channel_group_has_results(tool):
    assert (tool.df_results["Onset Time"] == pd.Timestamp(T0 - timedelta(minutes=2))).all()
    assert tool.df_results["Fluence"].notna().all()


def test_df_series_has_a_row_per_series(tool):
    assert tool.df_series.index.names == SERIES_INDEX
    n_channels = len(list(tool._iter_channels()))
    assert len(tool.df_series) == n_channels * len(tool.params.resample_freqs) * len(tool.params.viewings)
    # the resolutions and viewings in the order of the parameters
    first = tool.df_series.index[:len(tool.params.viewings) + 1]
    assert list(first.get_level_values("Viewing")) == tool.params.viewings + [tool.params.viewings[0]]
    assert first.get_level_values("Resolution")[-1] == tool.params.resample_freqs[1]


def test_group_energies(tool):
    # the fake channels c have a low energy of c + 1 MeV and a width of (c + 1) * 0.1 MeV
    assert tool.group_energies("electrons", "HET", "1 MeV") == pytest.approx((1.0, 2.2))
    assert tool.group_energies("protons", "HET", "8 MeV") == pytest.approx((2.0, 4.4))


def test_results_table_has_a_row_per_event_and_channel_group(tool):
    table = tool.results_table()
    assert list(table.columns[:6]) == ["Event No", "Particle", "Sensor", "Energy Label", "Low Energy", "High Energy"]
    columns = RESULT_COLUMNS.copy()
    i = columns.index("Onset Corrected") + 1
    columns[i:i] = ["BG Start", "BG End", "BG Window Source", "End Time Source"]
    assert list(table.columns[6:]) == columns
    assert (table["BG Window Source"] == "default").all() and (table["End Time Source"] == "default").all()
    assert (table["BG Start"] == tool.events.loc[1, "BG Start"]).all()
    assert (table["BG End"] == tool.events.loc[1, "BG End"]).all()
    assert list(zip(table["Event No"], table["Particle"], table["Sensor"], table["Energy Label"])) == \
        [(1, particle, sensor, mevlbl) for particle, sensor, mevlbl in tool._iter_channels()]


def test_results_table_has_the_values_of_df_results(tool):
    table = tool.results_table().set_index(["Event No", "Particle", "Sensor", "Energy Label"])
    for key, row in table.iterrows():
        for column in RESULT_COLUMNS:
            value = tool.df_results.loc[key, column]
            if isinstance(value, timedelta):
                assert row[column] == value.total_seconds() / 60
            elif pd.isna(value):
                assert pd.isna(row[column])
            else:
                assert row[column] == value


def test_save_results(tool):
    tool.save_results()
    folder = tool.params.dir_outputs
    assert os.listdir(folder) == ["results.csv"]
    results = pd.read_csv(os.path.join(folder, "results.csv"))
    assert len(results) == len(list(tool._iter_channels()))
    row = results[results["Energy Label"] == "1 MeV"].iloc[0]
    # resolutions in minutes, times without fractions of seconds
    assert row["Onset Resolution"] == 2
    assert row["Fluence Resolution"] == 30
    assert row["Onset Time"] == (T0 - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    assert row["Low Energy"] == pytest.approx(1.0)
    assert row["High Energy"] == pytest.approx(2.2)


def test_plot_events(tool):
    tool.plot_events()
    assert os.listdir(tool.params.dir_plots) == ["event_001.png"]


def test_run_data_creates_the_cache_folder(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, dir_saves=str(tmp_path / "new" / "cache"), cache_data=True)
    assert os.listdir(tmp_path / "new" / "cache") == ["flux_cache.pkl"]
    assert tool.dfs_flux is not None


def two_events() -> dict:
    return {1: {"Reference Time": T0}, 2: {"Reference Time": T0 + timedelta(days=10)}}


def test_run_data_leaves_out_the_events_without_data(tmp_path, monkeypatch, capsys):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FailingEPD([T0 + timedelta(days=10)], rises)
    tool = synthetic_tool(tmp_path, monkeypatch, events=two_events(), fake=fake)
    assert list(tool.skipped_events) == [2] and list(tool.events.index) == [1]
    assert "1 event left out, as its data could not be loaded: 2 (No data found from" in capsys.readouterr().out
    for step in (tool.run_onsets, tool.run_spikes, tool.run_peaks, tool.run_fluences):
        step()
    assert tool.results_table()["Event No"].unique().tolist() == [1]
    # the event left out is tried again by the next data step
    fake.missing = []
    tool.run_data()
    assert tool.skipped_events == {} and list(tool.events.index) == [1, 2]


def test_run_data_reads_the_energies_of_the_first_event_with_data(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, events=two_events(), fake=FailingEPD([T0]))
    assert list(tool.skipped_events) == [1] and list(tool.events.index) == [2]
    assert list(tool.energies) == ["HET"]


def test_results_table_without_any_onset(tmp_path, monkeypatch):
    # flat flux: no onset in any channel group
    tool = synthetic_tool(tmp_path, monkeypatch, fake=FakeEPD())
    for step in (tool.run_onsets, tool.run_spikes, tool.run_peaks, tool.run_fluences):
        step()
    table = tool.results_table()
    assert table["Onset Time"].isna().all()
    for column in ("Onset Resolution", "Peak Flux Resolution", "Fluence Resolution"):
        assert table[column].isna().all() and table[column].dtype == "float64"


def test_run_data_fails_if_no_event_has_data(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="No data found"):
        synthetic_tool(tmp_path, monkeypatch, events=two_events(), fake=FakeEPD(fail=1000))


def test_run_data_without_the_cache(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, dir_saves=str(tmp_path / "new" / "cache"))
    assert not os.path.exists(tmp_path / "new") and tool.dfs_flux is not None


def test_results_table_has_the_same_type_for_one_or_more_events(tmp_path, monkeypatch):
    # float32 flux, as downloaded EPD data; the results are written as computed, in float64
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    assert tool.dfs_flux["electrons"]["HET"][timedelta(minutes=2)].dtypes.iloc[0] == "float32"
    for column in ("Peak Flux", "Fluence", "Fluence Threshold"):
        assert tool.results_table()[column].dtype == "float64"
