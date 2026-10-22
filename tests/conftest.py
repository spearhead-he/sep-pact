import json
import os

import pytest

import spearhead.sep_pact.shocks as shocks

# copies of the shock lists online, for the offline tests
DATA = os.path.join(os.path.dirname(__file__), "data")
IRFU_FILE_URL = "https://zenodo.org/api/records/14001054/files/irfu.txt/content"


def fake_get(url: str) -> bytes:
    """The content of the shock lists online, from the copies in tests/data"""
    if url == shocks.SODA_URL:
        path = os.path.join(DATA, "soda.json")
    elif url == shocks.IRFU_RECORD_URL:
        return json.dumps({"files": [{"key": "Solar Orbiter IRFU IP Shock List_v2.txt",
                                      "links": {"self": IRFU_FILE_URL}}]}).encode()
    elif url == IRFU_FILE_URL:
        path = os.path.join(DATA, "irfu_solo.txt")
    else:
        raise OSError(f"No connection to {url} in the offline tests")
    with open(path, "rb") as file:
        return file.read()


@pytest.fixture(autouse=True)
def offline_shock_lists(request, monkeypatch):
    """The offline tests read the shock lists online from their copies"""
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(shocks, "_get", fake_get)


def pytest_collection_modifyitems(items):
    """Runs the fast offline tests before the network tests, which download data"""
    items.sort(key=lambda item: item.get_closest_marker("network") is not None)
