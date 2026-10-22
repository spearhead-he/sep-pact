"""CSV input files, written by hand or saved by spreadsheet programs: their column separator and their times

This module uses only pandas and the standard library, so that the SPEARHEAD tools can share it.
"""
import pandas as pd

# the accepted column separators, with their names for the messages; a comma when none is found
SEPARATORS = {",": "','", ";": "';'", "\t": "tab"}
TIME_FORMAT = "YYYY-MM-DD HH:MM or YYYY-MM-DD HH:MM:SS (UTC)"
SPREADSHEET_HINT = ("Spreadsheet programs can change the format of the times when they save a CSV file; set the format "
                    "of the time cells to YYYY-MM-DD HH:MM:SS before saving.")


def csv_separator(path: str) -> str:
    """Returns the column separator of the CSV file: the one of SEPARATORS that splits its header (its first line that
    is not empty or a comment starting with #) into the most columns"""
    with open(path, encoding="utf-8-sig") as file:
        header = next((line for line in file if line.strip() and not line.startswith("#")), "")
    # the first one, a comma, on a tie
    return max(SEPARATORS, key=header.count)


def parse_times(values: pd.Series, where) -> pd.Series:
    """Returns the times of the values (ISO 8601), or raises an error for the first value in another format, which
    says where it is with where(index of the value)"""
    try:
        return pd.to_datetime(values, format="ISO8601")
    except ValueError:
        for index, value in values.dropna().items():
            try:
                pd.to_datetime(pd.Series([value]), format="ISO8601")
            except ValueError:
                raise ValueError(f"{where(index)}: {str(value)!r} is not a time as {TIME_FORMAT}. "
                                 f"{SPREADSHEET_HINT}") from None
        raise
