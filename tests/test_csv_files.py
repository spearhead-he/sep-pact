"""Tests of the CSV input files: their column separator and their times"""
import pandas as pd
import pytest

from spearhead.sep_pact.csv_files import csv_separator, parse_times


@pytest.mark.parametrize("header, separator", [
    ("Event No,Start Time,End Time", ","),
    ("Event No;Start Time;End Time", ";"),
    ("Event No\tStart Time\tEnd Time", "\t"),
    # a comma inside a column name of a list separated by ';'
    ("Event No;Start Time, UTC;BG End;End Time", ";"),
    ("Shock Time", ","),
])
def test_csv_separator(tmp_path, header, separator):
    path = tmp_path / "list.csv"
    path.write_text(f"{header}\n1\n")
    assert csv_separator(str(path)) == separator


def test_csv_separator_after_comments_and_a_byte_order_mark(tmp_path):
    path = tmp_path / "list.csv"
    path.write_bytes("﻿# shocks\n\nShock Time;Source\n".encode())
    assert csv_separator(str(path)) == ";"


def test_csv_separator_of_an_empty_file(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text("")
    assert csv_separator(str(path)) == ","


def test_parse_times_in_iso_format():
    times = parse_times(pd.Series(["2021-11-01 10:00", "2021-11-01T10:00:30", None]), str)
    assert list(times[:2]) == [pd.Timestamp(2021, 11, 1, 10), pd.Timestamp(2021, 11, 1, 10, 0, 30)]
    assert pd.isna(times[2])


def test_parse_times_names_the_first_time_in_another_format():
    values = pd.Series(["2021-11-01 10:00", "01/11/2021 10:00", "2/11/2021"], index=[2, 3, 4])
    with pytest.raises(ValueError) as error:
        parse_times(values, lambda line: f"Line {line}")
    assert str(error.value).startswith("Line 3: '01/11/2021 10:00' is not a time as YYYY-MM-DD HH:MM or "
                                       "YYYY-MM-DD HH:MM:SS (UTC). Spreadsheet programs can change the format")


def test_parse_times_keeps_the_error_of_times_valid_one_by_one():
    # each time is ISO 8601, but not all of them have a time zone
    with pytest.raises(ValueError, match="Mixed timezones"):
        parse_times(pd.Series(["2021-11-01 10:00+00:00", "2021-11-01 10:00"]), str)
