# SEP-PACT user guide

- [Overview](#overview)
- [Parameters](#parameters)
  - [Events tab](#events-tab)
  - [Data tab](#data-tab)
  - [Energy channels tab](#energy-channels-tab)
  - [Onsets tab](#onsets-tab)
  - [Peak and fluence tab](#peak-and-fluence-tab)
  - [Plots and outputs tab](#plots-and-outputs-tab)
  - [Parameters in scripts](#parameters-in-scripts)
- [Input files](#input-files)
  - [Event list](#event-list)
  - [Shock list](#shock-list)
- [Steps of the notebook](#steps-of-the-notebook)
  - [Data](#data-step)
  - [Analysis](#analysis-step)
  - [Onset](#onset-step)
  - [Spikes](#spikes-step)
  - [Peak flux](#peak-flux-step)
  - [Fluence](#fluence-step)
  - [Events](#events-step)
- [Results](#results)
  - [results.csv](#resultscsv)
  - [Units](#units)
- [Plots](#plots)

## Overview

SEP-PACT analyses the events of an event list with the data of Solar Orbiter EPD/HET (level 2). For each event and energy channel group, it calculates the onset time, the peak flux and the fluence at every resolution and viewing, and chooses one result of each.

The notebook `sep-pact.ipynb` runs the whole analysis. Set the parameters in its form, then run the cells in order. The results are written to `outputs/results.csv`, and the plots to `plots/`.

## Parameters

All the parameters are in the form at the top of the notebook (`tool.parameters_form()`), in tabs. A value that is not accepted, e.g. a fraction above 1 or a missing event list, is shown in red below its field and keeps the previous value; the steps do not run until it is corrected. The parameter names below are those of `SEPPACT_parameters`, for [scripts](#parameters-in-scripts).

### Events tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Event list | `file_events` | `inputs/events_example.csv` | Path of the [event list](#event-list). Below the path, the number of events and the range of their onsets, or why the file cannot be read |
| Shock list | `file_shocks` | `inputs/shocks.dat` | Path of the [shock list](#shock-list), with its number of shocks |
| Background start before the onset (hours) | `bg_start_before_onset` | 2 h | Start of the background window, before the onset of the event list |
| Background end before the onset (minutes) | `bg_end_before_onset` | 5 min | End of the background window, before the onset of the event list |
| End after the onset (hours) | `end_after_onset` | 48 h | End of the event, after the onset of the event list |
| Shortest data period (days) | `min_plot_window` | 2 days | Minimum length of the data period (background start to end); shorter events are extended equally on both sides |

The event windows are used where the event list leaves the background window or the end time empty.

### Data tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Viewings | `viewings` | sun, asun, north, south | HET viewing directions |
| Resolutions | `resample_freqs` | 2, 5, 10, 30 min | Resolutions of the analysis, chosen from 1, 2, 5, 10, 15, 30 and 60 min |
| Spike threshold | `spike_thresholds` | 2.0 (2 and 5 min), 2.5 (10 min), 3.0 (30 min) | Smallest difference, in orders of magnitude, of a spike from both its neighbours, for each resolution |
| Data folder | `dir_data` | `data` | Folder of the downloaded EPD files |
| Cache folder | `dir_saves` | `intermediate_states` | Folder of the cached flux |
| Download tries | `download_tries` | 2 | Tries of each download; the tries after the first load only the background start to the end time |

The data level is `l2` (`level`).

### Energy channels tab

One row per channel group (`group_options`), in the order of the panels of the plots:
- the particle;
- the label: the name of the group in the plots and in `results.csv`, unique for the particle;
- the HET channels it combines, listed with their energy ranges (select several with Ctrl+click). The flux of a group is the mean of its channels weighted by their energy widths;
- "Reference channel": at most one group (see [Onset](#onset-step));
- "Remove", and the buttons "Add electron group" and "Add proton group" above the groups.

The energy ranges of the channels are read from the data of the first event of the event list. If they cannot be read, e.g. without a connection to the data server, the groups are listed without the editor, with the error and a button to read the channels again.

The default groups are:

| Particle | Group | HET channels |
|---|---|---|
| electrons | `1 MeV` (reference channel) | 0, 1 |
| electrons | `5.9930 - 18.8300 MeV` | 3 |
| protons | `8 MeV` | 1, 2, 3 |
| protons | `25 MeV` | 18, 19 |
| protons | `50 MeV` | 27 |

### Onsets tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Threshold, in standard deviations above the background | `onset_sigma` | 2 | Threshold = background mean + `onset_sigma` × background standard deviation |
| Consecutive points above the threshold | `onset_points` | 3 | Points above the threshold that make an onset |
| Largest distance from the reference onset (hours) | `reference_onset_window` | 2.5 h | Onsets further than this from the onset of the reference channel are ignored |
| Largest ratio of transitions to zero or missing values | `quality_tolerance` | 0.1 | Allowed ratio of transitions from valid to zero or NaN values after the onset, to the number of points |
| Tolerance grows with the resolution | `quality_adjustable` | off | If on, the tolerance is multiplied by 1 + resolution / 60 min |

### Peak and fluence tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Search in the first half of the event if it is at least (hours) | `peak_window_min` | 10 h | Spikes and peaks are searched in the first half of the onset to the end, if that half is at least this long |
| Fluence threshold, as a fraction of the peak flux | `fluence_peak_fraction` | 0.5 | The fluence threshold is this fraction of the peak flux |
| Consecutive points at or below the threshold that bound the interval | `fluence_points` | 2 | Consecutive points at or below the fluence threshold that bound the fluence interval |

The fluence is the integral of the flux over an interval around the peak: from where the flux last rises above the fluence threshold before the peak, to where it first falls back to it after the peak (see [Fluence](#fluence-step)).

### Plots and outputs tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Viewing of channel groups without an onset | `fallback_viewing` | sun | Viewing shown, at the coarsest resolution, for a channel group without an onset |
| Save the plots of the events | | on | Whether the results step also writes the plots (see [Results](#results)) |
| Plots folder | `dir_plots` | `plots` | Folder of the plots, one per event |
| Results folder | `dir_outputs` | `outputs` | Folder of `results.csv` |

### Parameters in scripts

In scripts, the parameters are the arguments of `SEPPACT_parameters`; see the [library guide](library.md#parameters). The durations are `datetime.timedelta`, e.g. `timedelta(hours=2)`. An unknown parameter name or an invalid value raises an error that names the valid choices.

## Input files

### Event list

A CSV file, given by its path in the form (see `inputs/events_example.csv`), with one row per event:

```
Event No,Onset Time,BG Start,BG End
20,2021-11-01 02:05:00,2021-10-31 19:00:00,2021-11-01 01:30:00
```


| Column | Required | Description |
|---|---|---|
| `Event No` | yes | Event number, the first column; used in the tables and the plot names |
| `Onset Time` | yes | Approximate onset of the event; only used for the default windows below |
| `BG Start` | no | Start of the background window; default `Onset Time` − `bg_start_before_onset` |
| `BG End` | no | End of the background window; default `Onset Time` − `bg_end_before_onset` |
| `End Time` | no | End of the event; default `Onset Time` + `end_after_onset` |

The columns `BG Start`, `BG End` and `End Time` may be missing or have empty cells. The times are in UTC, as `YYYY-MM-DD HH:MM:SS` or `YYYY-MM-DD HH:MM` (ISO 8601). Spaces after the commas are allowed. The onset itself is always detected in the data, after `BG End`.

Event lists in Excel (`.xlsx`), as in version 0.1.0, are no longer accepted. To convert one, save it as CSV in Excel or a spreadsheet program, or with pandas:

```python
import pandas as pd
pd.read_excel("my_events.xlsx", index_col=0).to_csv("my_events.csv", date_format="%Y-%m-%d %H:%M:%S")
```

### Shock list

The shock list, by default `inputs/shocks.dat`, is the list of interplanetary shocks of the [ipshocks database](https://ipshocks.helsinki.fi/): lines starting with `#` are comments, and the first six columns (separated by `;`) are the year, month, day, hour, minute and second of the shock. The analysis of a channel group ends at the first shock after its onset, if that is before `End Time`.

## Steps of the notebook

1. **Setup:** imports the package and creates the interface, `tool = SEPPACT_notebook()`.
2. **Parameters:** `tool.parameters_form()`; see [Parameters](#parameters).
3. **Data:** `tool.run_data()` reads the event list and the shock list, fills in the missing windows, and downloads the data (see [Data](#data-step)). It shows the event list with its windows.
4. **Analysis:** `tool.run_analysis()` runs the onset, spikes, peak flux and fluence steps (see [Analysis](#analysis-step)).
5. **Events:** `tool.event_viewer()` shows the plot and the results of each event (see [Events](#events-step)).
6. **Results:** `tool.save_results()` writes `results.csv` and, if "Save the plots of the events" is on, the plots (see [Results](#results)).

The analysis uses the parameters of the form when the data step runs; after a change in the form, run the steps again from the data step. The results stay available as attributes of `tool`: `tool.df_series` has the results of every resolution and viewing, and `tool.df_results` the chosen ones; see the [library guide](library.md#results).

<a id="data-step"></a>
### Data

The data of each event, viewing and sensor are downloaded from the Solar Orbiter Archive with [solo-epd-loader](https://github.com/jgieseler/solo-epd-loader) into `dir_data`, for the period from the background start to the end time, extended to `min_plot_window`. Files already in `dir_data` are not downloaded again. The channels of each group are combined, weighted by their energy widths.

The result is cached in `dir_saves`, in a file named after the level, the viewings, the channel groups and the event windows. Running the notebook again with the same settings loads the cache; changing any of them creates a new cache file.

<a id="analysis-step"></a>
### Analysis

The analysis step shows its progress through the onset, spikes, peak flux and fluence steps below, then how many channel groups have an onset, how many of these are copied from the reference channel, and how many are at the end of the background window.

<a id="onset-step"></a>
### Onset

For each event, channel group, resolution and viewing:
1. The background level and standard deviation are calculated from `BG Start` to `BG End`. The threshold is the level plus `onset_sigma` standard deviations.
2. From `BG End` to `End Time`, the onset is the first of `onset_points` consecutive points above the threshold.
3. The onset is then moved back to earlier points as long as each one is lower than the next, but not before `BG End`.

A channel group of another particle than the reference channel (by default, a proton group) with no onset at a resolution and viewing takes the onset of the reference channel at the same resolution and viewing. This is marked in the column `Onset Copied` of `results.csv`.

Then, for each channel group, one onset is chosen. A resolution and viewing is used only if:
- it has an onset;
- the onset is within `reference_onset_window` of the onset of the reference channel (which is chosen first);
- the data from the onset to the end are of good enough quality: the ratio of transitions to zero or NaN values is below `quality_tolerance`, and there are fewer zero or NaN values than valid ones.

The chosen onset is the earliest of the viewings at the finest resolution that can be used. A channel group with no usable resolution and viewing has no onset, peak flux or fluence.

<a id="spikes-step"></a>
### Spikes

In the window from the chosen onset to the end (shortened as described in `peak_window_min`), a point is a spike if it differs from both its neighbours by more than `spike_thresholds` orders of magnitude. Zero and NaN values are left out of the comparison. Before the peak flux and the fluence are calculated, each spike is replaced by the mean of its valid neighbours.

<a id="peak-flux-step"></a>
### Peak flux

The peak flux is the maximum of the flux in the same window as the spikes, without the spikes. The chosen peak flux is the highest of the viewings at the resolution of the chosen onset.

<a id="fluence-step"></a>
### Fluence

For each resolution, in the viewing of the chosen peak flux, from the chosen onset to the end:
1. The peak is the point next to the time of the chosen peak flux (the higher of the points just before and after it). The threshold is `fluence_peak_fraction` of its flux.
2. The interval starts at the last of `fluence_points` consecutive points at or below the threshold before the peak (or at a single such point, if there are none), and not before the onset.
3. It ends at the first of `fluence_points` consecutive points at or below the threshold after the peak (or at a single such point), or at the end of the window.
4. The fluence is the integral of the flux over the interval (trapezoidal rule, over time in seconds), without the spikes and the missing values.

The chosen fluence is the largest of the resolutions whose interval does not start before the onset.

<a id="events-step"></a>
### Events

The event viewer shows the [plot](#plots) of the event chosen in the dropdown, and its rows of [results.csv](#resultscsv). The Previous and Next buttons go through the events. The checkbox limits the list to the events with a channel group whose onset is copied from the reference channel or at the end of the background window, to check them.

## Results

The results step writes `results.csv` to the results folder (`dir_outputs`), and the plots to the plots folder (`dir_plots`) if "Save the plots of the events" is on.

### results.csv

The chosen results, one row per event and channel group, in the order of the event list and of `group_options`:

```
Event No,Particle,Sensor,Energy Label,Low Energy,High Energy,Onset Time,Onset Resolution,Onset Viewing,...
20,electrons,HET,1 MeV,0.4533,2.401,2021-11-01 01:50:00,2.0,north,...
```

| Column | Description |
|---|---|
| `Event No` | Event number of the event list |
| `Particle`, `Sensor` | Particle (`electrons` or `protons`) and sensor of the channel group |
| `Energy Label` | Name of the channel group in `group_options` |
| `Low Energy`, `High Energy` | Energy range of the channel group: the low energy of its first channel and the high energy of its last channel |
| `Onset Time` | Chosen onset |
| `Onset Resolution`, `Onset Viewing` | Resolution and viewing of the onset |
| `Onset Copied` | `True` if the onset is the one of the reference channel (see [Onset](#onset-step)) |
| `Onset at BG End` | `True` if the onset is at the end of the background window: the rise may have started earlier |
| `Peak Flux` | Chosen peak flux |
| `Peak Flux Time` | Time of the peak flux |
| `Peak Flux Resolution`, `Peak Flux Viewing` | Resolution and viewing of the peak flux |
| `Fluence` | Chosen fluence |
| `Fluence Start`, `Fluence End` | Interval of the fluence |
| `Fluence Threshold` | Flux threshold that bounds the interval |
| `Fluence Resolution`, `Fluence Viewing` | Resolution and viewing of the fluence |

Empty cells mean that the channel group has no onset, peak flux or fluence for that event.

The same results are `tool.df_results`, and the results of every resolution and viewing are `tool.df_series` (see the [library guide](library.md#results)). The file can be read with one row per event with pandas:

```python
results = pd.read_csv("outputs/results.csv")
wide = results.set_index(["Event No", "Particle", "Sensor", "Energy Label"]).unstack(["Particle", "Sensor", "Energy Label"])
```

### Units

| Quantity | Unit |
|---|---|
| Flux, peak flux, background level, thresholds | particles / (cm² s sr MeV) |
| Fluence | particles / (cm² sr MeV) |
| Times | UTC |
| Energies | MeV |
| Resolutions in `results.csv` | minutes |

## Plots

Each plot, `event_<number>.png`, has one panel per channel group. The title gives the group, the particle and sensor, and the viewing and resolution of the onset. Each panel shows:

| Element | Meaning |
|---|---|
| Orange line | Flux at the resolution and viewing of the onset |
| Orange dashed line | Flux at the resolution and viewing of the peak flux, if they are different |
| Brown dotted line | Flux at the resolution of the fluence, if it is different from the one of the peak flux |
| Green area | Background window |
| Blue dashed line | Background level |
| Red dashed line | Onset threshold |
| Green line and label | Onset time; the label notes "from 1 MeV electrons" for an onset copied from the reference channel, and "at BG end" for an onset at the end of the background window |
| Grey area | Event range, from the onset to the end (or the first shock after the onset) |
| Red point and label | Peak flux, with its time, viewing and resolution |
| Purple dashed lines | `fluence_peak_fraction` of the peak flux, and the fluence threshold |
| Brown area and label | Fluence interval, with the fluence, its viewing and resolution |
| Purple dotted lines | Interplanetary shocks |
| Text at the bottom right | Quality of the onset data: the ratio of transitions to zero or NaN values, and the numbers of zero and valid values |

A red title marks a channel group:
- without an onset: the panel then shows the flux in `fallback_viewing` at the coarsest resolution, with the background window and the event range;
- with an onset at the end of the background window.
