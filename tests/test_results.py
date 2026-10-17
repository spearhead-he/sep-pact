"""Tests of a whole synthetic run: the result tables and the files written by save_results() and plot_events()"""
import os
from datetime import timedelta

import pandas as pd
import pytest

from spearhead.sep_pact.analysis import RESULT_COLUMNS
from tests.helpers import T0, synthetic_tool


@pytest.fixture
def tool(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


def test_every_channel_group_has_results(tool):
    onsets = tool.df_optimals.xs(("Onset Time", "Onset Time"), axis="columns", level=(3, 4))
    assert (onsets == pd.Timestamp(T0 - timedelta(minutes=2))).all().all()
    assert tool.df_optimals.xs(("Fluence", "Fluence"), axis="columns", level=(3, 4)).notna().all().all()


def test_group_energies(tool):
    # the fake channels c have a low energy of c + 1 MeV and a width of (c + 1) * 0.1 MeV
    assert tool.group_energies("electrons", "HET", "1 MeV") == pytest.approx((1.0, 2.2))
    assert tool.group_energies("protons", "HET", "8 MeV") == pytest.approx((2.0, 4.4))


def test_results_table_has_a_row_per_event_and_channel_group(tool):
    table = tool.results_table()
    assert list(table.columns[:6]) == ["Event No", "Particle", "Sensor", "Energy Label", "Low Energy", "High Energy"]
    assert list(table.columns[6:]) == list(RESULT_COLUMNS.values())
    assert list(zip(table["Event No"], table["Particle"], table["Sensor"], table["Energy Label"])) == \
        [(1, particle, sensor, mevlbl) for particle, sensor, mevlbl in tool._iter_channels()]


def test_results_table_has_the_values_of_df_optimals(tool):
    table = tool.results_table().set_index(["Event No", "Particle", "Sensor", "Energy Label"])
    for (event_no, particle, sensor, mevlbl), row in table.iterrows():
        for (quantity, field), column in RESULT_COLUMNS.items():
            value = tool.df_optimals.loc[event_no, (particle, sensor, mevlbl, quantity, field)]
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
    tool = synthetic_tool(tmp_path, monkeypatch, dir_saves=str(tmp_path / "new" / "cache"))
    assert len(os.listdir(tmp_path / "new" / "cache")) == 1
    assert tool.dfs_flux is not None
