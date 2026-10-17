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


# the times of the event list; only Onset Time is required
EVENT_TIME_COLUMNS = ["Onset Time", "BG Start", "BG End", "End Time"]


def _read_event_times(path: str) -> pd.DataFrame:
    """Returns the times of the CSV event list, indexed by Event No, with the missing optional columns empty"""
    if not path.lower().endswith(".csv"):
        raise ValueError(f"The event list {path} is not a CSV file. Event lists in Excel or other formats are not "
                         f"accepted; save it as CSV, with the columns Event No, {', '.join(EVENT_TIME_COLUMNS)}.")
    df_event_times = pd.read_csv(path, header=0, index_col=0, skipinitialspace=True)
    df_event_times.columns = df_event_times.columns.str.strip()
    df_event_times.index.name = "Event No"
    df_event_times = df_event_times.dropna(how="all")
    if "Onset Time" not in df_event_times.columns:
        raise ValueError(f"The event list {path} has no column \"Onset Time\". "
                         f"Its columns are: {', '.join(df_event_times.columns)}.")
    for column in EVENT_TIME_COLUMNS:
        if column not in df_event_times.columns:
            df_event_times[column] = pd.NaT
        df_event_times[column] = pd.to_datetime(df_event_times[column], format="ISO8601").astype("datetime64[ns]")
    return df_event_times


def read_events(path: str, params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the event list, with the missing windows filled in and the period of data (Plot Start, Plot End) of each event

    The event list is a CSV file. The first column is the event number, and Onset Time is required. BG Start, BG End
    and End Time are optional; where they are missing or empty, they are set from Onset Time with the event window
    parameters.
    """
    df_event_times = _read_event_times(path)
    onsets = df_event_times["Onset Time"]
    df_event_times["BG Start"] = df_event_times["BG Start"].fillna(onsets - params.bg_start_before_onset)
    df_event_times["BG End"] = df_event_times["BG End"].fillna(onsets - params.bg_end_before_onset)
    df_event_times["End Time"] = df_event_times["End Time"].fillna(onsets + params.end_after_onset)

    # events shorter than min_plot_window are extended equally on both sides
    buffer_time = ((params.min_plot_window - (df_event_times["End Time"] - df_event_times["BG Start"])) / 2) \
        .clip(lower=timedelta(0))
    df_event_times["Plot Start"] = df_event_times["BG Start"] - buffer_time
    df_event_times["Plot End"] = df_event_times["End Time"] + buffer_time
    return df_event_times
