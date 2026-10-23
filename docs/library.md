# SEP-PACT library guide

- [Installation](#installation)
- [A minimal script](#a-minimal-script)
- [Parameters](#parameters)
- [The analysis](#the-analysis)
- [Event times](#event-times)
- [Onset corrections](#onset-corrections)
- [Results](#results)
- [Plots](#plots)
- [Notebook interface](#notebook-interface)
- [Modules](#modules)

The notebook `sep-pact.ipynb` uses the package `spearhead.sep_pact`, which can also be used in scripts. This guide describes its main classes and functions; the [user guide](user_guide.md) describes the parameters, the steps and the results.

## Installation

From PyPI, without the notebook dependencies:

```bash
pip install spearhead-sep-pact
```

`pip install "spearhead-sep-pact[notebook]"` also installs the notebook dependencies. From the repository folder, `pip install -e .` installs the code of the repository, with the extras `notebook` and `test` (the test dependencies).

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

The script reads `inputs/events_example.csv`, downloads the SODA shock list, writes the plots to `plots/` and the tables to `outputs/`, relative to the working folder.

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
| `run_inputs()` | Reads the events (the event list, or `date_ranges` without one) and the shocks, and prints the warnings about the shocks |
| `run_data(redownload=False)` | Loads the flux of the channel groups from the data files (downloading the missing ones) or, with `cache_data`, from the cache (not with `redownload=True`), and resamples it; the events that cannot be loaded are left out (`skipped_events`) |
| `run_onsets()` | Detects the onsets of every resolution and viewing (`calculate_onsets()`), and chooses one per event and channel group (`select_onsets()`) |
| `run_spikes()` | Finds the spikes after the chosen onsets |
| `run_peaks()` | Finds the peak flux of every resolution and viewing (`calculate_peaks()`), and chooses one (`select_peaks()`) |
| `run_fluences()` | Calculates the fluence of every resolution (`calculate_fluences()`), and chooses one (`select_fluences()`) |
| `plot_events()` | Writes one plot per event to `dir_plots` |
| `save_results()` | Writes `results.csv`, the table of `results_table()`, to `dir_outputs` |

`select_onsets()`, `run_spikes()`, `calculate_peaks()`, `select_peaks()`, `calculate_fluences()` and `select_fluences()` take an optional event number, to run for that event only; [onset corrections](#onset-corrections) use it.

## Event times

After `run_data()`, and before the onsets, the background window and the end time of an event can be changed within its loaded data (the [Event times](user_guide.md#event-times-step) step of the notebook):

```python
tool.set_bg_window(20, "2021-11-01 00:00", "2021-11-01 01:30")   # BG Start, BG End of the event
tool.set_bg_window(20, "2021-11-01 00:00", "2021-11-01 02:30", "protons", "HET")   # of a particle and sensor
tool.set_bg_window(20, "2021-11-01 00:00", "2021-11-01 02:30", "protons")          # of a particle, all its sensors
tool.bg_window(20, "protons", "HET")   # (start, end, source, particle, sensor) of the window that the series use
tool.set_end_time(20, "2021-11-02 12:00")
tool.bg_window_points(20)      # {resolution: the fewest points with data in the window of each series of the event}
tool.bg_window_points(20, "protons", "HET")   # of the series of a particle and sensor
tool.bg_window_series(20)      # {(particle, sensor) of each window, ("", "") for the event: the series that use it}
tool.bg_window_warnings(20)    # a warning for each window and resolution with fewer than 3 points
tool.reset_bg_window(20, "protons", "HET")   # the window of the event list, or else the window of the event
tool.reset_bg_window(20)       # the window of the event list, or the default one
tool.reset_end_time(20)
tool.save_events("outputs/events.csv")
```

- The times must stay in the order Start Time ≤ BG Start < BG End < End Time for every window of the event, and the end time within the loaded data (`Plot End`); otherwise a `ValueError` says why, and the event is not changed.
- A series uses the window of its particle and sensor, else of its particle, else of the event (see [Background windows of particles and sensors](user_guide.md#bg-windows-of-particles)). `events` has the window of each event; `bg_windows`, a `BackgroundWindows`, has all of them.
- The columns `BG Window Source` and `End Time Source` of `events` say where the times of the event come from: `event list`, `default` or `set`; in `results.csv`, `BG Start`, `BG End` and `BG Window Source` are the ones of the window of each channel group.
- `save_events(path)` writes the event list with the times of all the events and the rows of the windows of particles and sensors, which can be given as `file_events`.

`spearhead.sep_pact.background` holds the windows and does not depend on the rest of the package:

```python
from datetime import timedelta
from spearhead.sep_pact.background import BackgroundWindows

# ranges: Start Time and End Time, indexed by Event No; windows: BG Start and BG End, indexed by Event No, Particle
# and Sensor ("" for none)
bg = BackgroundWindows(ranges, windows, default=(timedelta(0), timedelta(hours=2)))
bg.window(1, "protons", "HET")   # BGWindow(start, end, source, particle, sensor)
bg.set(1, start, end, "protons", "HET")
bg.reset(1, "protons", "HET")
bg.to_frame()                    # all the windows, with their source
```
- Run `run_onsets()` and the next steps again after a change.

## Onset corrections

After `run_onsets()`, the onset of a channel group can be set to one of the onsets detected in its series, or to no onset (the [Onset corrections](user_guide.md#onset-corrections) of the notebook). The steps that have run are run again for that event only:

```python
tool.set_onset(20, "electrons", "HET", "1 MeV", 2, "south")     # resolution (minutes or timedelta), viewing
tool.set_onset(20, "protons", "HET", "8 MeV")                   # no onset
tool.reset_onset(20, "protons", "HET", "8 MeV")                 # the automatic choice
tool.corrections        # {(event, particle, sensor, group): (resolution, viewing), or None for no onset}
tool.save_corrections("outputs/corrections.csv")
```

- A series without an onset, or a channel group or series that does not exist, raises a `ValueError`.
- A corrected reference channel changes the onsets chosen for the other channel groups of its event, except the corrected ones. The corrected rows have `Onset Corrected` set in `df_results`.
- The corrections stay when the steps run again. `save_corrections(path)` writes them, and the parameter `file_corrections` applies a saved file in a later run (read by `run_inputs()`, applied by `select_onsets()`); see the [user guide](user_guide.md#onset-corrections) for its columns and messages. `inputs.read_corrections(path)` reads it.

## Results

After the steps, the results are attributes of the `SEPPACT` object:

| Attribute | Content |
|---|---|
| `events` | The events: `Start Time`, `BG Start`, `BG End`, `End Time` and `Reference Time` (if given), with the default windows filled in, the period of data (`Plot Start`, `Plot End`), and where the background window and end time come from (`BG Window Source`, `End Time Source`) |
| `skipped_events` | The events left out by the data step, as their data could not be loaded: `{event number: error}`; they are not in `events`, and `run_data()` tries them again |
| `bg_windows` | The background windows of the events and of their particles and sensors, a `BackgroundWindows` (see [Event times](#event-times)) |
| `shocks` | The shocks: `Shock Time` and `Source` (`SODA`, `IRFU`, the name of the shock list file, or `custom`), sorted by time, without `removed_shocks` |
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

`tool.results_table()` returns `df_results` as the table of `results.csv`: one row per event and channel group, with the energy range of the group and the resolutions in whole minutes (`Int64`, empty without a result). `tool.group_energies(particle, sensor, group)` returns the low and high energy of a channel group, in MeV.

```python
results = tool.results_table()
protons = results[results["Particle"] == "protons"]
```

## Plots

`spearhead.sep_pact.views.plot_event(tool, event_no, filename=None)` returns the plot of one event as a matplotlib `Figure`, and saves it if a file name is given. `event_plot_filename(tool, event_no)` gives the file name that `plot_events()` uses in `dir_plots`. `plot_background(tool, event_no, filename=None, resolution=None, viewing=None)` returns the plot of the event times step: the flux of all the channel groups per particle and sensor, at a resolution of `resample_freqs` (a `timedelta`) and in a viewing of `viewings` (by default the finest and the first), with the background window of each panel and the start and end times.

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
tool.event_times()
tool.run_analysis()
tool.event_viewer()
tool.df_results           # the same as tool.seppact.df_results
```

- `tool.parameters` is the `SEPPACT_parameters` of the form, and `tool.errors` the values of the form that are not accepted.
- `run_data()` creates `tool.seppact`, a `SEPPACT` with a copy of the parameters, so that a later change in the form does not change an analysis that has run.
- `tool.widgets` holds the widgets of the form by parameter name, and those of the event times step and the event viewer.

## Modules

| Module | Content |
|---|---|
| `conf` | `SEPPACT_parameters`, and the default channel groups and spike thresholds |
| `background` | `BackgroundWindows`, the background windows per event, particle and sensor, and `split_event_rows()`, the rows of an event list with the windows of particles and sensors; it uses only pandas |
| `shocks` | `download_shocks(source)` (the shock lists online of `SHOCK_SOURCES`), `read_shock_file(path)` (the formats of `SHOCK_FILE_FORMATS`), `parse_soda()`, `parse_irfu()`, `parse_ipshocks()`, `combine_shocks()` and `events_outside()`; it uses only pandas and the standard library |
| `inputs` | `load_shocks(params)` and `shock_warnings(shocks, events)`, `read_events(path, params)`, `make_events(params)` and `load_events(params)` (the event list, or the date ranges, and their `BackgroundWindows`), `read_event_list(path)`, `EVENT_LIST_LAYOUTS`, the accepted columns of the event list, and `read_corrections(path)` with `CORRECTION_COLUMNS`, the file of onset corrections |
| `data` | `load()`, which returns the EPD data of each particle as `ParticleData` (the flux with the channel numbers as columns, and the energies of the channels), `load_energies()`, `group_channels_de()`, `download_data()` (which returns the flux and the events left out), `event_cache_key()` and `resample_flux()`: the EPD data, the flux of the channel groups and its cache |
| `analysis` | `SEPPACT`, and the functions of the steps: `onset_detection_sigma()` (which returns the onset, the background start and end, and the background level and threshold), `quality_analysis()`, `choose_onset()`, `choose_peak()`, `choose_fluence()`, `detect_spikes()`, `remove_spikes()`, `get_peak_flux()`, `fluence_interval()`, `peak_search_end()` and `shocks_in_range()` |
| `views` | `plot_event()`, `plot_background()` and `event_plot_filename()` |
| `notebook` | `SEPPACT_notebook`, the interface of the notebook (needs the `notebook` extra) |
