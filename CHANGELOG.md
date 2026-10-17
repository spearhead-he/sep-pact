# Changelog

All notable changes of SEP-PACT. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Parameters cell at the top of `sep-pact.ipynb`, with all the settings: files and folders, event windows, data, onset, data quality, spikes, peak and fluence, and plots. See [Parameters](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#parameters).
- Channel groups per particle and sensor (`group_options`), with an optional reference channel, and a 5.99-18.83 MeV electron group.
- Choice of the resolution and viewing of each channel group, with a data quality check after the onset (`quality_tolerance`).
- Onsets limited to a window around the onset of the reference channel (`reference_onset_window`); channel groups without an onset take the one of the reference channel.
- Spike removal before the peak flux and the fluence (`spike_thresholds`).
- `outputs/optimals.xlsx`, with the chosen onset, peak flux and fluence of each channel group, and the flags "Onset Copied" and "Onset at BG End". See [optimals.xlsx](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#optimalsxlsx).
- Package `spearhead-sep-pact` (`spearhead.sep_pact`), with the code of the analysis: `SEPPACT_parameters`, the parameters, and `SEPPACT`, which runs the steps and keeps their results. The notebook has one cell per step, and the package can be used in scripts; see the [library guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/library.md).
- [User guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md), [library guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/library.md), [development guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/development.md) and this changelog.
- Tests of every part of the package, with synthetic data, and an end-to-end test of the example event; continuous integration with Python 3.11 to 3.14.

### Changed

- The event list is a CSV file (`inputs/events_example.csv`) instead of an Excel file; Excel event lists are no longer accepted. See [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list).
- The event list may have an `End Time` column; `BG Start`, `BG End` and `End Time` are optional, with defaults set in the parameters.
- The analysis of a channel group ends at the first shock after its onset, instead of the event end being moved to the first shock after the background.
- The flux is downloaded per event, viewing and sensor, combined into channel groups before resampling, and cached in `intermediate_states/` in a file named after the settings. The previous cache files are not used.
- The plots show the flux at the resolution and viewing of the onset, and of the peak flux and the fluence when they differ, the event range, and notes on copied onsets and onsets at the end of the background window.
- Python 3.11 or newer is required.

### Fixed

- Plots of channel groups with an onset but without a peak flux or a fluence.
- The cache folder `intermediate_states/` is created if it does not exist.

### Upgrading from 0.1.0

- Use Python 3.11 or newer, and reinstall the requirements: `pip install -r requirements.txt`, which now installs the package with its notebook dependencies (new: `openpyxl`, the `timeseries` and `visualization` extras of sunpy, solo-epd-loader 0.4.4).
- Save the event list as CSV, e.g. in Excel or with `pd.read_excel("my_events.xlsx", index_col=0).to_csv("my_events.csv", date_format="%Y-%m-%d %H:%M:%S")`; see [Event list](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#event-list).
- Set the event list and the other settings in the parameters cell, as arguments of `SEPPACT_parameters`. The results are written to `outputs/`.
- The cache files of 0.1.0 in `intermediate_states/` (`protons_*.pkl`, `electrons_*.pkl`, `data_*.pkl`, `resampled_data_*.pkl`) are not used and can be deleted.
- The results change: the onset, peak flux and fluence are now chosen per channel group from all resolutions and viewings, with the data quality check, the reference channel, the spike removal and the end at the first shock after the onset.

## [0.1.0] - 2026-05-13

First release: onset time, peak flux and fluence of electrons and protons in Solar Orbiter EPD/HET data, at several resolutions and viewings, with one plot per event.

[Unreleased]: https://github.com/spearhead-he/sep-pact/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/spearhead-he/sep-pact/releases/tag/v0.1.0
