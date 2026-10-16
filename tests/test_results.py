"""Tests of a whole synthetic run: the result tables and the files written by save_results() and plot_events()"""
import os
from datetime import timedelta

import pandas as pd
import pytest

from tests.helpers import BACKGROUND, T0, synthetic_tool


@pytest.fixture
def tool(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


BG_MEANS_BUG = pytest.mark.xfail(
    strict=True, reason="bg_means.csv is the mean flux of the whole data period of the event, not of the background window")


@BG_MEANS_BUG
def test_background_means(tool):
    assert tool.df_means.loc[1, "1 MeV electrons sun 2m"] == pytest.approx(BACKGROUND)
    assert tool.df_means.loc[1, "50 MeV protons south 30m"] == pytest.approx(BACKGROUND)


def test_background_means_columns(tool):
    assert list(tool.df_means.columns[:2]) == ["BG Start", "BG End"]
    assert len(tool.df_means.columns) == 2 + 5 * 4 * 4  # groups, viewings, resolutions


def test_every_channel_group_has_results(tool):
    onsets = tool.df_optimals.xs(("Onset Time", "Onset Time"), axis="columns", level=(3, 4))
    assert (onsets == pd.Timestamp(T0 - timedelta(minutes=2))).all().all()
    assert tool.df_optimals.xs(("Fluence", "Fluence"), axis="columns", level=(3, 4)).notna().all().all()


def test_save_results(tool):
    tool.save_results()
    folder = tool.params.dir_outputs
    assert sorted(os.listdir(folder)) == ["bg_means.csv", "latest_onsets.csv", "optimals.xlsx"]
    optimals = pd.read_excel(os.path.join(folder, "optimals.xlsx"), header=[0, 1, 2, 3, 4], index_col=0)
    # resolutions in minutes
    assert optimals.loc[1, ("electrons", "HET", "1 MeV", "Onset Time", "Resolution")] == 2
    assert optimals.loc[1, ("electrons", "HET", "1 MeV", "Fluence", "Resolution")] == 30
    onset = optimals.loc[1, ("electrons", "HET", "1 MeV", "Onset Time", "Onset Time")]
    assert onset == pd.Timestamp(T0 - timedelta(minutes=2))
    bg_means = pd.read_csv(os.path.join(folder, "bg_means.csv"), index_col=0)
    assert list(bg_means.index) == [1] and "8 MeV protons north 10m" in bg_means.columns


def test_plot_events(tool):
    tool.plot_events()
    assert os.listdir(tool.params.dir_plots) == ["event_001.png"]


def test_run_data_creates_the_cache_folder(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, dir_saves=str(tmp_path / "new" / "cache"))
    assert len(os.listdir(tmp_path / "new" / "cache")) == 1
    assert tool.dfs_flux is not None
