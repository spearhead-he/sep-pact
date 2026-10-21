"""Background windows of the events, per event, particle, or particle and sensor

This module uses only pandas and nothing else of the package, so that the SPEARHEAD tools can share it.

An event list can have, next to the row of an event, rows with a Particle, or a Particle and a Sensor: their BG Start
and BG End are the background window of that particle (and sensor) in the event, which replaces the window of the
event for its series. The times of the event (e.g. Start Time and End Time) can be in any of its rows; each time is
the last one given in the rows of the event, and so is each background time of the same particle and sensor.
"""
from collections import namedtuple
from datetime import timedelta

import pandas as pd

# the columns of the rows of particles and sensors in an event list
KEY_COLUMNS = ["Particle", "Sensor"]
WINDOW_COLUMNS = ["BG Start", "BG End"]
WINDOW_INDEX = ["Event No", *KEY_COLUMNS]

# a window of a series: the one of its particle and sensor, of its particle, or of the event ("" for no particle or
# sensor), and where it comes from: "event list", "default" or "set"
BGWindow = namedtuple("BGWindow", ["start", "end", "source", "particle", "sensor"])


def key_label(event_no, particle: str = "", sensor: str = "") -> str:
    """Returns "Event 2", "Event 2, protons" or "Event 2, protons HET\""""
    return f"Event {event_no}" + (f", {particle}" if particle else "") + (f" {sensor}" if sensor else "")


def order_error(start_time, bg_start, bg_end, end_time) -> str | None:
    """Returns why the times are not in the order Start Time <= BG Start < BG End < End Time, or None"""
    if start_time <= bg_start < bg_end < end_time:
        return None
    return (f"the times must be in the order Start Time <= BG Start < BG End < End Time, not {start_time}, {bg_start}, "
            f"{bg_end}, {end_time}.")


def _last_values(rows: pd.DataFrame, label: str) -> tuple[dict, list[str]]:
    """Returns {column: its last non-empty value in the rows (indexed by their line in the file), or None}, and a
    message for each column with different values"""
    values, messages = {}, []
    for column in rows.columns:
        given = rows[column].dropna()
        values[column] = given.iloc[-1] if len(given) else None
        if given.nunique() > 1:
            lines = ", ".join(f"{value} in line {line}" for line, value in given.items())
            messages.append(f"{label}: {column} is given {len(given)} times ({lines}); the last one is used.")
    return values, messages


def split_event_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Splits the rows of an event list into the times of the events and the background windows

    df has a column Event No, the columns Particle and Sensor (empty for the rows of the events) and the time columns,
    and is indexed by the line of each row in the file. Returns the times of each event (indexed by Event No, in the
    order of the list, with the columns of df but Particle, Sensor, BG Start and BG End), its window and the windows of
    its particles and sensors (indexed by Event No, Particle and Sensor, "" for none; BG Start may be empty), and the
    messages about the times given more than once, of which the last one is used.
    """
    df = df.copy()
    df[KEY_COLUMNS] = df[KEY_COLUMNS].fillna("").astype(str).apply(lambda column: column.str.strip())
    if len(sensor_only := df[(df["Particle"] == "") & (df["Sensor"] != "")]):
        raise ValueError(f"Line {sensor_only.index[0]} of the event list has a Sensor without a Particle; give the "
                         "Particle too, or only the Particle for all its sensors.")
    window_columns = [column for column in WINDOW_COLUMNS if column in df.columns]
    time_columns = [column for column in df.columns if column not in ["Event No", *KEY_COLUMNS, *WINDOW_COLUMNS]]
    times, windows, messages = {}, {}, []
    for event_no, rows in df.groupby("Event No", sort=False):
        is_event_row = rows["Particle"] == ""
        values, event_messages = _last_values(rows.loc[:, time_columns], key_label(event_no))
        window, window_messages = _last_values(rows.loc[is_event_row, window_columns], key_label(event_no))
        times[event_no] = {**values, **window}
        messages += event_messages + window_messages
        for (particle, sensor), key_rows in rows[~is_event_row].groupby(KEY_COLUMNS, sort=False):
            label = key_label(event_no, particle, sensor)
            window, window_messages = _last_values(key_rows[window_columns], label)
            if window.get("BG End") is None:
                raise ValueError(f"{label} of the event list has no BG End: the rows of a particle or sensor give its "
                                 "background window (BG End, and BG Start or else the Start Time of the event).")
            windows[(event_no, particle, sensor)] = window
            messages += window_messages
    df_times = pd.DataFrame.from_dict(times, orient="index", columns=time_columns + window_columns)
    df_times.index.name = "Event No"
    df_windows = pd.DataFrame.from_dict(windows, orient="index", columns=WINDOW_COLUMNS).astype("datetime64[ns]")
    df_windows.index = pd.MultiIndex.from_tuples(list(windows), names=WINDOW_INDEX)
    return df_times, df_windows, messages


class BackgroundWindows:
    """The background windows of the events

    Each event has a window: the one of the event list, or the default one, default[0] to default[1] after its Start
    Time. A particle, or a particle and sensor, can have its own window in an event, which replaces the one of the
    event for its series. window() returns the window of a series: the one of its particle and sensor, else of its
    particle, else of the event. Every window is in the data range of its event: Start Time <= BG Start < BG End < End
    Time.
    """

    def __init__(self,
                 ranges: pd.DataFrame,
                 windows: pd.DataFrame | None = None,
                 default: tuple[timedelta, timedelta] = (timedelta(0), timedelta(hours=1))):
        """ranges: the Start Time and End Time of each event, indexed by Event No. windows: the windows of the event
        list, indexed by Event No, Particle and Sensor ("" for none), with the columns BG Start (empty for the Start
        Time) and BG End; an event without a window gets the default one."""
        self.ranges = ranges[["Start Time", "End Time"]].astype("datetime64[ns]").copy()
        self.default = default
        if windows is None:
            windows = pd.DataFrame(columns=WINDOW_COLUMNS, index=pd.MultiIndex.from_tuples([], names=WINDOW_INDEX))
        windows = windows[WINDOW_COLUMNS].astype("datetime64[ns]")
        if unknown := sorted(set(windows.index.get_level_values("Event No")) - set(self.ranges.index)):
            raise ValueError(f"The background windows of the events {', '.join(map(str, unknown))} are of no event.")
        # the windows as given, for reset()
        self._input = windows[windows["BG End"].notna()].copy()
        self._input["BG Start"] = self._input["BG Start"].fillna(
            self.ranges["Start Time"].reindex(self._input.index.get_level_values("Event No")).set_axis(self._input.index))
        self._input["Source"] = "event list"
        table = self._input.copy()
        without = [(event_no, "", "") for event_no in self.ranges.index if (event_no, "", "") not in table.index]
        table = pd.concat([table, self._default_windows(without)]) if without else table
        self._table = table.astype({"BG Start": "datetime64[ns]", "BG End": "datetime64[ns]", "Source": object})
        for key in self._table.index:
            self._check(key, *self._table.loc[key, WINDOW_COLUMNS])

    def _default_windows(self, keys: list) -> pd.DataFrame:
        """Returns the default windows of these keys of events"""
        index = pd.MultiIndex.from_tuples(keys, names=WINDOW_INDEX)
        starts = self.ranges.loc[[key[0] for key in keys], "Start Time"].set_axis(index)
        return pd.DataFrame({"BG Start": starts + pd.Timedelta(self.default[0]),
                             "BG End": starts + pd.Timedelta(self.default[1]), "Source": "default"}, index=index)

    def _check(self, key: tuple, bg_start, bg_end, start_time=None, end_time=None) -> None:
        """Raises an error if the window of the key is not in the data range of its event"""
        start_time = self.ranges.loc[key[0], "Start Time"] if start_time is None else start_time
        end_time = self.ranges.loc[key[0], "End Time"] if end_time is None else end_time
        if error := order_error(start_time, bg_start, bg_end, end_time):
            raise ValueError(f"The background window of {key_label(*key)}: {error}")

    @staticmethod
    def _key(event_no, particle: str, sensor: str) -> tuple:
        if sensor and not particle:
            raise ValueError(f"A background window of a sensor needs its particle (event {event_no}, sensor {sensor}).")
        return (event_no, particle, sensor)

    def window(self, event_no, particle: str = "", sensor: str = "") -> BGWindow:
        """Returns the window of a series of the event: the one of its particle and sensor, else of its particle, else
        of the event; without a particle, the window of the event"""
        for key in [(event_no, particle, sensor), (event_no, particle, ""), (event_no, "", "")]:
            if key in self._table.index:
                row = self._table.loc[key]
                return BGWindow(row["BG Start"], row["BG End"], row["Source"], key[1], key[2])
        raise KeyError(f"There is no event {event_no}.")

    def own_windows(self, event_no=None) -> list[tuple]:
        """Returns the (event number, particle, sensor) that have their own window, of all the events or of one"""
        return [key for key in self._table.index if key[1] and (event_no is None or key[0] == event_no)]

    def set(self, event_no, start, end, particle: str = "", sensor: str = "") -> None:
        """Sets the window of the event, or of its particle (and sensor) (source "set")"""
        key = self._key(event_no, particle, sensor)
        if event_no not in self.ranges.index:
            raise KeyError(f"There is no event {event_no}.")
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        self._check(key, start, end)
        self._table.loc[key, ["BG Start", "BG End", "Source"]] = [start, end, "set"]

    def reset(self, event_no, particle: str = "", sensor: str = "") -> None:
        """Sets the window of the event back to the one of the event list or the default one; the window of a particle
        (and sensor) back to the one of the event list, or removes it"""
        key = self._key(event_no, particle, sensor)
        if key in self._input.index:
            self._table.loc[key] = self._input.loc[key]
        elif particle:
            self._table = self._table.drop(key, errors="ignore")
        else:
            self._table.loc[key] = self._default_windows([key]).loc[key]

    def set_default(self, start_after: timedelta, end_after: timedelta) -> None:
        """Sets the default window, start_after to end_after after the Start Time, of the events without another one"""
        keys = list(self._table.index[self._table["Source"] == "default"])
        defaults = BackgroundWindows(self.ranges, default=(start_after, end_after))._default_windows(keys)
        for key in keys:
            self._check(key, *defaults.loc[key, WINDOW_COLUMNS])
        self.default = (start_after, end_after)
        self._table.loc[keys] = defaults

    def set_end_time(self, event_no, end) -> None:
        """Sets the End Time of the event, after all its windows"""
        end = pd.Timestamp(end)
        for key in self._table.index[self._table.index.get_level_values("Event No") == event_no]:
            self._check(key, *self._table.loc[key, WINDOW_COLUMNS], end_time=end)
        self.ranges.loc[event_no, "End Time"] = end

    def check_names(self, names: dict) -> None:
        """Raises an error for the windows of particles and sensors not in names {particle: [sensors]}, and writes the
        others as in names (the names are compared without case)"""
        canonical = {particle.lower(): (particle, {sensor.lower(): sensor for sensor in sensors})
                     for particle, sensors in names.items()}
        renamed = {}
        for key in self.own_windows():
            particle, sensors = canonical.get(key[1].lower(), (None, {}))
            sensor = sensors.get(key[2].lower()) if key[2] else ""
            if particle is None or sensor is None:
                accepted = "; ".join(f"{particle}: {', '.join(sensors)}" for particle, sensors in names.items())
                raise ValueError(f"{key_label(*key)} of the event list: there is no {key[1]} {key[2]}".rstrip()
                                 + f". The particles and their sensors are: {accepted}.")
            renamed[key] = (key[0], particle, sensor)
        for table in (self._table, self._input):
            table.index = pd.MultiIndex.from_tuples([renamed.get(key, key) for key in table.index], names=WINDOW_INDEX)
        if self._table.index.has_duplicates:
            duplicate = self._table.index[self._table.index.duplicated()][0]
            raise ValueError(f"{key_label(*duplicate)} has more than one background window in the event list.")

    def to_frame(self) -> pd.DataFrame:
        """Returns all the windows (BG Start, BG End, Source), indexed by Event No, Particle and Sensor, the window of
        each event first"""
        order = {event_no: i for i, event_no in enumerate(self.ranges.index)}
        return self._table.sort_index(key=lambda level: level.map(order) if level.name == "Event No" else level).copy()

    def event_list(self, times: pd.DataFrame) -> pd.DataFrame:
        """Returns the rows of an event list with the windows: the row of each event, with its times (the columns of
        times, indexed by Event No) and its window, then the rows of its particles and sensors with their windows; the
        columns Particle and Sensor only if there are such rows"""
        windows = self.to_frame()
        rows = windows.join(times.drop(columns=WINDOW_COLUMNS, errors="ignore"), on="Event No").drop(columns="Source")
        own = windows.index.get_level_values("Particle") != ""
        rows.loc[own, [column for column in rows.columns if column not in WINDOW_COLUMNS]] = pd.NaT
        columns = [column for column in times.columns if column not in WINDOW_COLUMNS]
        columns = columns[:1] + WINDOW_COLUMNS + columns[1:]
        rows = rows.reset_index(level=KEY_COLUMNS)[KEY_COLUMNS + columns]
        return rows if own.any() else rows.drop(columns=KEY_COLUMNS)


def window_points(data, start, end) -> int:
    """Returns the points with data in the window: the fewest non-empty values of a column of data (a DataFrame or
    Series indexed by time), or the times of a DatetimeIndex"""
    if isinstance(data, pd.DatetimeIndex):
        return int(((data >= start) & (data <= end)).sum())
    counts = data.loc[start:end].notna().sum()
    return int(counts.min()) if isinstance(counts, pd.Series) else int(counts)
