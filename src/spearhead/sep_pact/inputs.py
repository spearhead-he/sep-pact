"""Reading of the input files: the shock list and the event list"""
from datetime import datetime

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


def read_events(path: str, params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the event list, with the missing windows filled in and the period of data (Plot Start, Plot End) of each event

    The first column is the event number, and Onset Time is required. BG Start, BG End and End Time are optional;
    where they are missing or empty, they are set from Onset Time with the event window parameters.
    """
    df_event_times = pd.read_excel(path,
                                   header=0,
                                   index_col=0,
                                   dtype={
                                       "Onset Time": "datetime64[ns]",
                                       "BG Start": "datetime64[ns]",
                                       "BG End": "datetime64[ns]",
                                       "End Time": "datetime64[ns]"
                                   })
    df_event_times = df_event_times.dropna(how="all")
    if "Onset Time" not in df_event_times.columns:
        raise ValueError(f"The event list {path} has no column \"Onset Time\". Its columns are: {', '.join(df_event_times.columns)}.")
    for column in ["BG Start", "BG End", "End Time"]:
        if column not in df_event_times.columns:
            df_event_times[column] = pd.NaT
    for i, row in df_event_times.iterrows():
        if pd.isna(row["BG Start"]):
            df_event_times.at[i, "BG Start"] = row["Onset Time"] - params.bg_start_before_onset
        if pd.isna(row["BG End"]):
            df_event_times.at[i, "BG End"] = row["Onset Time"] - params.bg_end_before_onset
        if pd.isna(row["End Time"]):
            df_event_times.at[i, "End Time"] = row["Onset Time"] + params.end_after_onset

    plot_starts = []
    plot_ends = []
    for event_no, row in df_event_times.iterrows():
        if (dt := row["End Time"] - row["BG Start"]) < params.min_plot_window:
            buffer_time = (params.min_plot_window - dt) / 2
            plot_starts.append(row["BG Start"] - buffer_time)
            plot_ends.append(row["End Time"] + buffer_time)
        else:
            plot_starts.append(row["BG Start"])
            plot_ends.append(row["End Time"])
    df_event_times["Plot Start"] = plot_starts
    df_event_times["Plot End"] = plot_ends
    return df_event_times
