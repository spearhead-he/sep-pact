"""Reading of the inputs: the shocks, the event list and the file of onset corrections"""
import os
from datetime import timedelta

import pandas as pd

from .background import KEY_COLUMNS, WINDOW_INDEX, BackgroundWindows, order_error, split_event_rows
from .conf import SEPPACT_parameters
from .shocks import combine_shocks, download_shocks, events_outside, read_shock_file


def load_shocks(params: SEPPACT_parameters) -> tuple[pd.DataFrame, list[str]]:
    """Returns the shocks (Shock Time, Source) of the shock list online (shock_source), of the shock list file
    (file_shocks) and the custom ones (shock_times, Source "custom"), without removed_shocks, sorted by time, and the
    warnings: a shock list online that could not be downloaded is left out"""
    sources, warnings = {}, []
    if params.shock_source:
        try:
            sources[params.shock_source] = download_shocks(params.shock_source)
        except (OSError, ValueError) as error:
            warnings.append(f"The shock list {params.shock_source} could not be downloaded ({error}); it is left out. "
                            "The data server may be unavailable; try again later.")
    if params.file_shocks:
        sources[os.path.basename(params.file_shocks)] = read_shock_file(params.file_shocks)
    if params.shock_times:
        sources["custom"] = pd.Series(pd.to_datetime(params.shock_times), dtype="datetime64[ns]")
    return combine_shocks(sources, params.removed_shocks), warnings


def shock_warnings(shocks: pd.DataFrame, events: pd.DataFrame) -> list[str]:
    """Returns the warnings about the shocks of the events: no shocks at all, or events outside the shock lists (the
    first to the last shock of the shock list online and the shock list file)"""
    if shocks.empty:
        return ["There are no shocks: the analysis of each channel group goes on to the end time of its event."]
    listed = shocks.loc[shocks["Source"] != "custom", "Shock Time"]
    if listed.empty:
        return ["There are only custom shocks: the other shocks during the events are not taken into account."]
    if outside := events_outside(events, listed):
        return [f"{count(len(outside), 'event')} ({_numbers(outside)}) {'is' if len(outside) == 1 else 'are'} not "
                f"within the shock lists ({listed.min():%Y-%m-%d} to {listed.max():%Y-%m-%d}): the shocks during "
                f"{'it' if len(outside) == 1 else 'them'} may be missing."]
    return []


def count(n: int, noun: str) -> str:
    """Returns the number with the noun, e.g. 1 event, 3 events"""
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _numbers(numbers: list, first: int = 10) -> str:
    """Returns the numbers, the first ones only if there are more"""
    text = ", ".join(map(str, numbers[:first]))
    return text + (f" and {len(numbers) - first} more" if len(numbers) > first else "")


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
    """Returns the layout of the event list with these columns (after Event No, without Particle and Sensor), or raises
    an error that lists the accepted ones"""
    for layout, layout_columns in EVENT_LIST_LAYOUTS.items():
        if set(columns) == set(layout_columns):
            return layout
    accepted = "\n".join(f"    Event No, {', '.join(layout_columns)}" for layout_columns in EVENT_LIST_LAYOUTS.values())
    accepted += "\nwith optionally Particle and Sensor, for the rows of the background windows of particles and sensors"
    hint = ""
    if "Onset Time" in columns:
        hint = ("\nThe Onset Time of former event lists is the Reference Time; an event list with Onset Time, BG Start "
                "and BG End becomes Start Time (= BG Start), BG Start, BG End and End Time.")
    raise ValueError(f"The event list {path} has the columns {', '.join(columns)}. Accepted columns:\n{accepted}{hint}")


def read_event_list(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns the times of the events of the CSV event list (indexed by Event No, with the columns of its layout), and
    the background windows of its particles and sensors (see background.split_event_rows()); prints a message for each
    time given more than once in the rows of an event, of which the last one is used"""
    if not path.lower().endswith(".csv"):
        raise ValueError(f"The event list {path} is not a CSV file. Event lists in Excel or other formats are not "
                         f"accepted; save it as CSV.")
    df = pd.read_csv(path, header=0, skipinitialspace=True, skip_blank_lines=False, dtype={"Particle": str, "Sensor": str})
    df.columns = df.columns.str.strip()
    df = df.rename(columns={df.columns[0]: "Event No"}).set_axis(range(2, len(df) + 2)).dropna(how="all")
    event_list_layout(path, [column for column in df.columns[1:] if column not in KEY_COLUMNS])
    if len(no_number := df[df["Event No"].isna()]):
        raise ValueError(f"Line {no_number.index[0]} of the event list {path} has no Event No.")
    df["Event No"] = df["Event No"].astype(int)
    for column in df.columns[1:]:
        if column in KEY_COLUMNS:
            continue
        # parsed before the rows of an event are compared
        df[column] = pd.to_datetime(df[column], format="ISO8601").astype("datetime64[ns]")
    for column in KEY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df_event_times, df_windows, messages = split_event_rows(df)
    for message in messages:
        print(f"The event list {path}: {message}")
    df_event_times = df_event_times.astype("datetime64[ns]")
    # the events without any time (e.g. a row with only its number)
    return df_event_times.dropna(how="all"), df_windows


def _date_range_events(date_ranges: list) -> pd.DataFrame:
    """Returns the times of the events of date_ranges [(start, end)], numbered from 1"""
    if not date_ranges:
        raise ValueError("There are no events: give an event list (file_events) or the date ranges of the events.")
    return pd.DataFrame({"Start Time": [start for start, _ in date_ranges], "End Time": [end for _, end in date_ranges]},
                        index=pd.Index(range(1, len(date_ranges) + 1), name="Event No")).astype("datetime64[ns]")


def window_order_error(row: pd.Series) -> str | None:
    """Returns why the times of an event are not in the order Start Time <= BG Start < BG End < End Time, or None"""
    return order_error(row["Start Time"], row["BG Start"], row["BG End"], row["End Time"])


def _check_event_windows(events: pd.DataFrame, source: str) -> None:
    """Checks that the times of each event are given, and that its background window is inside its data range"""
    for event_no, row in events.iterrows():
        missing = [column for column in ("Start Time", "End Time") if pd.isna(row[column])]
        if missing:
            raise ValueError(f"Event {event_no} of {source} has no {' and no '.join(missing)}.")
        if error := window_order_error(row):
            raise ValueError(f"Event {event_no} of {source}: {error}")


def complete_events(df_event_times: pd.DataFrame, params: SEPPACT_parameters, source: str) -> pd.DataFrame:
    """Returns the events with all their times, the default ones where they are missing, their period of data
    (Plot Start, Plot End), and where their background window and end time come from (BG Window Source and End Time
    Source: "event list" or "default")

    The data of events with a Reference Time start start_before_reference before it and end end_after_reference after
    it. Events without a background window get the default one, bg_start_after_start to bg_end_after_start after
    the Start Time; events with only a BG End start their background at the Start Time.
    """
    events = df_event_times.reindex(columns=EVENT_COLUMNS).astype("datetime64[ns]")
    references = events["Reference Time"]
    end_time_source = pd.Series("event list", index=events.index).where(events["End Time"].notna(), "default")
    events["Start Time"] = events["Start Time"].fillna(references - params.start_before_reference)
    events["End Time"] = events["End Time"].fillna(references + params.end_after_reference)
    without_bg = events["BG Start"].isna() & events["BG End"].isna()
    bg_window = pd.Series("event list", index=events.index).where(~without_bg, "default")
    events.loc[without_bg, "BG Start"] = events.loc[without_bg, "Start Time"] + params.bg_start_after_start
    events.loc[without_bg, "BG End"] = events.loc[without_bg, "Start Time"] + params.bg_end_after_start
    events["BG Start"] = events["BG Start"].fillna(events["Start Time"])
    _check_event_windows(events, source)

    # events shorter than min_plot_window are extended equally on both sides
    buffer_time = ((params.min_plot_window - (events["End Time"] - events["Start Time"])) / 2).clip(lower=timedelta(0))
    events["Plot Start"] = events["Start Time"] - buffer_time
    events["Plot End"] = events["End Time"] + buffer_time
    events["BG Window Source"] = bg_window
    events["End Time Source"] = end_time_source
    return events


def read_events(path: str, params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the events of the CSV event list, with all their times and their period of data (see complete_events())

    The first column is the event number, then the columns of one of EVENT_LIST_LAYOUTS: Reference Time, or Start
    Time and End Time with optionally BG End or BG Start and BG End; optionally Particle and Sensor, for the rows of
    the background windows of particles and sensors.
    """
    return complete_events(read_event_list(path)[0], params, f"the event list {path}")


def make_bg_windows(events: pd.DataFrame, own_windows: pd.DataFrame, params: SEPPACT_parameters) -> BackgroundWindows:
    """Returns the background windows of the events (of complete_events()), with the windows of their particles and
    sensors (of read_event_list())"""
    listed = events[events["BG Window Source"] == "event list"]
    event_windows = listed[["BG Start", "BG End"]].set_axis(
        pd.MultiIndex.from_tuples([(event_no, "", "") for event_no in listed.index], names=WINDOW_INDEX))
    windows = pd.concat([event_windows, own_windows]) if len(own_windows) else event_windows
    bg_windows = BackgroundWindows(events[["Start Time", "End Time"]], windows,
                                   (params.bg_start_after_start, params.bg_end_after_start))
    bg_windows.check_names({particle: list(params.SENSORS) for particle in params.PARTICLES})
    return bg_windows


def load_events(params: SEPPACT_parameters) -> tuple[pd.DataFrame, BackgroundWindows]:
    """Returns the events of the event list file_events, or of date_ranges if file_events is empty (see
    complete_events()), and their background windows, with those of their particles and sensors"""
    if not params.file_events:
        events = complete_events(_date_range_events(params.date_ranges), params, "the date ranges")
        return events, make_bg_windows(events, pd.DataFrame(), params)
    path = params.file_events
    event_times, own_windows = read_event_list(path)
    events = complete_events(event_times, params, f"the event list {path}")
    try:
        return events, make_bg_windows(events, own_windows, params)
    except ValueError as error:
        raise ValueError(f"The event list {path}: {error}") from None


def make_events(params: SEPPACT_parameters) -> pd.DataFrame:
    """Returns the events of the event list file_events, or of date_ranges if file_events is empty"""
    return load_events(params)[0]


# the columns of the file of onset corrections
CORRECTION_COLUMNS = ["Event No", "Particle", "Sensor", "Energy Label", "Onset Resolution", "Onset Viewing", "Onset Time"]


def read_corrections(path: str) -> tuple[dict, dict]:
    """Returns the onset corrections of the file written by SEPPACT.save_corrections(): {(event number, particle,
    sensor, group label): (resolution, viewing), or None for no onset}, and {same key: onset time} of the corrections
    with an onset

    The file has the columns of CORRECTION_COLUMNS, with the resolution in minutes; a row without a resolution and
    viewing means no onset.
    """
    df = pd.read_csv(path, skipinitialspace=True, dtype={"Particle": str, "Sensor": str, "Energy Label": str,
                                                         "Onset Viewing": str})
    if missing := [column for column in CORRECTION_COLUMNS if column not in df.columns]:
        raise ValueError(f"The onset corrections {path} have no column {', '.join(missing)}. The columns are: "
                         f"{', '.join(CORRECTION_COLUMNS)}.")
    corrections, onset_times = {}, {}
    for i, row in df.iterrows():
        key = (int(row["Event No"]), row["Particle"], row["Sensor"], row["Energy Label"])
        if pd.isna(row["Onset Resolution"]) and pd.isna(row["Onset Viewing"]):
            corrections[key] = None
        elif pd.isna(row["Onset Resolution"]) or pd.isna(row["Onset Viewing"]):
            raise ValueError(f"Row {i + 2} of the onset corrections {path} has an onset resolution or viewing without "
                             "the other; give both, or neither for no onset.")
        else:
            corrections[key] = (pd.Timedelta(minutes=float(row["Onset Resolution"])), row["Onset Viewing"])
            if not pd.isna(row["Onset Time"]):
                onset_times[key] = pd.Timestamp(row["Onset Time"])
    return corrections, onset_times
