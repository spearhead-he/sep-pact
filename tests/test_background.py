"""Tests of the background windows per event, particle and sensor (background)"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from spearhead.sep_pact.background import (BackgroundWindows, key_label, order_error, split_event_rows,
                                           window_points)

T0 = pd.Timestamp(2021, 1, 1, 12)
HOUR = timedelta(hours=1)
DEFAULT = (timedelta(0), 2 * HOUR)


def ranges(*event_nos) -> pd.DataFrame:
    """Events from T0 + (n - 1) days, 30 h long"""
    starts = [T0 + timedelta(days=n - 1) for n in event_nos]
    return pd.DataFrame({"Start Time": starts, "End Time": [start + 30 * HOUR for start in starts]},
                        index=pd.Index(event_nos, name="Event No"))


def windows(rows: dict) -> pd.DataFrame:
    """{(event_no, particle, sensor): (bg_start, bg_end)} as the windows of an event list"""
    return pd.DataFrame(list(rows.values()), columns=["BG Start", "BG End"],
                        index=pd.MultiIndex.from_tuples(list(rows), names=["Event No", "Particle", "Sensor"]))


def event_rows(rows: list[dict]) -> pd.DataFrame:
    """The rows of an event list, indexed by their line in the file"""
    df = pd.DataFrame(rows).reindex(columns=["Event No", "Particle", "Sensor", "Start Time", "BG Start", "BG End",
                                             "End Time"])
    return df.set_axis(range(2, len(df) + 2))


# split_event_rows

def test_split_event_rows_without_particles():
    df = event_rows([{"Event No": 1, "Start Time": T0, "BG End": T0 + HOUR, "End Time": T0 + 30 * HOUR},
                     {"Event No": 2, "Start Time": T0 + 48 * HOUR, "End Time": T0 + 60 * HOUR}])
    times, own, messages = split_event_rows(df)
    assert list(times.index) == [1, 2]
    assert list(times.columns) == ["Start Time", "End Time", "BG Start", "BG End"]
    assert times.loc[1, "BG End"] == T0 + HOUR
    assert pd.isna(times.loc[2, "BG End"])
    assert own.empty
    assert messages == []


def test_split_event_rows_with_the_window_of_a_particle_and_sensor():
    df = event_rows([{"Event No": 2, "Start Time": T0, "BG End": T0 + HOUR, "End Time": T0 + 30 * HOUR},
                     {"Event No": 2, "Particle": "protons", "Sensor": "HET", "BG Start": T0 + HOUR,
                      "BG End": T0 + 3 * HOUR}])
    times, own, messages = split_event_rows(df)
    assert list(times.index) == [2]
    assert times.loc[2, "BG End"] == T0 + HOUR
    assert list(own.index) == [(2, "protons", "HET")]
    assert list(own.loc[(2, "protons", "HET")]) == [T0 + HOUR, T0 + 3 * HOUR]
    assert messages == []


def test_split_event_rows_takes_the_times_of_the_event_from_any_row():
    # no row of the event itself: the times are in the rows of the particles
    df = event_rows([{"Event No": 3, "Particle": "protons", "Sensor": "HET", "Start Time": T0, "BG End": T0 + HOUR},
                     {"Event No": 3, "Particle": "electrons", "Sensor": "HET", "BG End": T0 + 2 * HOUR,
                      "End Time": T0 + 30 * HOUR}])
    times, own, messages = split_event_rows(df)
    assert list(times.loc[3, ["Start Time", "End Time"]]) == [T0, T0 + 30 * HOUR]
    # no window of the event: it gets the default one later
    assert pd.isna(times.loc[3, "BG End"])
    assert list(own.index) == [(3, "protons", "HET"), (3, "electrons", "HET")]
    assert messages == []


def test_split_event_rows_uses_the_last_time_with_a_message():
    df = event_rows([{"Event No": 2, "Start Time": T0, "End Time": T0 + 30 * HOUR},
                     {"Event No": 2, "Particle": "protons", "Sensor": "HET", "Start Time": T0 + HOUR,
                      "BG End": T0 + 3 * HOUR},
                     {"Event No": 2, "Start Time": T0 + 2 * HOUR}])
    times, _, messages = split_event_rows(df)
    assert times.loc[2, "Start Time"] == T0 + 2 * HOUR
    assert messages == ["Event 2: Start Time is given 3 times (2021-01-01 12:00:00 in line 2, 2021-01-01 13:00:00 in "
                        "line 3, 2021-01-01 14:00:00 in line 4); the last one is used."]


def test_split_event_rows_same_times_give_no_message():
    row = {"Event No": 2, "Start Time": T0, "End Time": T0 + 30 * HOUR}
    times, _, messages = split_event_rows(event_rows([row, row]))
    assert list(times.index) == [2]
    assert messages == []


def test_split_event_rows_uses_the_last_window_of_a_particle_and_sensor_with_a_message():
    df = event_rows([{"Event No": 2, "Start Time": T0, "End Time": T0 + 30 * HOUR},
                     {"Event No": 2, "Particle": "protons", "Sensor": "HET", "BG End": T0 + 3 * HOUR},
                     {"Event No": 2, "Particle": "protons", "Sensor": "HET", "BG End": T0 + 4 * HOUR},
                     {"Event No": 2, "Particle": "protons", "BG End": T0 + 5 * HOUR}])
    _, own, messages = split_event_rows(df)
    assert own.loc[(2, "protons", "HET"), "BG End"] == T0 + 4 * HOUR
    # the window of the particle is another one
    assert own.loc[(2, "protons", ""), "BG End"] == T0 + 5 * HOUR
    assert messages == ["Event 2, protons HET: BG End is given 2 times (2021-01-01 15:00:00 in line 3, "
                        "2021-01-01 16:00:00 in line 4); the last one is used."]


def test_split_event_rows_uses_the_last_window_of_the_event_with_a_message():
    df = event_rows([{"Event No": 2, "Start Time": T0, "BG End": T0 + HOUR, "End Time": T0 + 30 * HOUR},
                     {"Event No": 2, "BG End": T0 + 2 * HOUR}])
    times, _, messages = split_event_rows(df)
    assert times.loc[2, "BG End"] == T0 + 2 * HOUR
    assert messages == ["Event 2: BG End is given 2 times (2021-01-01 13:00:00 in line 2, 2021-01-01 14:00:00 in "
                        "line 3); the last one is used."]


def test_split_event_rows_strips_the_names():
    df = event_rows([{"Event No": 1, "Start Time": T0, "End Time": T0 + 30 * HOUR},
                     {"Event No": 1, "Particle": " protons ", "Sensor": "HET ", "BG End": T0 + HOUR}])
    assert list(split_event_rows(df)[1].index) == [(1, "protons", "HET")]


def test_split_event_rows_sensor_without_a_particle():
    df = event_rows([{"Event No": 1, "Sensor": "HET", "Start Time": T0, "BG End": T0 + HOUR,
                      "End Time": T0 + 30 * HOUR}])
    with pytest.raises(ValueError, match="Line 2 of the event list has a Sensor without a Particle"):
        split_event_rows(df)


def test_split_event_rows_particle_without_a_window():
    df = event_rows([{"Event No": 1, "Start Time": T0, "End Time": T0 + 30 * HOUR},
                     {"Event No": 1, "Particle": "protons", "Sensor": "HET", "BG Start": T0}])
    with pytest.raises(ValueError, match="The row of event 1, protons HET in the event list has no BG End"):
        split_event_rows(df)


# BackgroundWindows

def test_window_of_the_event_list_and_the_default_one():
    bg = BackgroundWindows(ranges(1, 2), windows({(1, "", ""): (T0 + HOUR, T0 + 3 * HOUR)}), DEFAULT)
    assert bg.window(1) == (T0 + HOUR, T0 + 3 * HOUR, "event list", "", "")
    start_2 = T0 + timedelta(days=1)
    assert bg.window(2) == (start_2, start_2 + 2 * HOUR, "default", "", "")


def test_window_without_a_background_start_starts_at_the_start_time():
    bg = BackgroundWindows(ranges(1), windows({(1, "", ""): (pd.NaT, T0 + 3 * HOUR),
                                               (1, "protons", "HET"): (pd.NaT, T0 + 4 * HOUR)}), DEFAULT)
    assert bg.window(1)[:2] == (T0, T0 + 3 * HOUR)
    assert bg.window(1, "protons", "HET")[:2] == (T0, T0 + 4 * HOUR)


def test_window_of_a_series_falls_back_to_its_particle_then_to_the_event():
    bg = BackgroundWindows(ranges(1), windows({(1, "protons", "HET"): (T0, T0 + 3 * HOUR),
                                               (1, "protons", ""): (T0, T0 + 4 * HOUR)}), DEFAULT)
    assert bg.window(1, "protons", "HET") == (T0, T0 + 3 * HOUR, "event list", "protons", "HET")
    assert bg.window(1, "protons", "EPT") == (T0, T0 + 4 * HOUR, "event list", "protons", "")
    assert bg.window(1, "electrons", "HET") == (T0, T0 + 2 * HOUR, "default", "", "")
    assert bg.own_windows() == [(1, "protons", "HET"), (1, "protons", "")]


def test_window_of_an_unknown_event():
    with pytest.raises(KeyError, match="There is no event 5"):
        BackgroundWindows(ranges(1)).window(5)


def test_windows_of_unknown_events():
    with pytest.raises(ValueError, match="The background windows of the events 4 are of no event"):
        BackgroundWindows(ranges(1), windows({(4, "", ""): (T0, T0 + HOUR)}))


@pytest.mark.parametrize("key, window", [
    ((1, "", ""), (T0 - HOUR, T0 + HOUR)),
    ((1, "protons", "HET"), (T0 + 3 * HOUR, T0 + 2 * HOUR)),
    ((1, "protons", ""), (T0, T0 + 31 * HOUR)),
])
def test_windows_outside_the_data_range(key, window):
    message = f"The background window of {key_label(*key)} is not valid: the times must be in the order"
    with pytest.raises(ValueError, match=message):
        BackgroundWindows(ranges(1), windows({key: window}))


def test_set_and_reset_the_window_of_the_event():
    bg = BackgroundWindows(ranges(1, 2), windows({(1, "", ""): (T0 + HOUR, T0 + 3 * HOUR)}), DEFAULT)
    bg.set(1, T0, datetime(2021, 1, 1, 18))
    assert bg.window(1) == (T0, T0 + 6 * HOUR, "set", "", "")
    bg.reset(1)
    assert bg.window(1) == (T0 + HOUR, T0 + 3 * HOUR, "event list", "", "")
    start_2 = T0 + timedelta(days=1)
    bg.set(2, start_2, start_2 + HOUR)
    bg.reset(2)
    assert bg.window(2) == (start_2, start_2 + 2 * HOUR, "default", "", "")


def test_set_and_reset_the_window_of_a_particle_and_sensor():
    bg = BackgroundWindows(ranges(1), windows({(1, "protons", ""): (T0, T0 + 4 * HOUR)}), DEFAULT)
    bg.set(1, T0, T0 + 5 * HOUR, "electrons", "HET")
    bg.set(1, T0, T0 + 6 * HOUR, "protons")
    assert bg.window(1, "electrons", "HET") == (T0, T0 + 5 * HOUR, "set", "electrons", "HET")
    assert bg.window(1, "protons", "HET") == (T0, T0 + 6 * HOUR, "set", "protons", "")
    bg.reset(1, "electrons", "HET")
    bg.reset(1, "protons")
    # removed, and back to the event list
    assert bg.window(1, "electrons", "HET")[2:] == ("default", "", "")
    assert bg.window(1, "protons", "HET") == (T0, T0 + 4 * HOUR, "event list", "protons", "")
    # nothing to reset
    bg.reset(1, "electrons", "HET")
    assert bg.own_windows() == [(1, "protons", "")]


def test_set_a_window_outside_the_data_range():
    bg = BackgroundWindows(ranges(1), default=DEFAULT)
    with pytest.raises(ValueError, match="The background window of event 1, protons HET is not valid: the times must be "
                                         "in the order Start Time <= BG Start < BG End < End Time"):
        bg.set(1, T0 + 3 * HOUR, T0 + 2 * HOUR, "protons", "HET")
    assert bg.own_windows() == []


def test_set_a_window_of_a_sensor_without_its_particle():
    with pytest.raises(ValueError, match="A background window of a sensor needs its particle"):
        BackgroundWindows(ranges(1)).set(1, T0, T0 + HOUR, sensor="HET")


def test_set_a_window_of_an_unknown_event():
    with pytest.raises(KeyError, match="There is no event 3"):
        BackgroundWindows(ranges(1)).set(3, T0, T0 + HOUR)


def test_set_default_changes_only_the_default_windows():
    bg = BackgroundWindows(ranges(1, 2, 3), windows({(1, "", ""): (T0 + HOUR, T0 + 3 * HOUR)}), DEFAULT)
    start_3 = T0 + timedelta(days=2)
    bg.set(3, start_3, start_3 + 5 * HOUR)
    bg.set_default(HOUR, 4 * HOUR)
    start_2 = T0 + timedelta(days=1)
    assert bg.window(1)[:3] == (T0 + HOUR, T0 + 3 * HOUR, "event list")
    assert bg.window(2)[:3] == (start_2 + HOUR, start_2 + 4 * HOUR, "default")
    assert bg.window(3)[:3] == (start_3, start_3 + 5 * HOUR, "set")
    # reset uses the new default
    bg.reset(3)
    assert bg.window(3)[:3] == (start_3 + HOUR, start_3 + 4 * HOUR, "default")


def test_set_default_outside_the_data_range():
    bg = BackgroundWindows(ranges(1), default=DEFAULT)
    with pytest.raises(ValueError, match="The background window of event 1 is not valid: the times must be in the order"):
        bg.set_default(HOUR, 40 * HOUR)
    assert bg.default == DEFAULT
    assert bg.window(1)[:2] == (T0, T0 + 2 * HOUR)


def test_set_end_time_after_all_the_windows():
    bg = BackgroundWindows(ranges(1), windows({(1, "protons", "HET"): (T0, T0 + 10 * HOUR)}), DEFAULT)
    bg.set_end_time(1, T0 + 11 * HOUR)
    assert bg.ranges.loc[1, "End Time"] == T0 + 11 * HOUR
    message = r"The end time of event 1 is not valid \(the background window of event 1, protons HET\): the times"
    with pytest.raises(ValueError, match=message):
        bg.set_end_time(1, T0 + 9 * HOUR)
    assert bg.ranges.loc[1, "End Time"] == T0 + 11 * HOUR


def test_check_names_writes_them_as_given():
    bg = BackgroundWindows(ranges(1), windows({(1, "Protons", "het"): (T0, T0 + 3 * HOUR),
                                               (1, "ELECTRONS", ""): (T0, T0 + 4 * HOUR)}), DEFAULT)
    bg.check_names({"electrons": ["HET"], "protons": ["HET", "EPT"]})
    assert bg.own_windows() == [(1, "protons", "HET"), (1, "electrons", "")]
    # reset keeps the windows of the event list
    bg.set(1, T0, T0 + 5 * HOUR, "protons", "HET")
    bg.reset(1, "protons", "HET")
    assert bg.window(1, "protons", "HET")[:3] == (T0, T0 + 3 * HOUR, "event list")


@pytest.mark.parametrize("key, message", [
    ((1, "ions", "HET"), "The background window of event 1, ions HET: there is no ions HET. The particles and their sensors "
                         "are: electrons: HET; protons: HET, EPT."),
    ((1, "protons", "STEP"), "there is no protons STEP."),
    ((1, "ions", ""), "The background window of event 1, ions: there is no ions. The particles"),
])
def test_check_names_of_unknown_particles_and_sensors(key, message):
    bg = BackgroundWindows(ranges(1), windows({key: (T0, T0 + 3 * HOUR)}))
    with pytest.raises(ValueError, match=message):
        bg.check_names({"electrons": ["HET"], "protons": ["HET", "EPT"]})


def test_check_names_of_the_same_particle_and_sensor_twice():
    bg = BackgroundWindows(ranges(1), windows({(1, "protons", "HET"): (T0, T0 + 3 * HOUR),
                                               (1, "Protons", "HET"): (T0, T0 + 4 * HOUR)}))
    with pytest.raises(ValueError, match="There is more than one background window of event 1, protons HET"):
        bg.check_names({"protons": ["HET"]})


def test_to_frame_lists_the_window_of_each_event_first():
    bg = BackgroundWindows(ranges(2, 1), windows({(1, "protons", "HET"): (T0, T0 + 3 * HOUR),
                                                  (2, "", ""): (T0 + 25 * HOUR, T0 + 27 * HOUR)}), DEFAULT)
    frame = bg.to_frame()
    assert list(frame.index) == [(2, "", ""), (1, "", ""), (1, "protons", "HET")]
    assert list(frame["Source"]) == ["event list", "default", "event list"]


def test_event_list_with_the_windows_of_particles_and_sensors():
    times = pd.DataFrame({"Start Time": [T0, T0 + 24 * HOUR], "End Time": [T0 + 30 * HOUR, T0 + 54 * HOUR]},
                         index=pd.Index([1, 2], name="Event No"))
    bg = BackgroundWindows(times, windows({(1, "protons", "HET"): (T0, T0 + 3 * HOUR)}), DEFAULT)
    rows = bg.event_list(times)
    assert list(rows.columns) == ["Particle", "Sensor", "Start Time", "BG Start", "BG End", "End Time"]
    assert list(rows.index) == [1, 1, 2]
    assert list(rows.iloc[0]) == ["", "", T0, T0, T0 + 2 * HOUR, T0 + 30 * HOUR]
    assert list(rows.iloc[1, :2]) == ["protons", "HET"]
    assert list(rows.iloc[1, 3:5]) == [T0, T0 + 3 * HOUR]
    # the times of the event only in its row
    assert pd.isna(rows.iloc[1]["Start Time"]) and pd.isna(rows.iloc[1]["End Time"])


def test_event_list_without_the_windows_of_particles_and_sensors():
    times = pd.DataFrame({"Start Time": [T0], "End Time": [T0 + 30 * HOUR], "BG End": [T0 + HOUR]},
                         index=pd.Index([1], name="Event No"))
    rows = BackgroundWindows(times, default=DEFAULT).event_list(times)
    assert list(rows.columns) == ["Start Time", "BG Start", "BG End", "End Time"]
    assert list(rows.iloc[0]) == [T0, T0, T0 + 2 * HOUR, T0 + 30 * HOUR]


# order_error and window_points

def test_order_error():
    assert order_error(T0, T0, T0 + HOUR, T0 + 2 * HOUR) is None
    assert order_error(T0, T0 + HOUR, T0 + HOUR, T0 + 2 * HOUR).startswith("the times must be in the order")


def test_window_points():
    index = pd.date_range(T0, periods=6, freq="30min")
    df = pd.DataFrame({"a": [1, 2, np.nan, 4, 5, 6], "b": [1, 2, 3, 4, 5, 6]}, index=index)
    assert window_points(df, T0, T0 + 2 * HOUR) == 4
    assert window_points(df["b"], T0, T0 + 2 * HOUR) == 5
    assert window_points(index, T0 + HOUR, T0 + 2 * HOUR) == 3
