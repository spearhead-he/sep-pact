# SEP-PACT user guide

- [Overview](#overview)
- [Parameters](#parameters)
  - [Files and folders](#files-and-folders)
  - [Event windows](#event-windows)
  - [Data](#data)
  - [Onset](#onset)
  - [Data quality](#data-quality)
  - [Spikes, peak and fluence](#spikes-peak-and-fluence)
  - [Plot parameters](#plot-parameters)
- [Input files](#input-files)
  - [Event list](#event-list)
  - [Shock list](#shock-list)
- [Steps of the notebook](#steps-of-the-notebook)
  - [Data](#data-step)
  - [Onset](#onset-step)
  - [Spikes](#spikes-step)
  - [Peak flux](#peak-flux-step)
  - [Fluence](#fluence-step)
- [Results](#results)
  - [results.csv](#resultscsv)
  - [Units](#units)
- [Plots](#plots)

## Overview

SEP-PACT analyses the events of an event list with the data of Solar Orbiter EPD/HET (level 2). For each event and energy channel group, it calculates the onset time, the peak flux and the fluence at every resolution and viewing, and chooses one result of each.

The notebook `sep-pact.ipynb` runs the whole analysis. Set the parameters in its parameters cell, then run all the cells in order. The plots are written to `plots/`, and the result tables to `outputs/`.

## Parameters

All the parameters are in the parameters cell at the top of the notebook, as the arguments of `SEPPACT_parameters`. A parameter left out keeps its default; the defaults are listed below. An unknown parameter name or an invalid value raises an error that names the valid choices.

### Files and folders

| Parameter | Default | Description |
|---|---|---|
| `dir_data` | `"data"` | Folder of the downloaded EPD files |
| `dir_saves` | `"intermediate_states"` | Folder of the cached flux |
| `dir_plots` | `"plots"` | Folder of the plots, one per event |
| `dir_outputs` | `"outputs"` | Folder of the result tables |
| `file_events` | `"inputs/events_example.csv"` | Path of the [event list](#event-list) |
| `file_shocks` | `"inputs/shocks.dat"` | Path of the [shock list](#shock-list) |

### Event windows

These are used where the event list leaves the background window or the end time empty.

| Parameter | Default | Description |
|---|---|---|
| `bg_start_before_onset` | 2 h | Start of the background window, before the onset of the event list |
| `bg_end_before_onset` | 5 min | End of the background window, before the onset of the event list |
| `end_after_onset` | 48 h | End of the event, after the onset of the event list |
| `min_plot_window` | 2 days | Minimum length of the data period (background start to end); shorter events are extended equally on both sides |

### Data

| Parameter | Default | Description |
|---|---|---|
| `level` | `"l2"` | EPD data level |
| `viewings` | `["sun", "asun", "north", "south"]` | HET viewing directions |
| `resample_freqs` | 2, 5, 10, 30 min | Resolutions, in ascending order |
| `group_options` | see below | Energy channel groups |
| `download_tries` | 2 | Tries of each download; the tries after the first load only the background start to the end time |

`group_options` has one entry per particle (`"electrons"`, `"protons"`) and, in it, one entry per channel group. The name of a group is its label in the plots and tables. Each group has the sensor (`"HET"`) and the HET channel numbers it combines. The flux of a group is the mean of its channels weighted by their energy widths. One group may be marked as the reference channel with `"reference_channel": True` (see [Onset](#onset-step)).

The default groups are:

| Particle | Group | HET channels |
|---|---|---|
| electrons | `1 MeV` (reference channel) | 0, 1 |
| electrons | `5.9930 - 18.8300 MeV` | 3 |
| protons | `8 MeV` | 1, 2, 3 |
| protons | `25 MeV` | 18, 19 |
| protons | `50 MeV` | 27 |

### Onset

| Parameter | Default | Description |
|---|---|---|
| `onset_sigma` | 2 | Threshold = background mean + `onset_sigma` × background standard deviation |
| `onset_points` | 3 | Consecutive points above the threshold that make an onset |
| `reference_onset_window` | 2.5 h | Onsets further than this from the onset of the reference channel are ignored |

### Data quality

| Parameter | Default | Description |
|---|---|---|
| `quality_tolerance` | 0.1 | Allowed ratio of transitions from valid to zero or NaN values after the onset, to the number of points |
| `quality_adjustable` | `False` | If `True`, the tolerance grows with the resolution: it is multiplied by 1 + resolution / 60 min |

### Spikes, peak and fluence

| Parameter | Default | Description |
|---|---|---|
| `spike_thresholds` | 2.0 (2 and 5 min), 2.5 (10 min), 3.0 (30 min) | Smallest difference, in orders of magnitude, of a spike from both its neighbours, per resolution. Each resolution of `resample_freqs` needs a threshold. |
| `peak_window_min` | 10 h | Spikes and peaks are searched in the first half of the onset to the end, if that half is at least this long |
| `fluence_peak_fraction` | 0.5 | The fluence interval is bounded where the flux falls below this fraction of the peak flux |
| `fluence_points` | 2 | Consecutive points below that threshold that bound the fluence interval |

### Plot parameters

| Parameter | Default | Description |
|---|---|---|
| `fallback_viewing` | `"sun"` | Viewing shown, at the coarsest resolution, for a channel group without an onset |

## Input files

### Event list

A CSV file, given by its path in `file_events`, with one row per event (see `inputs/events_example.csv`):

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

Each step is one call of the `SEPPACT` object `tool`, created in the parameters cell:

1. **Setup:** imports the package.
2. **Parameters:** `params = SEPPACT_parameters(...)` and `tool = SEPPACT(params)`; see [Parameters](#parameters).
3. **Inputs:** `tool.run_inputs()` reads the shock list and the event list, and fills in the missing windows.
4. **Data:** `tool.run_data()` downloads, groups and caches the HET data (see [Data](#data-step)), and resamples the flux of each group to every resolution.
5. **Onset:** `tool.run_onsets()`; see [Onset](#onset-step).
6. **Spikes:** `tool.run_spikes()`; see [Spikes](#spikes-step).
7. **Peak flux:** `tool.run_peaks()`; see [Peak flux](#peak-flux-step).
8. **Fluence:** `tool.run_fluences()`; see [Fluence](#fluence-step).
9. **Plots:** `tool.plot_events()` writes one plot per event to `dir_plots` (see [Plots](#plots)).
10. **Results:** `tool.save_results()` writes `results.csv` (see [Results](#results)).

The results stay available as attributes of `tool`: `tool.df_series` has the results of every resolution and viewing, and `tool.df_results` the chosen ones; see the [library guide](library.md#results).

<a id="data-step"></a>
### Data

The data of each event, viewing and sensor are downloaded from the Solar Orbiter Archive with [solo-epd-loader](https://github.com/jgieseler/solo-epd-loader) into `dir_data`, for the period from the background start to the end time, extended to `min_plot_window`. Files already in `dir_data` are not downloaded again. The channels of each group are combined, weighted by their energy widths.

The result is cached in `dir_saves`, in a file named after the level, the viewings, the channel groups and the event windows. Running the notebook again with the same settings loads the cache; changing any of them creates a new cache file.

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

## Results

The results are written to `dir_outputs`.

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
