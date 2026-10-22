"""Tests of the inputs: the event list and the shocks of the parameters"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT_parameters
from spearhead.sep_pact.inputs import (EVENT_LIST_LAYOUTS, load_shocks, make_events, read_event_list, read_events,
                                       shock_warnings)
from tests.helpers import T0, make_params, write_events, write_shocks


def test_load_shocks_of_all_the_sources(tmp_path):
    params = make_params(tmp_path, shock_source="SODA", shock_times=[datetime(2021, 11, 2, 12)],
                         file_shocks=write_shocks(tmp_path, [datetime(2021, 6, 13, 10, 8, 41)]))
    shocks, warnings = load_shocks(params)
    assert warnings == []
    assert shocks["Shock Time"].is_monotonic_increasing
    assert shocks["Source"].value_counts().to_dict() == {"SODA": 18, "shocks.dat": 1, "custom": 1}
    assert shocks.loc[shocks["Source"] == "custom", "Shock Time"].tolist() == [pd.Timestamp(2021, 11, 2, 12)]


def test_load_shocks_without_the_removed_ones(tmp_path):
    params = make_params(tmp_path, shock_source="SODA", file_shocks="", removed_shocks=[datetime(2021, 5, 4, 16, 26, 57)])
    shocks, _ = load_shocks(params)
    assert len(shocks) == 17 and pd.Timestamp(2021, 5, 4, 16, 26, 57) not in shocks["Shock Time"].tolist()


def test_load_shocks_without_a_connection(tmp_path, monkeypatch):
    import spearhead.sep_pact.shocks as module

    def no_connection(url):
        raise OSError("connection refused")

    monkeypatch.setattr(module, "_get", no_connection)
    params = make_params(tmp_path, shock_source="IRFU", file_shocks="", shock_times=[datetime(2021, 11, 2)])
    shocks, warnings = load_shocks(params)
    assert shocks["Source"].tolist() == ["custom"]
    assert warnings == ["The shock list IRFU could not be downloaded (connection refused); it is left out. The data "
                        "server may be unavailable; try again later."]


def test_load_shocks_without_any(tmp_path):
    shocks, warnings = load_shocks(make_params(tmp_path, file_shocks=""))
    assert shocks.empty and list(shocks.columns) == ["Shock Time", "Source"] and warnings == []


def shocks_at(*times, source="SODA") -> pd.DataFrame:
    return pd.DataFrame({"Shock Time": pd.to_datetime(list(times)), "Source": source})


def test_shock_warnings(tmp_path):
    events = read_events(write_events(tmp_path, {1: {"Reference Time": T0}, 2: {"Reference Time": T0 + 30 * HOUR},
                                                 3: {"Reference Time": T0 + 300 * HOUR}}), make_params(tmp_path))
    assert shock_warnings(shocks_at(T0 - 10 * HOUR, T0 + 400 * HOUR), events) == []
    assert shock_warnings(shocks_at(T0 - 10 * HOUR, T0 + 100 * HOUR), events) == [
        "1 event (3) is not within the shock lists (2021-01-01 to 2021-01-05): the shocks during it may be missing."]
    assert shock_warnings(shocks_at(T0 + 100 * HOUR, T0 + 101 * HOUR), events)[0].startswith(
        "3 events (1, 2, 3) are not within the shock lists")
    assert shock_warnings(shocks_at(T0, source="custom"), events) == [
        "There are only custom shocks: the other shocks during the events are not taken into account."]
    assert shock_warnings(shocks_at(), events) == [
        "There are no shocks: the analysis of each channel group goes on to the end time of its event."]


HOUR = timedelta(hours=1)


def times(events, event_no=1) -> list:
    return [events.loc[event_no, column] for column in ("Start Time", "BG Start", "BG End", "End Time")]


def test_reference_times(tmp_path):
    params = make_params(tmp_path)
    events = read_events(write_events(tmp_path, {1: {"Reference Time": T0}}), params)
    # data from 2 hours before to 48 hours after the reference time, background from the start to 1 h 55 min after
    assert times(events) == [pd.Timestamp(t) for t in (T0 - 2 * HOUR, T0 - 2 * HOUR, T0 - timedelta(minutes=5),
                                                       T0 + 48 * HOUR)]
    assert events.loc[1, "Reference Time"] == pd.Timestamp(T0)


def test_reference_times_with_other_windows(tmp_path):
    params = make_params(tmp_path, start_before_reference=5 * HOUR, end_after_reference=10 * HOUR,
                         bg_start_after_start=HOUR, bg_end_after_start=3 * HOUR)
    events = read_events(write_events(tmp_path, {1: {"Reference Time": T0}}), params)
    assert times(events) == [pd.Timestamp(t) for t in (T0 - 5 * HOUR, T0 - 4 * HOUR, T0 - 2 * HOUR, T0 + 10 * HOUR)]


def test_datetime_ranges(tmp_path):
    events = read_events(write_events(tmp_path, {1: {"Start Time": T0, "End Time": T0 + 30 * HOUR}}), make_params(tmp_path))
    assert times(events) == [pd.Timestamp(t) for t in (T0, T0, T0 + timedelta(hours=1, minutes=55), T0 + 30 * HOUR)]
    assert pd.isna(events.loc[1, "Reference Time"])


def test_datetime_ranges_with_the_background_end(tmp_path):
    row = {"Start Time": T0, "BG End": T0 + 3 * HOUR, "End Time": T0 + 30 * HOUR}
    events = read_events(write_events(tmp_path, {1: row}), make_params(tmp_path))
    assert times(events) == [pd.Timestamp(t) for t in (T0, T0, T0 + 3 * HOUR, T0 + 30 * HOUR)]


def test_datetime_ranges_with_the_background_window(tmp_path):
    row = {"Start Time": T0, "BG Start": T0 + HOUR, "BG End": T0 + 3 * HOUR, "End Time": T0 + 30 * HOUR}
    events = read_events(write_events(tmp_path, {7: row}), make_params(tmp_path))
    assert list(events.index) == [7]
    assert times(events, 7) == [pd.Timestamp(t) for t in row.values()]


def test_empty_background_cells_get_the_default_window(tmp_path):
    rows = {1: {"Start Time": T0, "BG Start": None, "BG End": None, "End Time": T0 + 30 * HOUR},
            2: {"Start Time": T0, "BG Start": None, "BG End": T0 + 3 * HOUR, "End Time": T0 + 30 * HOUR}}
    events = read_events(write_events(tmp_path, rows), make_params(tmp_path))
    assert times(events, 1)[1:3] == [pd.Timestamp(T0), pd.Timestamp(T0 + timedelta(hours=1, minutes=55))]
    assert times(events, 2)[1:3] == [pd.Timestamp(T0), pd.Timestamp(T0 + 3 * HOUR)]


def test_columns_in_any_order(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Event No, End Time, Start Time\n1, 2021-01-02 18:00, 2021-01-01 12:00\n")
    events = read_events(str(path), make_params(tmp_path))
    assert times(events)[0::3] == [pd.Timestamp(T0), pd.Timestamp(T0 + 30 * HOUR)]


@pytest.mark.parametrize("columns", [("Start Time",), ("Start Time", "BG Start", "End Time"), ("Reference Time", "End Time"),
                                     ("Start Time", "End Time", "Comment")])
def test_other_columns_are_not_accepted(tmp_path, columns):
    path = write_events(tmp_path, {1: {column: T0 for column in columns}})
    accepted = "Accepted columns:\n    Event No, Reference Time\n    Event No, Start Time, End Time"
    with pytest.raises(ValueError, match=accepted):
        read_events(path, make_params(tmp_path))


def test_former_onset_time_lists(tmp_path):
    path = write_events(tmp_path, {1: {"Onset Time": T0, "BG Start": T0 - 2 * HOUR, "BG End": T0 - HOUR}})
    with pytest.raises(ValueError, match="The Onset Time of former event lists is the Reference Time"):
        read_events(path, make_params(tmp_path))


@pytest.mark.parametrize("row, message", [
    ({"Start Time": T0 + HOUR, "BG Start": T0, "BG End": T0 + 2 * HOUR, "End Time": T0 + 9 * HOUR}, "Start Time <= BG Start"),
    ({"Start Time": T0, "BG Start": T0 + 2 * HOUR, "BG End": T0 + HOUR, "End Time": T0 + 9 * HOUR}, "BG Start < BG End"),
    ({"Start Time": T0, "BG Start": T0, "BG End": T0 + 9 * HOUR, "End Time": T0 + 8 * HOUR}, "BG End < End Time"),
])
def test_windows_in_the_wrong_order(tmp_path, row, message):
    with pytest.raises(ValueError, match=f"Event 1 of the event list .*: the times must be in the order .*{message}"):
        read_events(write_events(tmp_path, {1: row}), make_params(tmp_path))


def test_default_background_after_the_end(tmp_path):
    # a data range shorter than the default background
    path = write_events(tmp_path, {1: {"Start Time": T0, "End Time": T0 + HOUR}})
    with pytest.raises(ValueError, match="BG End < End Time"):
        read_events(path, make_params(tmp_path))


def test_missing_times(tmp_path):
    path = write_events(tmp_path, {1: {"Start Time": T0, "End Time": T0 + 30 * HOUR}, 2: {"Start Time": T0, "End Time": None}})
    with pytest.raises(ValueError, match="Event 2 of the event list .* has no End Time"):
        read_events(path, make_params(tmp_path))


def test_short_events_are_extended_equally_on_both_sides(tmp_path):
    params = make_params(tmp_path, min_plot_window=timedelta(days=2))
    row = {"Start Time": T0 - 2 * HOUR, "End Time": T0 + 10 * HOUR}
    events = read_events(write_events(tmp_path, {1: row}), params)
    # 12 h of event, extended by 18 h on each side to 2 days
    assert events.loc[1, "Plot Start"] == pd.Timestamp(T0 - timedelta(hours=20))
    assert events.loc[1, "Plot End"] == pd.Timestamp(T0 + timedelta(hours=28))


def test_long_events_are_not_extended(tmp_path):
    params = make_params(tmp_path, min_plot_window=timedelta(days=1))
    events = read_events(write_events(tmp_path, {1: {"Reference Time": T0}}), params)
    assert events.loc[1, "Plot Start"] == events.loc[1, "Start Time"]
    assert events.loc[1, "Plot End"] == events.loc[1, "End Time"]


def test_read_events_drops_empty_rows(tmp_path):
    rows = {1: {"Reference Time": T0}, 2: {"Reference Time": None}, 3: {"Reference Time": T0 + timedelta(days=5)}}
    events = read_events(write_events(tmp_path, rows), make_params(tmp_path))
    assert list(events.index) == [1, 3]


def test_read_events_with_spaces_after_the_commas(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Number, Reference Time\n"
                    "4,      2021-01-01 12:00:00\n")
    events = read_events(str(path), make_params(tmp_path))
    assert events.index.name == "Event No"
    assert list(events.index) == [4]
    assert events.loc[4, "Reference Time"] == pd.Timestamp(T0)


def test_read_events_times_with_and_without_seconds(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Event No,Start Time,End Time\n"
                    "1,2021-01-01 12:00,2021-01-02 12:00:30\n"
                    "2,2021-01-02T12:00:00,2021-01-03 12:00\n")
    events = read_events(str(path), make_params(tmp_path))
    assert events.loc[1, "Start Time"] == pd.Timestamp(T0)
    assert events.loc[1, "End Time"] == pd.Timestamp(2021, 1, 2, 12, 0, 30)
    assert events.loc[2, "Start Time"] == pd.Timestamp(T0 + timedelta(days=1))


def test_read_events_times_in_nanoseconds(tmp_path):
    events = read_events(write_events(tmp_path, {1: {"Reference Time": T0}}), make_params(tmp_path))
    for column in ["Start Time", "BG Start", "BG End", "End Time", "Reference Time", "Plot Start", "Plot End"]:
        assert events[column].dtype == "datetime64[ns]"


@pytest.mark.parametrize("name", ["events.xlsx", "events.txt"])
def test_read_events_accepts_only_csv(tmp_path, name):
    path = tmp_path / name
    path.write_text("Event No,Reference Time\n1,2021-01-01 12:00:00\n")
    with pytest.raises(ValueError, match="is not a CSV file. Event lists in Excel or other formats are not accepted"):
        read_events(str(path), make_params(tmp_path))


def test_date_ranges_without_an_event_list(tmp_path):
    params = make_params(tmp_path, file_events="", date_ranges=[(T0, T0 + 30 * HOUR), (T0 + 72 * HOUR, T0 + 96 * HOUR)])
    events = make_events(params)
    assert list(events.index) == [1, 2]
    assert times(events, 2) == [pd.Timestamp(t) for t in (T0 + 72 * HOUR, T0 + 72 * HOUR,
                                                          T0 + 72 * HOUR + timedelta(hours=1, minutes=55), T0 + 96 * HOUR)]


def test_no_events(tmp_path):
    with pytest.raises(ValueError, match="There are no events: give an event list"):
        make_events(make_params(tmp_path, file_events=""))


def test_make_events_reads_the_event_list(tmp_path):
    params = make_params(tmp_path, date_ranges=[(T0, T0 + 30 * HOUR)])
    write_events(tmp_path / "inputs", {5: {"Reference Time": T0}})
    assert list(make_events(params).index) == [5]


@pytest.mark.parametrize("name", ["events_example", "reference_times_example", "datetime_range_only_example",
                                  "datetime_range_example"])
def test_example_event_lists(name):
    events = read_events(f"inputs/{name}.csv", SEPPACT_parameters())
    assert list(events.index) == [20]
    assert events.loc[20, "End Time"] == pd.Timestamp(2021, 11, 3, 2, 5)


def test_example_event_list_keeps_the_windows_of_the_former_one():
    # the former example: Onset Time 2021-11-01 02:05, BG Start 2021-10-31 19:00, BG End 2021-11-01 01:30
    events = read_events("inputs/events_example.csv", SEPPACT_parameters())
    assert times(events, 20) == [pd.Timestamp(2021, 10, 31, 19), pd.Timestamp(2021, 10, 31, 19),
                                 pd.Timestamp(2021, 11, 1, 1, 30), pd.Timestamp(2021, 11, 3, 2, 5)]
    assert (events.loc[20, "Plot Start"], events.loc[20, "Plot End"]) == (pd.Timestamp(2021, 10, 31, 19),
                                                                          pd.Timestamp(2021, 11, 3, 2, 5))


def test_layouts_as_in_the_vda_tool():
    assert list(EVENT_LIST_LAYOUTS.values()) == [("Reference Time",), ("Start Time", "End Time"),
                                                 ("Start Time", "BG End", "End Time"),
                                                 ("Start Time", "BG Start", "BG End", "End Time")]


def test_event_list_with_the_windows_of_particles_and_sensors(tmp_path, capsys):
    path = tmp_path / "events.csv"
    path.write_text("Event No,Particle,Sensor,Start Time,BG Start,BG End,End Time\n"
                    "1,,,2021-01-01 12:00,2021-01-01 12:00,2021-01-01 13:00,2021-01-02 18:00\n"
                    "1,protons,HET,,2021-01-01 12:00,2021-01-01 15:00,\n"
                    "\n"
                    "2,protons,,2021-01-05 12:00,,2021-01-05 14:00,\n"
                    "2,electrons,HET,,,2021-01-05 13:00,2021-01-06 12:00\n")
    event_times, windows = read_event_list(str(path))
    assert list(event_times.columns) == ["Start Time", "End Time", "BG Start", "BG End"]
    assert list(event_times.loc[1]) == [pd.Timestamp(t) for t in (T0, T0 + 30 * HOUR, T0, T0 + HOUR)]
    # the times of event 2 from the rows of its particles, without a window of the event
    assert list(event_times.loc[2, ["Start Time", "End Time"]]) == [pd.Timestamp(T0 + 96 * HOUR),
                                                                    pd.Timestamp(T0 + 120 * HOUR)]
    assert pd.isna(event_times.loc[2, "BG End"])
    assert list(windows.index) == [(1, "protons", "HET"), (2, "protons", ""), (2, "electrons", "HET")]
    assert windows.loc[(1, "protons", "HET"), "BG End"] == pd.Timestamp(T0 + 3 * HOUR)
    assert pd.isna(windows.loc[(2, "protons", ""), "BG Start"])
    assert capsys.readouterr().out == ""
    # the events take the times and the window of the event
    events = read_events(str(path), make_params(tmp_path))
    assert times(events, 1) == [pd.Timestamp(t) for t in (T0, T0, T0 + HOUR, T0 + 30 * HOUR)]
    assert events.loc[2, "BG Window Source"] == "default"


def test_event_list_with_a_time_given_twice(tmp_path, capsys):
    path = tmp_path / "events.csv"
    path.write_text("Event No,Particle,Sensor,Start Time,End Time\n"
                    "1,,,2021-01-01 12:00,2021-01-02 18:00\n"
                    "1,,,2021-01-01 12:00:00,2021-01-02 20:00\n")
    events = read_events(str(path), make_params(tmp_path))
    assert events.loc[1, "End Time"] == pd.Timestamp(T0 + 32 * HOUR)
    # the same Start Time in another format gives no message
    assert capsys.readouterr().out == (f"The event list {path}: Event 1: End Time is given 2 times (2021-01-02 18:00:00 "
                                       "in line 2, 2021-01-02 20:00:00 in line 3); the last one is used.\n")


def test_event_list_rows_of_the_same_event_without_particles(tmp_path, capsys):
    rows = "Event No,Start Time,End Time\n1,2021-01-01 12:00,\n1,,2021-01-02 18:00\n"
    path = tmp_path / "events.csv"
    path.write_text(rows)
    events = read_events(str(path), make_params(tmp_path))
    assert times(events)[0::3] == [pd.Timestamp(T0), pd.Timestamp(T0 + 30 * HOUR)]
    assert capsys.readouterr().out == ""


def test_event_list_row_without_an_event_number(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("Event No,Start Time,End Time\n1,2021-01-01 12:00,2021-01-02 18:00\n,2021-01-01 12:00,\n")
    with pytest.raises(ValueError, match="Line 3 of the event list .* has no Event No"):
        read_events(str(path), make_params(tmp_path))


def test_event_list_with_particles_and_other_columns(tmp_path):
    path = write_events(tmp_path, {1: {"Particle": "protons", "Sensor": "HET", "Start Time": T0, "Comment": T0}})
    with pytest.raises(ValueError, match="with optionally Particle and Sensor"):
        read_events(path, make_params(tmp_path))
