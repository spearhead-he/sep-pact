"""Shocks: the shock lists online (SODA, IRFU), the shock list files and the custom shock times

This module uses only pandas and the standard library, so that the SPEARHEAD tools can share it.
"""
import json
import os
import re
import urllib.request

import pandas as pd

# the shock lists online, with the Solar Orbiter shocks: {name: description}
SHOCK_SOURCES = {
    "SODA": "SODA, the automated shock list of the Parker Solar Probe science site (https://parker.gsfc.nasa.gov/shocks.html)",
    "IRFU": "the Solar Orbiter IRFU shock list by A. P. Dimmock, its latest version on Zenodo "
            "(https://doi.org/10.5281/zenodo.11091062)",
}
SODA_URL = "https://parker.gsfc.nasa.gov/static_data/soda2/soda.json"
# Solar Orbiter in SODA
SODA_SPACECRAFT = "SLO"
IRFU_RECORD_URL = "https://zenodo.org/api/records/14001054/versions/latest"
# seconds to wait for a server
TIMEOUT = 30
# the columns of the table of the shocks
SHOCK_COLUMNS = ["Shock Time", "Source"]
SHOCK_FILE_FORMATS = ("an ipshocks list (.dat, with the year, month, day, hour, minute and second separated by ';')",
                      "the IRFU list (.txt)", "a CSV file with the column Shock Time")


def _get(url: str) -> bytes:
    """Returns the content of the URL"""
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        return response.read()


def _times(values) -> pd.Series:
    return pd.Series(pd.to_datetime(list(values)), dtype="datetime64[ns]").sort_values(ignore_index=True)


def parse_soda(text: str, spacecraft: str = SODA_SPACECRAFT) -> pd.Series:
    """Returns the times of the shocks of a spacecraft in the SODA list (JSON)"""
    return _times(pd.Timestamp(row["Time"].replace("/", "-")) for row in json.loads(text) if row["SC"] == spacecraft)


IRFU_ROW = re.compile(r"\s*\d+\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)")


def parse_irfu(text: str) -> pd.Series:
    """Returns the times of the shocks of the IRFU list (rows of number, time of the ramp, ...; # for comments)"""
    return _times(match.group(1) for line in text.splitlines() if (match := IRFU_ROW.match(line)))


IPSHOCKS_ROW = re.compile(r"\s*(\d{4})\s*;\s*(\d+)\s*;\s*(\d+)\s*;\s*(\d+)\s*;\s*(\d+)\s*;\s*(\d+)\s*;")


def parse_ipshocks(text: str) -> pd.Series:
    """Returns the times of the shocks of an ipshocks list (the year, month, day, hour, minute and second, separated
    by ';', then the other columns; # for comments)"""
    return _times(pd.Timestamp(*map(int, match.groups())) for line in text.splitlines()
                  if not line.startswith("#") and (match := IPSHOCKS_ROW.match(line)))


def download_shocks(source: str) -> pd.Series:
    """Returns the times of the Solar Orbiter shocks of a shock list online (one of SHOCK_SOURCES)"""
    if source == "SODA":
        return parse_soda(_get(SODA_URL).decode())
    if source == "IRFU":
        record = json.loads(_get(IRFU_RECORD_URL))
        file = next(file for file in record["files"] if file["key"].endswith(".txt"))
        return parse_irfu(_get(file["links"]["self"]).decode())
    raise ValueError(f"There is no shock list online {source!r}; the lists are: {', '.join(SHOCK_SOURCES)}.")


def read_shock_file(path: str) -> pd.Series:
    """Returns the times of the shocks of a shock list file, in one of SHOCK_FILE_FORMATS"""
    if not os.path.isfile(path):
        raise ValueError(f"The shock list {path} is not found.")
    with open(path, encoding="utf-8") as file:
        text = file.read()
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if lines and "Shock Time" in lines[0]:
        column = pd.read_csv(path, comment="#", skipinitialspace=True)["Shock Time"].dropna()
        return _times(pd.to_datetime(column, format="ISO8601"))
    for parse in (parse_ipshocks, parse_irfu):
        if len(times := parse(text)):
            return times
    raise ValueError(f"The shock list {path} has no shocks in one of the formats: {'; '.join(SHOCK_FILE_FORMATS)}.")


def combine_shocks(sources: dict, removed: list | None = None) -> pd.DataFrame:
    """Returns the shocks of the sources {name: times} (Shock Time, Source), sorted by time, without the removed times;
    a shock in more than one source is in the table once per source"""
    frames = [pd.DataFrame({"Shock Time": times.to_numpy(), "Source": name}) for name, times in sources.items()]
    shocks = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SHOCK_COLUMNS)
    shocks["Shock Time"] = shocks["Shock Time"].astype("datetime64[ns]")
    shocks = shocks[~shocks["Shock Time"].isin(pd.to_datetime(list(removed or [])))]
    return shocks.sort_values("Shock Time", kind="stable", ignore_index=True)


def events_outside(events: pd.DataFrame, times: pd.Series) -> list:
    """Returns the numbers of the events whose data range (Start Time to End Time) is not within the first to the last
    of the times, all the events without times"""
    if times.empty:
        return list(events.index)
    inside = (events["Start Time"] >= times.min()) & (events["End Time"] <= times.max())
    return list(events.index[~inside])
