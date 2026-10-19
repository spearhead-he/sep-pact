"""Reading of the input files: the shock list and the event list"""
from datetime import datetime, timedelta

import pandas as pd

from .conf import SEPPACT_parameters


def read_shocks(path: str) -> pd.Series:
    """Returns the times of the shocks of an ipshocks.helsinki.fi list (lines starting with # are comments)"""
    shocktimes = pd.read_csv(path,
                             sep=";",
                             header=None,
                             comment="#",
                             usecols=[0, 1, 2, 3, 4, 5])
    shocktimes["Datetime"] = [datetime(row[0], row[1], row[2], row[3], row[4], row[5]) for _, row in shocktimes.iterrows()]
    for i in range(6):
        del shocktimes[i]
    return pd.Series(shocktimes["Datetime"])


# the columns of the event list after Event No, in each of its layouts (as in the VDA tool)
EVENT_LIST_LAYOUTS = {
    "reference times": ("Reference Time",),
    "datetime ranges": ("Start Time", "End Time"),
    # the background starts at the Start Time
    "datetime ranges with the background end": ("Start Time", "BG End", "End Time"),
    "datetime ranges with the background window": ("Start Time", "BG Start", "BG End", "End Time"),
}
# the columns of the events table, before the period of data (Plot Start, Plot End)
EVENT_COLUMNS = ["Start Time", "BG Start", "BG End", "End Time", "Reference Time"]


def event_list_layout(path: str, columns) -> str:
    """Returns the layout of the event list with these columns (after Event No), or raises an error that lists the
    accepted ones"""
    for layout, layout_columns in EVENT_LIST_LAYOUTS.items():
        if set(columns) == set(layout_columns):
            return layout
    accepted = "\n".join(f"    Event No, {', '.join(layout_columns)}" for layout_columns in EVENT_LIST_LAYOUTS.values())
    hint = ""
    if "Onset Time" in columns:
        hint = ("\nThe Onset Time of former event lists is the Reference Time; an event list with Onset Time, BG Start "
                "and BG End becomes Start Time (= BG Start), BG Start, BG End and End Time.")
    raise ValueError(f"The event list {path} has the columns {', '.join(columns)}. Accepted columns:\n{accepted}{hint}")


def _read_event_times(path: str) -> pd.DataFrame:
    """Returns the times of the CSV event list, indexed by Event No, with the columns of its layout"""
    if not path.lower().endswith(".csv"):
        raise ValueError(f"The event list {path} is not a CSV file. Event lists in Excel or other formats are not "
                         f"accepted; save it as CSV.")
    df_event_times = pd.read_csv(path, header=0, index_col=0, skipinitialspace=True)
    df_event_times.columns = df_event_times.columns.str.strip()
    df_event_times.index.name = "Event No"
    df_event_times = df_event_times.dropna(how="all")
    event_list_layout(path, list(df_event_times.columns))
    for column in df_event_times.columns:
        df_event_times[column] = pd.to_datetime(df_event_times[column], format="ISO8601").astype("datetime64[ns]")
    return df_event_times


def _date_range_events(date_ranges: list) -> pd.DataFrame:
    """Returns the times of the events of date_ranges [(start, end)], numbered from 1"""
    if not date_ranges:
        raise ValueError("There are no events: give an event list (file_events) or the date ranges of the events.")
    return pd.DataFrame({"Start Time": [start for start, _ in date_ranges], "End Time": [end for _, end in date_ranges]},
                        index=pd.Index(range(1, len(date_ranges) + 1), name="Event No")).astype("datetime64[ns]")


def _check_event_windows(events: pd.DataFrame, source: str) -> None:
    """Checks that the times of each event are given, and that its background window is inside its data range"""
    for event_no, row in events.iterrows():
        missing = [column for column in ("Start Time", "End Time") if pd.isna(row[column])]
        if missing:
            raise ValueError(f"Event {event_no} of {source} has no {' and no '.join(missing)}.")
        if not row["Start Time"] <= row["BG Start"] < row["BG End"] < row["End Time"]:
            raise ValueError(f"Event {event_no} of {source}: the times must be in the order Start Time <= BG Start < "
                             f"BG End < End Time, not {row['Start Time']}, {row['BG Start']}, {row['BG End']}, "
                             f"{row['End Time']}.")


def complete_events(df_event_times: pd.DataFrame, params: SEPPACT_parameters, source: str) -> pd.DataFrame:
    """Returns the events with all their times, the default ones where they are missing, and their period of data
    (Plot Start, Plot End)

    The data of events with a Reference Time start start_before_reference before it and end end_after_reference after
    it. Events without a background window get the default one, bg_start_after_start to bg_end_after_start after
    the Start Time; events with only a BG End start their background at the Start Time.
    """
    events = df_event_times.reindex(columns=EVENT_COLUMNS).astype("datetime64[ns]")
    references = events["Reference Time"]
    events["Start Time"] = events["Start Time"].fillna(references - params.start_before_reference)
    events["End Time"] = events["End Time"].fillna(references + params.end_after_reference)
    without_bg = events["BG Start"].isna() & events["BG End"].isna()
    events.loc[without_bg, "BG Start"] = events.loc[without_bg, "Start Time"] + params.bg_start_after_start
    events.loc[without_bg, "BG End"] = events.loc[without_bg, "Start Time"] + params.bg_end_after_start
    events["BG Start"] = events["BG Start"].fillna(events["Start Time"])
    _check_event_windows(events, source)

    # events shorter than min_plot_window are extended equally on both sides
    buffer_time = ((params.min_plot_window - (events["End Time"] - events["Start Time"])) / 2).clip(lower=timedelta(0))
    events["Plot Start"] = events["Start Time"] - buffer_time
    events["Plot End"] = events["End Time"] + buffer_time
    return events


def read_events(path: str, params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the events of the CSV event list, with all their times and their period of data (see complete_events())

    The first column is the event number, then the columns of one of EVENT_LIST_LAYOUTS: Reference Time, or Start
    Time and End Time with optionally BG End or BG Start and BG End.
    """
    return complete_events(_read_event_times(path), params, f"the event list {path}")


def make_events(params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the events of the event list file_events, or of date_ranges if file_events is empty"""
    if params.file_events:
        return read_events(params.file_events, params)
    return complete_events(_date_range_events(params.date_ranges), params, "the date ranges")
