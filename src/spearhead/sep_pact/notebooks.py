"""The notebook of the SEP-PACT tool and its example files, for an installation of the package (e.g. from PyPI).

The notebook is not part of the package: copy_notebooks() downloads it, with the example files, from the GitHub
release of the installed version. It is also the command spearhead-sep-pact-notebooks:

    spearhead-sep-pact-notebooks              # into the current folder
    spearhead-sep-pact-notebooks my_folder    # into my_folder
"""
import argparse
import os
from urllib.error import HTTPError
from urllib.request import urlopen

from . import __version__

REPOSITORY_RAW_URL = "https://raw.githubusercontent.com/spearhead-he/sep-pact"

# The notebook and its example files, as paths in the repository: the event lists in each layout and the shock lists
# in each format
FILES = (
    "sep-pact.ipynb",
    "inputs/events_example.csv",
    "inputs/datetime_range_example.csv",
    "inputs/datetime_range_only_example.csv",
    "inputs/reference_times_example.csv",
    "inputs/shocks_example.csv",
    "inputs/shocks_ipshocks_example.dat",
    "inputs/shocks_irfu_example.txt",
)


def files_url(version) -> str:
    """URL of the files of the repository at the release of the version"""
    return f"{REPOSITORY_RAW_URL}/v{version}"


def copy_notebooks(folder=".", overwrite=False, version=__version__) -> dict:
    """Downloads the notebook and its example files of the version (by default the installed one) into the folder.

    Existing files are kept, unless overwrite is True. Returns {path: "downloaded" or "kept"}.
    """
    url = files_url(version)
    copied = {}
    for name in FILES:
        path = os.path.join(folder, *name.split("/"))
        if os.path.exists(path) and not overwrite:
            copied[path] = "kept"
            continue
        try:
            with urlopen(f"{url}/{name}", timeout=60) as response:
                data = response.read()
        except HTTPError as e:
            if e.code == 404:
                raise ValueError(f"{name} of version {version} not found on GitHub ({url}/{name}): "
                                 f"is v{version} a release of the SEP-PACT tool?") from None
            raise
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        copied[path] = "downloaded"
    return copied


def main(argv=None) -> None:
    """The command spearhead-sep-pact-notebooks"""
    parser = argparse.ArgumentParser(
        prog="spearhead-sep-pact-notebooks",
        description="Downloads the notebook of the SPEARHEAD SEP-PACT tool and its example files from GitHub, "
                    "for the installed version of the tool.",
    )
    parser.add_argument("folder", nargs="?", default=".", help="folder to download them into (default: the current one)")
    parser.add_argument("--overwrite", action="store_true", help="replace the files that already exist")
    parser.add_argument("--version", default=__version__,
                        help=f"version of the tool whose notebook is downloaded (default: the installed one, {__version__})")
    args = parser.parse_args(argv)
    try:
        copied = copy_notebooks(args.folder, args.overwrite, args.version)
    except ValueError as e:
        parser.exit(1, f"Error: {e}\n")
    for path, action in copied.items():
        print(f"{'Downloaded' if action == 'downloaded' else 'Kept the existing'} {path}")
    if "kept" in copied.values():
        print("Use --overwrite to replace the existing files.")
    print(f"Open the notebook with: jupyter-lab {os.path.join(args.folder, FILES[0])}")
