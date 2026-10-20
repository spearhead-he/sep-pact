# Changelog

All notable changes of SEP-PACT. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Form at the top of `sep-pact.ipynb` (`SEPPACT_notebook`), with all the parameters in tabs: the paths of the event list and the shock list with a summary of each, the event windows, the viewings, the resolutions with their spike thresholds, an editor of the energy channel groups with the energies of the channels, and the onset, data quality, peak flux, fluence and plot parameters. Values that are not accepted are shown in the form. See [Parameters](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#parameters).
- Event viewer in the notebook: the plot and the results of each event, with a filter for the events with copied onsets or onsets at the end of the background window. See [Events](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#events-step).
- Channel groups per particle and sensor (`group_options`), with an optional reference channel, and a 5.99-18.83 MeV electron group.
- Choice of the resolution and viewing of each channel group, with a data quality check after the onset (`quality_tolerance`).
- Onsets limited to a window around the onset of the reference channel (`reference_onset_window`); channel groups without an onset take the one of the reference channel.
- Spike removal before the peak flux and the fluence (`spike_thresholds`).
- `outputs/results.csv`, with the chosen onset, peak flux and fluence of each event and channel group, the energy range of the group, and the flags `Onset Copied` and `Onset at BG End`. See [results.csv](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#resultscsv).
- Package `spearhead-sep-pact` (`spearhead.sep_pact`), with the code of the analysis: `SEPPACT_parameters`, the parameters, and `SEPPACT`, which runs the steps and keeps their results in tables with one row per series (`df_series`) and per event and channel group (`df_results`). The notebook has one cell per step, and the package can be used in scripts; see the [library guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/library.md).
- [User guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md), [library guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/library.md), [development guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/development.md) and this changelog.
- Tests of every part of the package, with synthetic data, and an end-to-end test of the example event; continuous integration with Python 3.11 to 3.14.

### Changed

- The event list is a CSV file (`inputs/events_example.csv`) instead of an Excel file; Excel event lists are no longer accepted. See [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list).
- The event list has the layouts of the SPEARHEAD VDA tool: `Reference Time`, or `Start Time` and `End Time` with optionally `BG End` or `BG Start` and `BG End`, with one example of each in `inputs/`. Without an event list, the events are date ranges set in the form (`date_ranges`). The data of events with a Reference Time start `start_before_reference` before it and end `end_after_reference` after it, and the default background window is `bg_start_after_start` to `bg_end_after_start` after the Start Time; the defaults give the windows of the former Onset Time. The times of each event are checked to be in order. See [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list).
- The analysis of a channel group ends at the first shock after its onset, instead of the event end being moved to the first shock after the background.
- The flux is downloaded per event, viewing and sensor, combined into channel groups before resampling, and cached in `intermediate_states/` in a file named after the settings. The previous cache files are not used.
- The plots show the flux at the resolution and viewing of the onset, and of the peak flux and the fluence when they differ, the event range, and notes on copied onsets and onsets at the end of the background window. The legend is between the title and the first panel and lists only the elements drawn in the plot, and plots with few channel groups have room for their title, legend and axis labels. The height of the panels can be set (`panel_height`).
- Python 3.11 or newer is required.
- The data step says whether the flux is loaded from the cache or from the data files, and how many files are downloaded for each event; files already in the data folder are not downloaded again.

### Fixed

- Plots of channel groups with an onset but without a peak flux or a fluence.
- The cache folder `intermediate_states/` is created if it does not exist.

### Upgrading from 0.1.0

- Use Python 3.11 or newer, and reinstall the requirements: `pip install -r requirements.txt`, which now installs the package with its notebook dependencies (new: `ipywidgets`, the `timeseries` and `visualization` extras of sunpy, solo-epd-loader 0.4.4).
- Save the event list as CSV, e.g. in Excel or with `pd.read_excel("my_events.xlsx", index_col=0).to_csv("my_events.csv", date_format="%Y-%m-%d %H:%M:%S")`; see [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list).
- Convert event lists with an `Onset Time` to the layout `Start Time`, `BG Start`, `BG End`, `End Time`, with the snippet of [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list); the windows, and the results, stay the same. The parameters `bg_start_before_onset`, `bg_end_before_onset` and `end_after_onset` are replaced by `start_before_reference`, `end_after_reference`, `bg_start_after_start` and `bg_end_after_start`.
- Set the path of the event list and the other settings in the form of the notebook. The results are written to `outputs/`.
- The cache files of 0.1.0 in `intermediate_states/` (`protons_*.pkl`, `electrons_*.pkl`, `data_*.pkl`, `resampled_data_*.pkl`) are not used and can be deleted.
- The results change: the onset, peak flux and fluence are now chosen per channel group from all resolutions and viewings, with the data quality check, the reference channel, the spike removal and the end at the first shock after the onset.

## [0.1.0] - 2026-05-13

First release: onset time, peak flux and fluence of electrons and protons in Solar Orbiter EPD/HET data, at several resolutions and viewings, with one plot per event.

[Unreleased]: https://github.com/spearhead-he/sep-pact/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/spearhead-he/sep-pact/releases/tag/v0.1.0
