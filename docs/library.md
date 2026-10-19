# SEP-PACT library guide

- [Installation](#installation)
- [A minimal script](#a-minimal-script)
- [Parameters](#parameters)
- [The analysis](#the-analysis)
- [Results](#results)
- [Plots](#plots)
- [Notebook interface](#notebook-interface)
- [Modules](#modules)

The notebook `sep-pact.ipynb` uses the package `spearhead.sep_pact`, which can also be used in scripts. This guide describes its main classes and functions; the [user guide](user_guide.md) describes the parameters, the steps and the results.

## Installation

From the repository folder:

```bash
pip install -e .
```

`pip install -e ".[notebook]"` also installs the notebook dependencies, and `pip install -e ".[test]"` the test dependencies.

## A minimal script

```python
from spearhead.sep_pact import SEPPACT, SEPPACT_parameters

params = SEPPACT_parameters(file_events="inputs/events_example.csv")
tool = SEPPACT(params)
tool.run_inputs()
tool.run_data()
tool.run_onsets()
tool.run_spikes()
tool.run_peaks()
tool.run_fluences()
tool.plot_events()
tool.save_results()

print(tool.df_results)
```

The script reads `inputs/events_example.csv` and `inputs/shocks.dat`, writes the plots to `plots/` and the tables to `outputs/`, relative to the working folder.

## Parameters

`SEPPACT_parameters` (`spearhead.sep_pact.conf`) is a dataclass with all the parameters and their defaults; see [Parameters](user_guide.md#parameters). A parameter left out keeps its default:

```python
from datetime import timedelta

params = SEPPACT_parameters(file_events="my_events.csv", onset_sigma=3)
params.resample_freqs = [timedelta(minutes=5), timedelta(minutes=30)]
params.spike_thresholds = {timedelta(minutes=5): 2.0, timedelta(minutes=30): 3.0}
params.check()
```

- An unknown name raises an `AttributeError` that lists the parameters.
- An invalid value (e.g. a viewing that is not `sun`, `asun`, `north` or `south`, or resolutions not in ascending order) raises a `ValueError` or `TypeError`.
- `check()` checks the parameters that depend on each other, e.g. a spike threshold for each resolution. `SEPPACT` calls it when it is created.
- `params.reference_channel` is the reference channel of `group_options`, as a dict with `particle`, `mev` (the group label) and `sensor`, or `None`.

## The analysis

`SEPPACT(params)` (`spearhead.sep_pact.analysis`) runs the steps of the analysis, which are called in this order:

| Method | Step |
|---|---|
| `run_inputs()` | Reads the shock list and the events: the event list, or `date_ranges` without one |
| `run_data(redownload=False)` | Loads the flux of the channel groups from the cache, or downloads it (always with `redownload=True`) and resamples it |
| `run_onsets()` | Detects the onsets of every resolution and viewing (`calculate_onsets()`), and chooses one per event and channel group (`select_onsets()`) |
| `run_spikes()` | Finds the spikes after the chosen onsets |
| `run_peaks()` | Finds the peak flux of every resolution and viewing (`calculate_peaks()`), and chooses one (`select_peaks()`) |
| `run_fluences()` | Calculates the fluence of every resolution (`calculate_fluences()`), and chooses one (`select_fluences()`) |
| `plot_events()` | Writes one plot per event to `dir_plots` |
| `save_results()` | Writes `results.csv`, the table of `results_table()`, to `dir_outputs` |

## Results

After the steps, the results are attributes of the `SEPPACT` object:

| Attribute | Content |
|---|---|
| `events` | The events: `Start Time`, `BG Start`, `BG End`, `End Time` and `Reference Time` (if given), with the default windows filled in, and the period of data (`Plot Start`, `Plot End`) |
| `shocktimes` | The times of the shocks (`pandas.Series`) |
| `dfs_flux` | The flux of the channel groups: `dfs_flux[particle][sensor][resolution]` is a DataFrame indexed by event number and time, with the columns (viewing, group) |
| `df_series` | The results of every series: one row per event, particle, sensor, channel group (`Energy Label`), resolution and viewing (see below) |
| `df_spikes` | The spike times: one row per spike, with the index of its series and the column `Spike Time` |
| `df_results` | The chosen results: one row per event and channel group, indexed by `Event No`, `Particle`, `Sensor` and `Energy Label` (see below) |

The three tables have one row per item and one column per quantity, with the resolutions as `Timedelta`. Their rows are in the order of the event list and the parameters (`group_options`, `resample_freqs`, `viewings`).

`df_series` has the columns:
- `Onset Time`, `BG Level` and `Threshold`, from `calculate_onsets()`;
- `Onset Copied`: `True` if the series had no onset and took the one of the reference channel at the same resolution and viewing;
- `Quality Length`, `Quality Zeroes` and `Quality Ratio`: the number of points from the onset to the end of the analysis, of zero or NaN values, and the ratio of transitions to them; `Usable`: whether the data quality is good enough for the onset to be chosen;
- `Peak Flux` and `Peak Flux Time`, from `calculate_peaks()`;
- `Fluence`, `Fluence Start`, `Fluence End` and `Fluence Threshold`, from `calculate_fluences()`.

`df_results` has the columns of [results.csv](user_guide.md#resultscsv) (without the energies, and with the resolutions as `Timedelta`) and the data quality of the chosen onset (`Quality Length`, `Quality Zeroes`, `Quality Ratio`).

```python
series = tool.df_series.loc[(20, "protons", "HET", "8 MeV")]          # the series of a channel group, by resolution and viewing
onsets = tool.df_series["Onset Time"].unstack("Viewing")               # one column per viewing
chosen = tool.df_results.loc[(20, "protons", "HET", "8 MeV"), "Onset Time"]
```

The choices are made by `choose_onset()`, `choose_peak()` and `choose_fluence()` (`spearhead.sep_pact.analysis`), from the rows of `df_series` of a channel group. Of equal values, the first viewing (in the order of `viewings`) or the first resolution is chosen.

`tool.results_table()` returns `df_results` as the table of `results.csv`: one row per event and channel group, with the energy range of the group and the resolutions in minutes. `tool.group_energies(particle, sensor, group)` returns the low and high energy of a channel group, in MeV.

```python
results = tool.results_table()
protons = results[results["Particle"] == "protons"]
```

## Plots

`spearhead.sep_pact.views.plot_event(tool, event_no, filename=None)` returns the plot of one event as a matplotlib `Figure`, and saves it if a file name is given. `event_plot_filename(tool, event_no)` gives the file name that `plot_events()` uses in `dir_plots`.

```python
from spearhead.sep_pact.views import plot_event

fig = plot_event(tool, 20)
fig.savefig("event_20.pdf")
```

## Notebook interface

`SEPPACT_notebook` (`spearhead.sep_pact.notebook`, with the `notebook` extra) is the interface of `sep-pact.ipynb`. It can be created with parameters, e.g. to start the form from other defaults, and its results are the same attributes as those of `SEPPACT`:

```python
from spearhead.sep_pact import SEPPACT_parameters
from spearhead.sep_pact.notebook import SEPPACT_notebook

tool = SEPPACT_notebook(SEPPACT_parameters(file_events="my_events.csv"))
tool.parameters_form()
tool.run_data()
tool.run_analysis()
tool.df_results           # the same as tool.seppact.df_results
```

- `tool.parameters` is the `SEPPACT_parameters` of the form, and `tool.errors` the values of the form that are not accepted.
- `run_data()` creates `tool.seppact`, a `SEPPACT` with a copy of the parameters, so that a later change in the form does not change an analysis that has run.
- `tool.widgets` holds the widgets of the form by parameter name, and those of the event viewer.

## Modules

| Module | Content |
|---|---|
| `conf` | `SEPPACT_parameters`, and the default channel groups and spike thresholds |
| `inputs` | `read_shocks(path)`, `read_events(path, params)` and `make_events(params)` (the event list, or the date ranges), and `EVENT_LIST_LAYOUTS`, the accepted columns of the event list |
| `data` | `load()`, which returns the EPD data of each particle as `ParticleData` (the flux with the channel numbers as columns, and the energies of the channels), `load_energies()`, `group_channels_de()`, `flux_cache_file()`, `download_data()` and `resample_flux()`: the EPD data, the flux of the channel groups and its cache |
| `analysis` | `SEPPACT`, and the functions of the steps: `onset_detection_sigma()` (which returns the onset, the background start and end, and the background level and threshold), `quality_analysis()`, `choose_onset()`, `choose_peak()`, `choose_fluence()`, `detect_spikes()`, `remove_spikes()`, `get_peak_flux()`, `fluence_interval()`, `peak_search_end()` and `shocks_in_range()` |
| `views` | `plot_event()` and `event_plot_filename()` |
| `notebook` | `SEPPACT_notebook`, the interface of the notebook (needs the `notebook` extra) |
