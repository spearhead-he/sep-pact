# Development

- [Installation](#installation)
- [Tests](#tests)
- [Baseline images](#baseline-images)
- [Continuous integration](#continuous-integration)

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
| `test_shocks.py` | The shocks: the SODA and IRFU lists and their downloads, the formats of the shock list files, their combination and the events outside the lists |
| `test_inputs.py` | The shocks of the parameters and their warnings, and the event list: its layouts and examples, the rows of particles and sensors and the times given more than once, the default windows, the order of the times, the data period, the date ranges, invalid files and former Onset Time lists |
| `test_background.py` | The background windows per event, particle and sensor (`background.py`): the rows of particles and sensors in the event list, the last of the times given more than once and its message, the fallback to the window of the particle and of the event, setting and resetting the windows, the default window, the names of the particles and sensors, and the event list with the windows |
| `test_event_times.py` | The event times: where the background window and end time come from, setting and resetting them, invalid times, the points of the window and their warnings, the effect on the onsets, and `save_events()` |
| `test_data.py` | The channel layout, the grouping of the channels, the download with its cache and retries, the resampling |
| `test_onsets.py` | Onset detection, data quality, and the choice of the onset: resolution, viewing, reference window, copied onsets, onsets at the end of the background, shocks |
| `test_spikes.py` | Spike detection with the threshold of each resolution, and spike removal |
| `test_peaks_fluence.py` | Peak flux and fluence: the functions, the choice of the viewing and resolution, shocks |
| `test_corrections.py` | Onset corrections: setting another onset or no onset, the reference channel, running the steps again for one event as for all the events, invalid corrections, saving them and applying the file of corrections |
| `test_results.py` | A whole synthetic run: the result tables and the files of `save_results()` and `plot_events()` |
| `test_views.py` | The plots: file names, saving, and the plot of an event compared with baseline images, with 1 to 6 channel groups and small, medium and large panels (the title, legend and panels, and the texts in the corners of the panels), the entries and groups of the legend, the order of the drawn elements, the titles of corrected panels, and the plot of the event times |
| `test_notebook.py` | The notebook interface without a browser: the fields of the form and their errors, the viewings and resolutions, the summaries of the input files, the channel group editor, and the steps: the event times with their sliders, the event viewer with the onset corrections, and saving the event list and the corrections |
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
