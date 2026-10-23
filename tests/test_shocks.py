"""Tests of the shocks: the shock lists online (SODA, IRFU), the shock list files and their combination"""
import io
import json

import pandas as pd
import pytest

from spearhead.sep_pact import shocks
from spearhead.sep_pact.shocks import (combine_shocks, download_shocks, events_outside, parse_irfu, parse_soda,
                                       read_shock_file)
from tests.conftest import DATA

# the download of the shock lists online, which the offline tests replace with their copies
REAL_GET = shocks._get


def times(*values) -> list:
    return [pd.Timestamp(value) for value in values]


def test_parse_soda_keeps_the_solar_orbiter_shocks():
    rows = [{"SC": "SLO", "Time": "2021/11/03 08:02:58"}, {"SC": "PSP", "Time": "2021/11/01 00:00:00"},
            {"SC": "SLO", "Time": "2021/10/30 22:02:09"}]
    assert parse_soda(json.dumps(rows)).tolist() == times("2021-10-30 22:02:09", "2021-11-03 08:02:58")


def test_parse_soda_of_other_spacecraft():
    rows = [{"SC": "SLO", "Time": "2021/11/03 08:02:58"}, {"SC": "PSP", "Time": "2021/11/01 00:00:00"}]
    assert parse_soda(json.dumps(rows), "PSP").tolist() == times("2021-11-01")


def test_parse_irfu_skips_the_comments():
    text = "# Num  Time of ramp (UTC)  |R| (AU)\n001     2020-04-19T05:06:18     0.8   NaN   47\n" \
           "002     2020-05-01T10:00:00     0.9   2.1   60\n"
    assert parse_irfu(text).tolist() == times("2020-04-19 05:06:18", "2020-05-01 10:00:00")


@pytest.mark.parametrize("source, n, first, last", [
    ("SODA", 18, "2021-05-04 16:26:57", "2021-12-27 10:16:33"),
    ("IRFU", 103, "2020-04-19 05:06:18", "2024-03-01 13:10:31"),
])
def test_download_shocks(source, n, first, last):
    # from the copies in tests/data (conftest.py)
    downloaded = download_shocks(source)
    assert len(downloaded) == n and downloaded.min() == pd.Timestamp(first) and downloaded.max() == pd.Timestamp(last)
    assert downloaded.is_monotonic_increasing and downloaded.dtype == "datetime64[ns]"


def test_download_shocks_of_an_unknown_list():
    with pytest.raises(ValueError, match="There is no shock list online 'ipshocks'; the lists are: SODA, IRFU"):
        download_shocks("ipshocks")


@pytest.mark.parametrize("name, n, first", [
    ("ipshocks_solo.dat", 70, "2021-06-13 10:08:41"),
    ("irfu_solo.txt", 103, "2020-04-19 05:06:18"),
    ("shocks.csv", 2, "2021-11-02 12:00:00"),
])
def test_read_shock_file_of_each_format(name, n, first):
    read = read_shock_file(f"{DATA}/{name}")
    assert len(read) == n and read.iloc[0] == pd.Timestamp(first)


@pytest.mark.parametrize("name", ["shocks_example.csv", "shocks_ipshocks_example.dat", "shocks_irfu_example.txt"])
def test_example_shock_files(name):
    # the shocks around the example event, in each format
    read = read_shock_file(f"inputs/{name}")
    assert read.iloc[0].floor("min") == pd.Timestamp("2021-10-30 22:02")
    assert read.iloc[-1].floor("min") == pd.Timestamp("2021-11-03 14:04")


@pytest.mark.parametrize("separator", [",", ";", "\t"])
def test_read_shock_file_csv_with_each_separator(tmp_path, separator):
    path = tmp_path / "shocks.csv"
    path.write_text(f"# shocks\nShock Time{separator}Note\n2021-11-02 12:00{separator}a\n2021-11-01 10:00{separator}\n")
    assert list(read_shock_file(str(path))) == times("2021-11-01 10:00", "2021-11-02 12:00")


def test_read_shock_file_csv_with_a_time_in_another_format(tmp_path):
    path = tmp_path / "shocks.csv"
    path.write_text("Shock Time\n2021-11-01 10:00\n02/11/2021 12:00\n")
    with pytest.raises(ValueError, match=f"The shock list {path}, Shock Time: '02/11/2021 12:00' is not a time as "
                                         "YYYY-MM-DD HH:MM"):
        read_shock_file(str(path))


def test_read_shock_file_not_found():
    with pytest.raises(ValueError, match="The shock list missing.dat is not found"):
        read_shock_file("missing.dat")


def test_read_shock_file_in_another_format(tmp_path):
    path = tmp_path / "shocks.txt"
    path.write_text("2021;6;13\n")
    with pytest.raises(ValueError, match="has no shocks in one of the formats: an ipshocks list"):
        read_shock_file(str(path))


def test_combine_shocks_sorted_with_their_source_and_without_merging():
    combined = combine_shocks({"SODA": pd.Series(times("2021-11-03 08:02:58", "2021-11-05")),
                               "custom": pd.Series(times("2021-11-03 08:03"))})
    assert list(zip(combined["Shock Time"], combined["Source"])) == [
        (pd.Timestamp("2021-11-03 08:02:58"), "SODA"), (pd.Timestamp("2021-11-03 08:03"), "custom"),
        (pd.Timestamp("2021-11-05"), "SODA")]


def test_combine_shocks_without_the_removed_ones():
    combined = combine_shocks({"SODA": pd.Series(times("2021-11-03", "2021-11-05"))}, [pd.Timestamp("2021-11-05")])
    assert combined["Shock Time"].tolist() == times("2021-11-03")


def test_combine_no_shocks():
    combined = combine_shocks({})
    assert combined.empty and combined["Shock Time"].dtype == "datetime64[ns]"


def test_events_outside():
    events = pd.DataFrame({"Start Time": times("2021-01-01", "2021-06-01"), "End Time": times("2021-01-03", "2021-06-03")},
                          index=[1, 2])
    assert events_outside(events, pd.Series(times("2020-12-01", "2021-03-01"))) == [2]
    assert events_outside(events, pd.Series(times("2020-12-01", "2021-12-01"))) == []
    assert events_outside(events, pd.Series([], dtype="datetime64[ns]")) == [1, 2]


@pytest.mark.network
@pytest.mark.parametrize("source", list(shocks.SHOCK_SOURCES))
def test_download_shocks_online(source):
    downloaded = download_shocks(source)
    assert len(downloaded) > 50 and downloaded.min() < pd.Timestamp("2021-01-01")


def test_download_waits_60_seconds_for_the_server(monkeypatch):
    timeouts = []

    def urlopen(url, timeout):
        timeouts.append(timeout)
        return io.BytesIO(b"content")

    monkeypatch.setattr(shocks.urllib.request, "urlopen", urlopen)
    assert REAL_GET(shocks.SODA_URL) == b"content" and timeouts == [60]
