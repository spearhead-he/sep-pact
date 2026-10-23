# Development

- [Installation](#installation)
- [Tests](#tests)
- [Baseline images](#baseline-images)
- [Continuous integration](#continuous-integration)
- [Publishing to PyPI](#publishing-to-pypi)

## Installation

From the base directory of the repository, install the package in editable mode with the dependencies of the notebook and of the tests:

```bash
pip install -e ".[notebook,test]"
```

## Tests

The tests are in `tests/`, one file per part of the tool:

| File | Tests |
|---|---|
| `test_parameters.py` | Parameters: defaults, the checks of each value and their messages, unknown names, the checks between parameters, the reference channel |
| `test_csv_files.py` | The CSV input files: the detection of their column separator, and the error for a time in another format |
| `test_shocks.py` | The shocks: the SODA and IRFU lists and their downloads, the formats of the shock list files and the separators of the CSV ones, their combination and the events outside the lists |
| `test_inputs.py` | The shocks of the parameters and their warnings, and the event list: its layouts and examples, its separators and times in another format, the rows of particles and sensors and the times given more than once, the default windows, the order of the times, the data period, the date ranges, invalid files and former Onset Time lists |
| `test_background.py` | The background windows per event, particle and sensor (`background.py`): the rows of particles and sensors in the event list, the last of the times given more than once and its message, the fallback to the window of the particle and of the event, setting and resetting the windows, the default window, the names of the particles and sensors, and the event list with the windows |
| `test_event_times.py` | The event times: where the background window and end time come from, setting and resetting them, invalid times, the points of the window and their warnings, the effect on the onsets, and `save_events()` |
| `test_data.py` | The channel layout, the grouping of the channels, the download with its retries and its messages without the progress bars of the loader, the events left out, the cache (its entries per event, saved every 10 events and when the loading stops), the resampling |
| `test_onsets.py` | Onset detection, data quality, and the choice of the onset: resolution, viewing, reference window, copied onsets, onsets at the end of the background, shocks |
| `test_spikes.py` | Spike detection with the threshold of each resolution, and spike removal |
| `test_peaks_fluence.py` | Peak flux and fluence: the functions, the choice of the viewing and resolution, shocks |
| `test_corrections.py` | Onset corrections: setting another onset or no onset, the reference channel, running the steps again for one event as for all the events, invalid corrections, saving them and applying the file of corrections |
| `test_results.py` | A whole synthetic run: the result tables and the files of `save_results()` and `plot_events()` |
| `test_views.py` | The plots: file names, saving, and the plot of an event compared with baseline images, with 1 to 6 channel groups and small, medium and large panels (the title, legend and panels, and the texts in the corners of the panels), the texts of the labels and their numbers, the entries and groups of the legend, the order of the drawn elements, the titles of corrected panels, and the plot of the event times, also at another resolution and viewing |
| `test_notebook.py` | The notebook interface without a browser: the fields of the form and their errors, the viewings and resolutions, the summaries of the input files, the channel group editor, and the steps: the event times with their sliders and the resolution and viewing of their plot, the event viewer with the onset corrections, and saving the event list and the corrections |
| `test_notebooks.py` | The command `spearhead-sep-pact-notebooks`: the download of the notebook and its example files of a version, the files kept or overwritten, the errors, and the notebook and its default event list working in the downloaded folder |
| `test_end_to_end.py` | The example event list, from the download of the data to the results and the plot (network) |

The offline tests read the shock lists online from their copies in `tests/data/` (`tests/conftest.py`), which also has the ipshocks list and a CSV shock list of the tests. All the tests except the end-to-end test run offline, with synthetic data built so that the expected results are known (`tests/helpers.py`): a constant background with a linear rise and decay, and a fake `epd_load` that returns data shaped like the real one. The end-to-end test downloads data and is marked `network`; it runs after the offline tests.

To run all the tests, from the base directory of the repository:

```bash
pytest tests/
```

Only the offline tests:

```bash
pytest -m "not network" tests/
```

With the comparison of the plots with their baseline images, and the coverage:

```bash
pytest --mpl --mpl-baseline-path=baseline --mpl-baseline-relative --cov --cov-report=term tests/
```

The notebook, run headless (it downloads the data of the example event, and writes to `plots/` and `outputs/`):

```bash
pytest --nbmake sep-pact.ipynb
```

## Baseline images

The baseline images of the plots are in `tests/baseline/`. Without `--mpl`, the image tests only check that the plots are made. When a change of a plot is intended, generate the baselines again and review the new images before committing them:

```bash
pytest --mpl-generate-path=tests/baseline tests/test_views.py tests/test_end_to_end.py
```

The baselines are made with matplotlib 3.11, the version that CI installs; older versions lay out the figures a few pixels differently. With matplotlib older than 3.11, the image tests run without the comparison (`image_compare` in `tests/helpers.py`).

## Continuous integration

The workflow `.github/workflows/pytest.yml` runs on every push and pull request, with Python 3.11, 3.12, 3.13 and 3.14:
- flake8: it stops on syntax errors and undefined names, and reports the style warnings (line length 127, complexity 10);
- all the tests, with the image comparison and the coverage;
- the notebook, with nbmake.

The coverage is uploaded to Codecov, and the pytest-mpl report of the image comparison is saved as an artifact of each run.

The workflow `.github/workflows/publish.yml` builds the package (sdist and wheel) on every push and pull request, checks it with `twine check --strict`, and checks that the wheel has no `spearhead/__init__.py` (see below). Dependabot (`.github/dependabot.yml`) updates the GitHub Actions of the workflows every month.

## Publishing to PyPI

The package `spearhead-sep-pact` is published to [PyPI](https://pypi.org/project/spearhead-sep-pact/) by `.github/workflows/publish.yml` when a GitHub release is published, with trusted publishing: the PyPI project trusts this workflow and its GitHub environment `pypi`, so no tokens are needed. Publishing waits for the approval of the environment's reviewers. The version is `spearhead.sep_pact.__version__`, which must be new on PyPI.

`spearhead` is a namespace package, shared with the other SPEARHEAD tools (e.g. `spearhead-vda`): the package has only `src/spearhead/sep_pact/`, and no `src/spearhead/__init__.py`, which would overwrite the `spearhead` package of the other tools.

The notebook and its example files are not in the package. The command `spearhead-sep-pact-notebooks [folder]` (`spearhead.sep_pact.notebooks`) downloads them from the GitHub release of the installed version (`raw.githubusercontent.com/spearhead-he/sep-pact/v<version>/`); its list of files is `notebooks.FILES`, which must be updated when the notebook uses a new example file.

Running the workflow manually (Actions > publish > Run workflow) publishes the package to [TestPyPI](https://test.pypi.org/project/spearhead-sep-pact/) (environment `testpypi`), e.g. to check a release before publishing it. A version can be uploaded only once to each index. To install from TestPyPI, download the package without its dependencies (TestPyPI has broken test versions of some of them), then install it with its dependencies from PyPI, e.g. for version 1.0.0:

```bash
pip download --no-deps --index-url https://test.pypi.org/simple/ spearhead-sep-pact==1.0.0 -d dist_test
```

```bash
pip install "dist_test/spearhead_sep_pact-1.0.0-py3-none-any.whl[notebook]"
```

To build and check the package locally:

```bash
pip install build twine
python -m build
twine check --strict dist/*
```
