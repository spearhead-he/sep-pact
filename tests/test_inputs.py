"""Tests of the input files: the shock list and the event list"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT_parameters
from spearhead.sep_pact.inputs import read_events, read_shocks
from tests.helpers import T0, make_params, write_events, write_shocks


def test_read_shocks_skips_the_comments(tmp_path):
    times = [datetime(2021, 6, 13, 10, 8, 41), datetime(2021, 7, 18, 17, 57, 52)]
    shocks = read_shocks(write_shocks(tmp_path, times))
    assert list(shocks) == [pd.Timestamp(t) for t in times]


def test_read_shocks_of_the_repository():
    shocks = read_shocks("inputs/shocks.dat")
    assert len(shocks) > 0
    assert shocks.iloc[0] == pd.Timestamp(2021, 6, 13, 10, 8, 41)


def test_read_events_with_all_the_columns(tmp_path):
    params = make_params(tmp_path)
    row = {"Onset Time": T0, "BG Start": T0 - timedelta(hours=5), "BG End": T0 - timedelta(hours=1),
           "End Time": T0 + timedelta(days=3)}
    events = read_events(write_events(tmp_path, {7: row}), params)
    assert list(events.index) == [7]
    for column, value in row.items():
        assert events.loc[7, column] == pd.Timestamp(value)


def test_read_events_fills_the_missing_columns(tmp_path):
    params = make_params(tmp_path)
    events = read_events(write_events(tmp_path, {1: {"Onset Time": T0}}), params)
    assert events.loc[1, "BG Start"] == pd.Timestamp(T0 - params.bg_start_before_onset)
    assert events.loc[1, "BG End"] == pd.Timestamp(T0 - params.bg_end_before_onset)
    assert events.loc[1, "End Time"] == pd.Timestamp(T0 + params.end_after_onset)


def test_read_events_fills_the_empty_cells(tmp_path):
    params = make_params(tmp_path, end_after_onset=timedelta(hours=10))
    rows = {1: {"Onset Time": T0, "BG Start": T0 - timedelta(hours=3), "End Time": None},
            2: {"Onset Time": T0, "BG Start": None, "End Time": T0 + timedelta(hours=5)}}
    events = read_events(write_events(tmp_path, rows), params)
    assert events.loc[1, "BG Start"] == pd.Timestamp(T0 - timedelta(hours=3))
    assert events.loc[1, "End Time"] == pd.Timestamp(T0 + timedelta(hours=10))
    assert events.loc[2, "BG Start"] == pd.Timestamp(T0 - params.bg_start_before_onset)
    assert events.loc[2, "End Time"] == pd.Timestamp(T0 + timedelta(hours=5))


def test_short_events_are_extended_equally_on_both_sides(tmp_path):
    params = make_params(tmp_path, min_plot_window=timedelta(days=2))
    row = {"Onset Time": T0, "BG Start": T0 - timedelta(hours=2), "End Time": T0 + timedelta(hours=10)}
    events = read_events(write_events(tmp_path, {1: row}), params)
    # 12 h of event, extended by 18 h on each side to 2 days
    assert events.loc[1, "Plot Start"] == pd.Timestamp(T0 - timedelta(hours=20))
    assert events.loc[1, "Plot End"] == pd.Timestamp(T0 + timedelta(hours=28))


def test_long_events_are_not_extended(tmp_path):
    params = make_params(tmp_path, min_plot_window=timedelta(days=1))
    events = read_events(write_events(tmp_path, {1: {"Onset Time": T0}}), params)
    assert events.loc[1, "Plot Start"] == events.loc[1, "BG Start"]
    assert events.loc[1, "Plot End"] == events.loc[1, "End Time"]


def test_read_events_drops_empty_rows(tmp_path):
    params = make_params(tmp_path)
    rows = {1: {"Onset Time": T0}, 2: {"Onset Time": None}, 3: {"Onset Time": T0 + timedelta(days=5)}}
    events = read_events(write_events(tmp_path, rows), params)
    assert list(events.index) == [1, 3]


def test_read_events_without_onset_time(tmp_path):
    params = make_params(tmp_path)
    path = write_events(tmp_path, {1: {"BG Start": T0}})
    with pytest.raises(ValueError, match="no column \"Onset Time\""):
        read_events(path, params)


def test_read_events_with_spaces_after_the_commas(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Number, Onset Time,          BG Start\n"
                    "4,      2021-01-01 12:00:00, 2021-01-01 09:00:00\n")
    events = read_events(str(path), make_params(tmp_path))
    assert events.index.name == "Event No"
    assert list(events.index) == [4]
    assert events.loc[4, "Onset Time"] == pd.Timestamp(T0)
    assert events.loc[4, "BG Start"] == pd.Timestamp(T0 - timedelta(hours=3))


def test_read_events_times_with_and_without_seconds(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Event No,Onset Time,BG Start\n"
                    "1,2021-01-01 12:00,2021-01-01 09:00:30\n"
                    "2,2021-01-02T12:00:00,\n")
    events = read_events(str(path), make_params(tmp_path))
    assert events.loc[1, "Onset Time"] == pd.Timestamp(T0)
    assert events.loc[1, "BG Start"] == pd.Timestamp(2021, 1, 1, 9, 0, 30)
    assert events.loc[2, "Onset Time"] == pd.Timestamp(T0 + timedelta(days=1))


def test_read_events_times_in_nanoseconds(tmp_path):
    events = read_events(write_events(tmp_path, {1: {"Onset Time": T0}}), make_params(tmp_path))
    for column in ["Onset Time", "BG Start", "BG End", "End Time", "Plot Start", "Plot End"]:
        assert events[column].dtype == "datetime64[ns]"


@pytest.mark.parametrize("name", ["events.xlsx", "events.txt"])
def test_read_events_accepts_only_csv(tmp_path, name):
    path = tmp_path / name
    path.write_text("Event No,Onset Time\n1,2021-01-01 12:00:00\n")
    with pytest.raises(ValueError, match="is not a CSV file. Event lists in Excel or other formats are not accepted"):
        read_events(str(path), make_params(tmp_path))


def test_example_event_list():
    events = read_events("inputs/events_example.csv", SEPPACT_parameters())
    assert list(events.index) == [20]
    assert events.loc[20, "Onset Time"] == pd.Timestamp(2021, 11, 1, 2, 5)
