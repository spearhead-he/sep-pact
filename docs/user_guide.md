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
  - [Background windows of particles and sensors](#bg-windows-of-particles)
  - [Shocks](#shocks)
- [Steps of the notebook](#steps-of-the-notebook)
  - [Data](#data-step)
  - [Event times](#event-times-step)
  - [Analysis](#analysis-step)
  - [Onset](#onset-step)
  - [Spikes](#spikes-step)
  - [Peak flux](#peak-flux-step)
  - [Fluence](#fluence-step)
  - [Events](#events-step)
  - [Onset corrections](#onset-corrections)
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
| Event list | `file_events` | `inputs/events_example.csv` | Path of the [event list](#event-list). Below the path, the number of events, the layout of the list, the range of the events and the column separator if it is not a comma, or why the file cannot be read. Leave it blank to use the date ranges |
| Date ranges | `date_ranges` | none | The start and end of each event, used without an event list; "Add event" and "Remove event" add and remove events |
| Shock list online | `shock_source` | SODA | The [shock list online](#shocks): SODA, IRFU or None; below it, its number of shocks and their range |
| Shock list file | `file_shocks` | none | Path of a [shock list file](#shocks), with its number of shocks and their range. Leave it blank for none |
| Custom shocks | `shock_times` | none | Shock times of your own; "Add shock" and "Remove shock" add and remove them |
| Shocks during the events | `removed_shocks` | none | The shocks within the data of the events, with their source; "Remove selected" leaves the selected ones out, and "Restore all" uses all of them again. Below the list, the number of removed shocks and the [warnings](#shocks) |
| Data start before the Reference Time (hours) | `start_before_reference` | 2 h | For event lists with a Reference Time: the Start Time of each event |
| Data end after the Reference Time (hours) | `end_after_reference` | 48 h | For event lists with a Reference Time: the End Time of each event |
| Default background start after the Start Time (minutes) | `bg_start_after_start` | 0 | Start of the background window of the events without one |
| Default background end after the Start Time (minutes) | `bg_end_after_start` | 115 min | End of the background window of the events without one |
| Shortest data period (days) | `min_plot_window` | 2 days | Minimum length of the data period (Start Time to End Time); shorter events are extended equally on both sides, so that the peak flux and the fluence can be measured over the rest of the event |

With the defaults, an event with a Reference Time has data from 2 hours before to 48 hours after it, and a background window from 2 hours to 5 minutes before it.

### Data tab

| Field | Parameter | Default | Description |
|---|---|---|---|
| Viewings | `viewings` | sun, asun, north, south | HET viewing directions |
| Resolutions | `resample_freqs` | 2, 5, 10, 30 min | Resolutions of the analysis, chosen from 1, 2, 5, 10, 15, 30 and 60 min |
| Spike threshold | `spike_thresholds` | 2.0 (2 and 5 min), 2.5 (10 min), 3.0 (30 min) | Smallest difference, in orders of magnitude, of a spike from both its neighbours, for each resolution |
| Data folder | `dir_data` | `data` | Folder of the downloaded EPD files |
| Download tries | `download_tries` | 2 | Tries of each download; the tries after the first load only the background start to the end time |
| Cache the flux of the channel groups (Advanced) | `cache_data` | off | Keeps the flux of each event in the cache folder (see [Data](#data-step)). With 10 events or more, a note recommends it |
| Cache folder (Advanced) | `dir_saves` | `intermediate_states` | Folder of the cache |

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
| Corrections file | `file_corrections` | none | Path of the [onset corrections](#onset-corrections) saved in the Events step, applied after the automatic choice of the onsets. Below the path, the number of corrections, or why the file cannot be read. Leave it blank for none |

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
| Height of the panel of each channel group (inches) | `panel_height` | 2.5 | From 1 to 10 inches. The plots are 15 inches wide, and as high as the panels plus 1.5 inches for the title, legend and axis labels; the note below the field gives the size of the plots with the channel groups of the form. 2 to 4 inches is recommended: below 2 the labels in a panel overlap, and above 4 the plots of several channel groups are hard to view on a screen |
| Save the plots of the events | | on | Whether the results step also writes the plots (see [Results](#results)) |
| Plots folder | `dir_plots` | `plots` | Folder of the plots, one per event |
| Results folder | `dir_outputs` | `outputs` | Folder of `results.csv` |

### Parameters in scripts

In scripts, the parameters are the arguments of `SEPPACT_parameters`; see the [library guide](library.md#parameters). The durations are `datetime.timedelta`, e.g. `timedelta(hours=2)`. An unknown parameter name or an invalid value raises an error that names the valid choices.

## Input files

### Event list

A CSV file, given by its path in the form, with one row per event, and optionally rows with the [background windows of particles and sensors](#bg-windows-of-particles). The first column is the event number (`Event No`), used in the tables and the plot names. The other columns are one of these layouts, the same as in the SPEARHEAD VDA tool:

| Layout | Columns after `Event No` | Example in `inputs/` |
|---|---|---|
| Reference times | `Reference Time` | `reference_times_example.csv` |
| Datetime ranges | `Start Time`, `End Time` | `datetime_range_only_example.csv` |
| Datetime ranges with the background end | `Start Time`, `BG End`, `End Time` | `datetime_range_example.csv` |
| Datetime ranges with the background window | `Start Time`, `BG Start`, `BG End`, `End Time` | `events_example.csv` |

```
Event No,Start Time,BG Start,BG End,End Time
20,2021-10-31 19:00:00,2021-10-31 19:00:00,2021-11-01 01:30:00,2021-11-03 02:05:00
```

- `Start Time` and `End Time`: the data range of the event. With a `Reference Time` (an approximate time of the event, e.g. its onset or a flare), they are `start_before_reference` before and `end_after_reference` after it.
- `BG Start` and `BG End`: the background window. Without them, or with empty cells, the window is the default one, `bg_start_after_start` to `bg_end_after_start` after the Start Time. With only `BG End`, the window starts at the Start Time.
- The times of each event must be in the order Start Time ≤ BG Start < BG End < End Time; an event list with an event out of order is not read, and the error names the event.
- The data range is extended to `min_plot_window` if it is shorter; the onset itself is always detected in the data, at or after `BG End` (see [Onset](#onset-step)).
- An event can have more than one row: each time is the last one given in its rows (see [below](#bg-windows-of-particles)).

The times are in UTC, as `YYYY-MM-DD HH:MM:SS` or `YYYY-MM-DD HH:MM` (ISO 8601). A time in another format, e.g. `01/11/2021 10:00`, is an error that gives its line and column; formats like this one are not guessed, because the order of the day and month depends on the country. Spreadsheet programs can change the format of the times when they save a CSV file: set the format of the time cells to `YYYY-MM-DD HH:MM:SS` before saving.

The columns may be in any order, and spaces after the separators are allowed. The column separator is a comma, a semicolon or a tab: the one that splits the header line into the most columns. A separator other than a comma is shown in the summary of the event list in the form and in a message of the data step, so that a wrong detection can be seen. Files saved by Excel as "CSV UTF-8" are read too.

Without an event list, the events are the date ranges of the form (`date_ranges`), with the default background window.

The [Event times](#event-times-step) step can save the event list with the background windows and end times set in it, in the layout with the background window and with the rows of the windows of particles and sensors; give it as the event list of a later run to use the same times.

Event lists with an `Onset Time`, as in earlier versions, are not accepted. To convert one, with the windows it had (empty cells were 2 hours and 5 minutes before the onset, and 48 hours after it):

```python
from datetime import timedelta
import pandas as pd

old = pd.read_csv("my_events.csv", index_col=0).apply(pd.to_datetime, format="ISO8601")
onset = old["Onset Time"]
bg_start = old.get("BG Start", pd.Series(pd.NaT, index=old.index)).fillna(onset - timedelta(hours=2))
new = pd.DataFrame({"Start Time": bg_start, "BG Start": bg_start,
                    "BG End": old.get("BG End", pd.Series(pd.NaT, index=old.index)).fillna(onset - timedelta(minutes=5)),
                    "End Time": old.get("End Time", pd.Series(pd.NaT, index=old.index)).fillna(onset + timedelta(hours=48))})
new.to_csv("my_events_new.csv", date_format="%Y-%m-%d %H:%M:%S")
```

Event lists in Excel (`.xlsx`), as in version 0.1.0, are no longer accepted. To convert one, save it as CSV in Excel or a spreadsheet program, or with pandas:

```python
import pandas as pd
pd.read_excel("my_events.xlsx", index_col=0).to_csv("my_events.csv", date_format="%Y-%m-%d %H:%M:%S")
```

<a id="bg-windows-of-particles"></a>
### Background windows of particles and sensors

Electrons and protons, or two sensors, can start to rise at different times, so that one background window does not fit all of them. With the optional columns `Particle` and `Sensor`, an event list can give the background window of a particle, or of a particle and sensor, in its own rows:

```
Event No,Particle,Sensor,Start Time,BG Start,BG End,End Time
1,,,2021-10-31 19:00,2021-10-31 19:00,2021-11-01 01:30,2021-11-03 02:05
1,protons,HET,,2021-11-01 00:00,2021-11-01 02:30,
2,,,2022-03-28 10:00,,2022-03-28 11:00,2022-03-29 10:00
```

- A row with empty `Particle` and `Sensor` is a row of the event: its `BG Start` and `BG End` are the background window of the event.
- A row with a `Particle` and a `Sensor` gives, in `BG Start` and `BG End`, the window of the channel groups of that particle and sensor in the event. A row with only the `Particle` gives the window of all its sensors. A `Sensor` without a `Particle` is not accepted.
- The channel groups use the window of their particle and sensor, else the one of their particle, else the one of the event, and else the default one. In the example, the proton channel groups of event 1 use the window from 00:00 to 02:30, and the electrons the window of the event.
- The row of a particle needs a `BG End`; without a `BG Start`, its window starts at the Start Time. Its window must be in the order Start Time ≤ BG Start < BG End < End Time of the event.
- The particles are `electrons` and `protons`, and the sensor `HET`; the case does not matter.
- The times of the event (`Start Time`, `End Time`, `Reference Time`) can be in any of its rows, and the event does not need a row of its own: without one, it has the default window. When a time is given in more than one row of an event with different values, the last one is used, and a message names the rows; the same applies to the window of the same particle and sensor.

Event lists without the columns `Particle` and `Sensor` keep one window per event, as before.

### Shocks

The analysis of a channel group ends at the first interplanetary shock after its onset, if that is before `End Time`: its data quality check, spikes, peak flux and fluence. The shocks are those of three sources, concatenated and sorted by time:

- **Shock list online** (`shock_source`): downloaded each time it is selected and in the data step; it is not stored. The Solar Orbiter shocks of:
  - [SODA](https://parker.gsfc.nasa.gov/shocks.html) (default): the ShOck Detection Algorithm list of the NASA Parker Solar Probe science site, from 2020-10-14 to 2025-02-28 at the time of writing (171 shocks);
  - [IRFU](https://doi.org/10.5281/zenodo.11091062): the Solar Orbiter IRFU shock list by A. P. Dimmock, in its latest version on Zenodo, from 2020-04-19 to 2024-03-01 (103 shocks);
  - None.

  If the list cannot be downloaded, a warning is shown and the analysis goes on with the other sources.
- **Shock list file** (`file_shocks`), in one of these formats:
  - an [ipshocks](https://ipshocks.helsinki.fi/) list: lines starting with `#` are comments, and the first six columns, separated by `;`, are the year, month, day, hour, minute and second of the shock;
  - the IRFU list (`.txt`), as downloaded from Zenodo;
  - a CSV file with the column `Shock Time` (`YYYY-MM-DD HH:MM:SS`, UTC), separated by commas, semicolons or tabs as the [event list](#event-list).

  `inputs/` has an example of each format, with shocks around the example event: `shocks_ipshocks_example.dat`, `shocks_irfu_example.txt` and `shocks_example.csv`:

  ```
  # Shocks at Solar Orbiter around the example event (UTC); one time per row, in the column Shock Time
  Shock Time
  2021-10-30 22:02:09
  2021-11-03 14:04:26
  ```
- **Custom shocks** (`shock_times`): shock times added in the form.

A shock found by two sources is listed twice, which does not change the analysis. Shocks can be left out with "Remove selected" in the list of the shocks during the events (`removed_shocks`), e.g. a shock that is not one, or one of the same shock from two sources.

The form and the data step warn:
- when there are no shocks: the analysis then goes on to the end time of each event;
- when there are only custom shocks;
- about the events that are not within the shock lists (from the first to the last shock of the shock list online and the file): the shocks during them may be missing. With SODA, these are the events before 2020-10-14 or after 2025-02-28.

The shock lists are automated or semi-automated and can miss or misidentify shocks; check the shocks in the plots of the events.

## Steps of the notebook

1. **Setup:** imports the package and creates the interface, `tool = SEPPACT_notebook()`.
2. **Parameters:** `tool.parameters_form()`; see [Parameters](#parameters).
3. **Data:** `tool.run_data()` reads the event list and the shocks, fills in the missing windows, and downloads the data (see [Data](#data-step)). It shows the event list with its windows.
4. **Event times:** `tool.event_times()` shows the background windows and the end time of each event, which can be changed, also for a particle and sensor (see [Event times](#event-times-step)).
5. **Analysis:** `tool.run_analysis()` runs the onset, spikes, peak flux and fluence steps (see [Analysis](#analysis-step)).
6. **Events:** `tool.event_viewer()` shows the plot and the results of each event, and the onset of each channel group can be corrected (see [Events](#events-step) and [Onset corrections](#onset-corrections)).
7. **Results:** `tool.save_results()` writes `results.csv` and, if "Save the plots of the events" is on, the plots (see [Results](#results)).

The analysis uses the parameters of the form when the data step runs; after a change in the form, run the steps again from the data step. After a change of the event times, run the analysis step again. The results stay available as attributes of `tool`: `tool.df_series` has the results of every resolution and viewing, and `tool.df_results` the chosen ones; see the [library guide](library.md#results).

<a id="data-step"></a>
### Data

The data of each event, viewing and sensor are downloaded from the Solar Orbiter Archive with [solo-epd-loader](https://github.com/jgieseler/solo-epd-loader) into `dir_data`, for the period from the background start to the end time, extended to `min_plot_window`. Files already in `dir_data` are not downloaded again. The channels of each group are combined, weighted by their energy widths.

The step shows the progress of each event. An event whose data cannot be loaded, after `download_tries` tries, is left out with its error, e.g. when the data server is unavailable or there are no data for its period, and the other events go on. At the end, the step lists the events left out; they are not analysed, and running the data step again tries them again. The [event list saved](#event-times-step) in the event times step keeps them. If no event can be loaded, the step stops with the error.

**Cache** (`cache_data`, off by default; Advanced section of the Data tab): for event lists of many events. The flux of the channel groups of each event is kept in `flux_cache.pkl` in `dir_saves`, one entry per event, for its times, the level, the viewings and the channel groups. The file is saved every 10 newly loaded events, at the end, and when the data step stops (an error, or the stop button), so that the events already loaded are kept. Later runs load the events from the cache, and only the new or changed events from the data files. The file keeps the entries of events that are no longer used; delete it to clear the cache. Without the cache, every run loads the events from the data files in `dir_data`, which are downloaded only once.

<a id="event-times-step"></a>
### Event times

Shows the background windows and the end time of the event chosen in the dropdown, with a plot of the flux of all its channel groups (one panel per particle and sensor, at the finest resolution, in the first viewing), the background window of each panel shaded and the start and end times dotted. The title of a panel with a [window of its own](#bg-windows-of-particles) gives the window.

- **Window of:** the window that the slider sets: the one of the event, or of a particle and sensor (e.g. `protons HET`), which the channel groups of that particle and sensor use instead of the window of the event. A particle and sensor without a window of its own shows the window of the event until the slider is moved.
- **Background:** a range slider over the data points from the Start Time to the End Time; move its ends to set the chosen window (`BG Start`, `BG End`).
- **End time:** a slider over the data points from after the background windows of the event to the end of the loaded data; move it to set the `End Time`. To extend an event beyond its data, change the event list and run the data step again. The slider starts at the closest data point at or before the end time, which is not changed until the slider is moved.
- **Reset:** gives back the chosen window of the event list, or else the default one for the event, or the window of the event for a particle and sensor. For the event, it also gives back the end time.
- **Status:** the window of the event and the windows of particles and sensors, where they come from (`event list`, `default` or `set`), the number of points with data in each window at each resolution (the fewest among the series that use it), and the end time and where it comes from. A window with fewer than 3 points at a resolution is shown with a warning in red: its standard deviation, and so the threshold, is not reliable, and with 1 point there is no onset at that resolution. The checkbox limits the list to the events with warnings.
- **Save:** writes the event list with the times of all the events and the windows of particles and sensors (by default `outputs/events.csv`), which can be given as the [event list](#event-list) of a later run.

A changed end time also changes where the onsets are searched, the data quality check, the window of the spikes and peak, and the fluence interval. Run the analysis step after the changes; the status line reminds of it when the analysis has already run.

<a id="analysis-step"></a>
### Analysis

The analysis step shows its progress through the onset, spikes, peak flux and fluence steps below, then how many channel groups have an onset, how many of these are copied from the reference channel, and how many are at the end of the background window.

<a id="onset-step"></a>
### Onset

For each event, channel group, resolution and viewing:
1. The background level and standard deviation are calculated from `BG Start` to `BG End` of the background window of the channel group: the window of its particle and sensor, of its particle, or of the event (see [Background windows of particles and sensors](#bg-windows-of-particles)). The threshold is the level plus `onset_sigma` standard deviations.
2. From `BG End` to `End Time`, the onset is the first of `onset_points` consecutive points above the threshold.
3. The onset is then moved back to earlier points as long as each one is lower than the next, but not before `BG End`.

<a id="onset-at-bg-end"></a>
The onset is never before `BG End`. When the flux already rises inside the background window, the onset is at `BG End`, marked in the column `Onset at BG End` of `results.csv` and by an orange panel title: the event may have started earlier, and its background level and threshold include part of the rise. Choosing background windows that end before the rise is up to the user: change them in the [Event times](#event-times-step) step, for the event or for a particle and sensor, or in the [event list](#event-list).

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

The event viewer shows the [plot](#plots) of the event chosen in the dropdown, and its rows of [results.csv](#resultscsv). The Previous and Next buttons go through the events. The checkbox limits the list to the events with a channel group whose onset is copied from the reference channel or at the end of the background window, to check them. A note below the onset choice explains the colours of the panel titles.

### Onset corrections

Below the event, the onset of each channel group can be set by hand:
- **Channel group:** the channel groups of the event.
- **Onset:** "No onset", or one of the onsets detected in the series of the group, labelled with their time, resolution and viewing, and "(not usable)" or "(copied)" when they apply. It shows the chosen onset.
- **Reset to automatic:** gives back the automatically chosen onset.

After a change, the spikes, peak flux and fluence of the event are calculated again, and its plot and results are redrawn; a note with an hourglass is shown meanwhile. A corrected panel has "(corrected)" at the end of its title, and the column `Onset Corrected` of `results.csv` is `True`. A corrected reference channel changes the onsets chosen for the other channel groups of its event, except the corrected ones.

The corrections stay when the analysis step runs again, e.g. after a change of the event times. **Save**, below the results of the event, writes them (by default `outputs/corrections.csv`): one row per corrected channel group, with `Event No`, `Particle`, `Sensor`, `Energy Label`, `Onset Resolution` (minutes), `Onset Viewing` and `Onset Time`, the last three empty for no onset. Give the file as the corrections file (`file_corrections`, in the [Onsets tab](#onsets-tab)) to apply them in a later run: a correction whose series has no onset any more, e.g. after a change of the parameters, is left out with a message, and a note is given when the onset of its series has changed.

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
| `Onset Corrected` | `True` if the onset was set by hand (see [Onset corrections](#onset-corrections)) |
| `BG Start`, `BG End` | Background window of the channel group: the window of its particle and sensor, of its particle, or of the event |
| `BG Window Source`, `End Time Source` | Where the background window of the channel group and the end time of the event come from: `event list`, `default`, or `set` in the [Event times](#event-times-step) step |
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

Each plot, `event_<number>.png`, has the title of the event, the legend, and one panel per channel group, `panel_height` inches high. The legend lists only the elements drawn in at least one panel, e.g. Shock Time only when a shock is in the plot, grouped by quantity: the onset, the peak flux, the fluence, and the event. The title of a panel, in its top-right corner, gives the group, the particle and sensor, and the viewing and resolution of the onset. Each panel shows:

| Element | Legend | Meaning |
|---|---|---|
| Orange line | Data (Onset) | Flux at the resolution and viewing of the onset |
| Light orange line | Data (No Onset) | Flux in `fallback_viewing` at the coarsest resolution, of a channel group without an onset |
| Green area | BG sample | Background window of the channel group |
| Blue dashed line | BG Level | Background level |
| Red dashed line | nσ Threshold | Onset threshold |
| Green dashed line and label | Onset Time | Onset time; the label notes "from 1 MeV electrons" for an onset copied from the reference channel, and "at BG end" for an onset at the end of the background window |
| Teal dashed line | Data (Peak Flux) | Flux at the resolution and viewing of the peak flux, if they are different from those of the onset |
| Red point and label | Peak Flux | Peak flux, with its time, viewing and resolution |
| Purple dashed line | 0.5 × Peak Flux | `fluence_peak_fraction` of the peak flux |
| Brown dash-dotted line | Data (Fluence) | Flux at the resolution of the fluence, if it is different from the one of the peak flux |
| Brown area and label | Fluence | Fluence interval, with the fluence, its viewing and resolution |
| Purple dotted line | Fluence Threshold | The fluence threshold, at the resolution of the fluence |
| Grey area | Event Range | Event range, from the onset to the end (or the first shock after the onset) |
| Pink lines and labels | Shock Time | Interplanetary shocks, with their times |
| Text in the bottom-right corner | | Quality of the onset data: the ratio of transitions to zero or NaN values, and the numbers of zero and valid values |

The colour of a panel title marks a channel group:
- red, without an onset: the panel then shows the flux in `fallback_viewing` at the coarsest resolution, with the background window and the event range;
- orange, with its onset at the end of the background window, where the event may have started earlier.

"(corrected)" at the end of a panel title marks an onset set by hand (see [Onset corrections](#onset-corrections)).

The shaded areas are drawn behind the flux, and the flux of the onset over those of the peak flux and the fluence. The horizontal lines (levels and thresholds) are drawn over the flux, the vertical lines (onset and shocks) over them, and the labels on top.
