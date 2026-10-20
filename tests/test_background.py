"""Tests of the background windows: their source, setting and resetting them, their points, and save_events()"""
from datetime import timedelta

import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT
from spearhead.sep_pact.inputs import read_events
from tests.helpers import T0, bg_end_event, make_params, synthetic_tool, write_events, write_shocks

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


@pytest.fixture
def tool(tmp_path, monkeypatch):
    return synthetic_tool(tmp_path, monkeypatch)


def window(tool, event_no=1) -> list:
    return list(tool.events.loc[event_no, ["BG Start", "BG End", "BG Window Source"]])


def test_bg_window_of_the_event_list_and_default(tmp_path):
    rows = {1: {"Start Time": T0, "End Time": T0 + 30 * HOUR},
            2: {"Start Time": T0, "BG End": T0 + 3 * HOUR, "End Time": T0 + 30 * HOUR},
            3: {"Start Time": T0, "BG Start": T0 + HOUR, "BG End": T0 + 3 * HOUR, "End Time": T0 + 30 * HOUR}}
    events = read_events(write_events(tmp_path, rows), make_params(tmp_path))
    assert list(events["BG Window Source"]) == ["default", "event list", "event list"]
    assert list(events["End Time Source"]) == ["event list"] * 3


def test_bg_window_of_date_ranges(tmp_path):
    params = make_params(tmp_path, file_events="", date_ranges=[(T0, T0 + 30 * HOUR)])
    tool = SEPPACT(params)
    write_shocks(tmp_path / "inputs", [T0])
    tool.run_inputs()
    assert list(tool.events["BG Window Source"]) == ["default"]
    assert list(tool.events["End Time Source"]) == ["event list"]


def test_set_bg_window(tool):
    tool.set_bg_window(1, T0 - HOUR, "2021-01-01 11:30")
    assert window(tool) == [pd.Timestamp(T0 - HOUR), pd.Timestamp(T0 - 30 * MINUTE), "set"]
    assert tool.events["BG Start"].dtype == "datetime64[ns]"


@pytest.mark.parametrize("start, end", [
    (T0 - 3 * HOUR, T0 - HOUR),          # before the start time
    (T0 - HOUR, T0 - HOUR),              # empty
    (T0 - HOUR, T0 - 2 * HOUR),          # end before start
    (T0, T0 + 49 * HOUR),                # after the end time
])
def test_set_bg_window_outside_the_data_range_or_in_the_wrong_order(tool, start, end):
    before = window(tool)
    with pytest.raises(ValueError, match="The background window of event 1 is not valid: the times must be in the "
                                         "order Start Time <= BG Start < BG End < End Time"):
        tool.set_bg_window(1, start, end)
    assert window(tool) == before


def test_reset_bg_window_to_the_default(tool):
    default = window(tool)
    tool.set_bg_window(1, T0 - HOUR, T0 - 30 * MINUTE)
    tool.reset_bg_window(1)
    assert window(tool) == default
    assert default[2] == "default"


def test_reset_bg_window_to_the_event_list(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, events={1: bg_end_event(T0 - 30 * MINUTE)})
    tool.set_bg_window(1, T0 - HOUR, T0 - 45 * MINUTE)
    tool.reset_bg_window(1)
    assert window(tool) == [pd.Timestamp(T0 - 2 * HOUR), pd.Timestamp(T0 - 30 * MINUTE), "event list"]


def test_set_bg_window_changes_the_onset_search(tool):
    # the synthetic flux rises at T0; with the background ending after it, the onset is found later
    tool.run_onsets()
    assert tool.df_results["Onset Time"].iloc[0] < pd.Timestamp(T0)
    tool.set_bg_window(1, T0 - 2 * HOUR, T0 + 30 * MINUTE)
    tool.run_onsets()
    assert tool.df_results["Onset Time"].iloc[0] >= pd.Timestamp(T0 + 30 * MINUTE)


def test_bg_window_points(tool):
    # the default window, 1 h 55 min of data
    assert tool.bg_window_points(1) == {timedelta(minutes=2): 58, timedelta(minutes=5): 24, timedelta(minutes=10): 12,
                                        timedelta(minutes=30): 4}
    assert tool.bg_window_warnings(1) == []


def test_bg_window_warnings(tool):
    tool.set_bg_window(1, T0 - HOUR, T0 - 40 * MINUTE)
    assert tool.bg_window_points(1)[timedelta(minutes=30)] == 1
    assert tool.bg_window_warnings(1) == [
        "The background window of event 1 has 1 point at the 30 min resolution in a series (fewer than 3)."]


def test_bg_window_points_without_data(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    flux = tool.dfs_flux["electrons"]["HET"][timedelta(minutes=10)]
    # no data from 10:00 to 11:00 in one series: 5 of the 12 points of the window (10:00 to 11:50) are left
    flux.loc[(1, slice(T0 - 2 * HOUR, T0 - HOUR)), flux.columns[0]] = float("nan")
    assert tool.bg_window_points(1)[timedelta(minutes=10)] == 5


def test_save_events_keeps_the_windows(tool, tmp_path):
    tool.set_bg_window(1, T0 - HOUR, T0 - 30 * MINUTE)
    path = str(tmp_path / "saved.csv")
    tool.save_events(path)
    assert pd.read_csv(path).columns.tolist() == ["Event No", "Start Time", "BG Start", "BG End", "End Time"]
    events = read_events(path, tool.params)
    columns = ["Start Time", "BG Start", "BG End", "End Time", "Plot Start", "Plot End"]
    pd.testing.assert_frame_equal(events[columns], tool.events[columns])
    assert list(events["BG Window Source"]) == ["event list"]


def end_time(tool, event_no=1) -> list:
    return list(tool.events.loc[event_no, ["End Time", "End Time Source"]])


def test_end_time_of_reference_times(tool):
    assert end_time(tool) == [pd.Timestamp(T0 + 48 * HOUR), "default"]


def test_set_end_time(tool):
    tool.set_end_time(1, "2021-01-02 12:00")
    assert end_time(tool) == [pd.Timestamp(T0 + 24 * HOUR), "set"]
    assert tool.events["End Time"].dtype == "datetime64[ns]"
    # the background window is not changed
    assert window(tool)[2] == "default"


@pytest.mark.parametrize("end, message", [
    (T0 - 5 * MINUTE, "is not valid: the times must be in the order Start Time <= BG Start < BG End < End Time"),
    (T0 - 2 * HOUR, "is not valid: the times must be in the order"),
    (T0 + 49 * HOUR, r"\(2021-01-03 13:00:00\) is after the end of its data \(2021-01-03 12:00:00\). To extend it, "
                     "change the event list and run the data step again"),
])
def test_set_end_time_before_the_background_or_after_the_data(tool, end, message):
    before = end_time(tool)
    with pytest.raises(ValueError, match=f"The end time of event 1 ?{message}"):
        tool.set_end_time(1, end)
    assert end_time(tool) == before


def test_reset_end_time_and_bg_window_separately(tool):
    tool.set_end_time(1, T0 + 24 * HOUR)
    tool.set_bg_window(1, T0 - HOUR, T0 - 30 * MINUTE)
    tool.reset_bg_window(1)
    assert window(tool)[2] == "default" and end_time(tool)[1] == "set"
    tool.set_bg_window(1, T0 - HOUR, T0 - 30 * MINUTE)
    tool.reset_end_time(1)
    assert end_time(tool) == [pd.Timestamp(T0 + 48 * HOUR), "default"] and window(tool)[2] == "set"


def test_set_end_time_changes_the_analysis(tool):
    # with the end time before the rise of the flux, there is no onset
    tool.set_end_time(1, T0 - MINUTE)
    tool.run_onsets()
    assert tool.df_results["Onset Time"].isna().all()


def test_save_events_keeps_the_end_time(tool, tmp_path):
    tool.set_end_time(1, T0 + 47 * HOUR)
    path = str(tmp_path / "saved.csv")
    tool.save_events(path)
    events = read_events(path, tool.params)
    assert events.loc[1, "End Time"] == pd.Timestamp(T0 + 47 * HOUR)
    assert list(events.loc[1, ["BG Window Source", "End Time Source"]]) == ["event list", "event list"]
