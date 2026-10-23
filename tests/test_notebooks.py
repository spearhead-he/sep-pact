"""Download of the notebook and its example files (spearhead-sep-pact-notebooks), without the network"""
import io
import json
import re
from pathlib import Path
from urllib.error import HTTPError

import pytest

from spearhead.sep_pact import SEPPACT_parameters, __version__, notebooks

REPOSITORY = Path(__file__).parents[1]


@pytest.fixture
def downloads(monkeypatch):
    """The URLs requested, each answered with its file name as content"""
    urls = []

    def urlopen(url, timeout=None):
        urls.append(url)
        return io.BytesIO(url.rsplit("/", 1)[1].encode())

    monkeypatch.setattr(notebooks, "urlopen", urlopen)
    return urls


def test_copy_notebooks(downloads, tmp_path):
    copied = notebooks.copy_notebooks(tmp_path)
    # the files of the installed version
    assert downloads[0] == f"https://raw.githubusercontent.com/spearhead-he/sep-pact/v{__version__}/sep-pact.ipynb"
    assert len(downloads) == len(notebooks.FILES)
    assert set(copied.values()) == {"downloaded"}
    assert (tmp_path / "sep-pact.ipynb").read_text() == "sep-pact.ipynb"
    assert (tmp_path / "inputs" / "events_example.csv").read_text() == "events_example.csv"


def test_existing_files_kept(downloads, tmp_path):
    (tmp_path / "sep-pact.ipynb").write_text("my notebook")
    copied = notebooks.copy_notebooks(tmp_path, version="1.2.3")
    assert copied[str(tmp_path / "sep-pact.ipynb")] == "kept"
    assert (tmp_path / "sep-pact.ipynb").read_text() == "my notebook"
    assert all("/v1.2.3/" in url for url in downloads) and len(downloads) == len(notebooks.FILES) - 1
    notebooks.copy_notebooks(tmp_path, overwrite=True)
    assert (tmp_path / "sep-pact.ipynb").read_text() == "sep-pact.ipynb"


@pytest.mark.parametrize("code", [404, 500])
def test_download_errors(monkeypatch, tmp_path, code):
    def urlopen(url, timeout=None):
        raise HTTPError(url, code, "error", None, None)

    monkeypatch.setattr(notebooks, "urlopen", urlopen)
    if code == 404:
        with pytest.raises(ValueError, match="version 0.0.1 not found on GitHub"):
            notebooks.copy_notebooks(tmp_path, version="0.0.1")
    else:
        with pytest.raises(HTTPError):
            notebooks.copy_notebooks(tmp_path)


def test_command(downloads, tmp_path, capsys):
    (tmp_path / "sep-pact.ipynb").write_text("my notebook")
    notebooks.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert f"Kept the existing {tmp_path / 'sep-pact.ipynb'}" in out
    assert f"Downloaded {tmp_path / 'inputs' / 'shocks_irfu_example.txt'}" in out
    assert "Use --overwrite to replace the existing files." in out
    assert f"Open the notebook with: jupyter-lab {tmp_path / 'sep-pact.ipynb'}" in out
    notebooks.main([str(tmp_path), "--overwrite"])
    assert "Use --overwrite" not in capsys.readouterr().out


def test_command_error(monkeypatch, tmp_path, capsys):
    def urlopen(url, timeout=None):
        raise HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(notebooks, "urlopen", urlopen)
    with pytest.raises(SystemExit) as e:
        notebooks.main([str(tmp_path), "--version", "9.9.9"])
    assert e.value.code == 1
    assert "Error: sep-pact.ipynb of version 9.9.9 not found" in capsys.readouterr().err


def test_files_are_in_the_repository():
    assert [name for name in notebooks.FILES if not (REPOSITORY / name).is_file()] == []


def test_default_event_list_is_downloaded():
    # the notebook runs with its defaults in the downloaded folder
    assert SEPPACT_parameters().file_events in notebooks.FILES


def test_notebook_links_work_in_the_downloaded_folder():
    # the downloaded folder has only the notebook and the example files: other links go to GitHub
    cells = json.loads((REPOSITORY / "sep-pact.ipynb").read_text())["cells"]
    text = "".join("".join(cell["source"]) for cell in cells if cell["cell_type"] == "markdown")
    targets = [target.split("#")[0] for target in re.findall(r"\]\(([^)]+)\)", text)]
    assert targets
    relative = [target for target in targets if not target.startswith(("https://", "http://")) and target]
    assert [target for target in relative if target not in notebooks.FILES] == []
