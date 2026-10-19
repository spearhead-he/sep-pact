[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20157436-blue)](https://doi.org/10.5281/zenodo.20157436)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![pytest](https://github.com/spearhead-he/sep-pact/actions/workflows/pytest.yml/badge.svg)](https://github.com/spearhead-he/sep-pact/actions/workflows/pytest.yml)
[![codecov](https://codecov.io/gh/spearhead-he/sep-pact/branch/main/graph/badge.svg)](https://codecov.io/gh/spearhead-he/sep-pact)
[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![website](https://img.shields.io/badge/Project%20Website-blue)](https://spearhead-he.eu)

# SPEARHEAD SEP-PACT tool

- [SPEARHEAD SEP-PACT tool](#spearhead-sep-pact-tool)
  - [About](#about)
  - [How to install](#how-to-install)
  - [How to use](#how-to-use)
  - [Example output](#example-output)
  - [Documentation](#documentation)
  - [Contributing](#contributing)
  - [Acknowledgement](#acknowledgement)

## About

SEP-PACT (Solar Energetic Particle Analysis and Calculation Tool) analyses Solar Energetic Particle (SEP) events automatically, with the data of the High Energy Telescope (HET) of Solar Orbiter's Energetic Particle Detector (EPD). For every event and energy channel group, it computes the onset time, the peak flux and its time, and the fluence of electrons and protons.

Each quantity is calculated at several time resolutions and in the four viewing directions of HET (sun, asun, north, south), and the tool chooses one result per channel group: the onset of the finest resolution with reliable data (the earliest of its viewings), the highest peak flux of the viewings at that resolution, and the largest fluence of the resolutions in the viewing of the peak.

- **Inputs:** an event list (CSV file with the event onsets and, optionally, the background windows and end times) and the list of interplanetary shocks from the [ipshocks database](https://ipshocks.helsinki.fi/), provided in `inputs/shocks.dat`.
- **Outputs:** one plot per event in `plots/`, and the results in `outputs/results.csv`: the chosen onset, peak flux and fluence of each event and channel group.
- **Notebook:** `sep-pact.ipynb`, the whole analysis: a form with all the parameters, then one cell per step, with an event viewer to check the plot and results of each event.
- **Package:** `spearhead.sep_pact`, the code of the analysis, also usable in scripts without the notebook.

Tested in Linux with Python 3.11, 3.12, 3.13 and 3.14.

## How to install

### Access online (JupyterHub)

You can access SEP-PACT online on the JupyterHub server of the SPEARHEAD project. All you need is a (free) [GitHub account](https://github.com/signup) for verification. [Access the tool by opening this link!](https://jupyterhub.spearhead-he.eu/hub/user-redirect/git-pull?repo=https%3A%2F%2Fgithub.com%2Fspearhead-he%2Fsep-pact&urlpath=lab%2Ftree%2Fsep-pact%2Fsep-pact.ipynb&branch=main)

### Install locally

1. Install Python 3.11 or newer, e.g. with [miniforge](https://github.com/conda-forge/miniforge).
2. Clone the repository: `git clone https://github.com/spearhead-he/sep-pact.git`, and open a terminal in the `sep-pact` folder.
3. Create a new virtual environment and activate it, e.g. `python -m venv venv_sep_pact` and `source venv_sep_pact/bin/activate`.
4. Install the package and the notebook dependencies: `pip install -r requirements.txt` (the same as `pip install -e ".[notebook]"`).
5. Open the notebook: `jupyter-lab sep-pact.ipynb`.

## How to use

Open `sep-pact.ipynb` and run its cells in order:

```python
tool = SEPPACT_notebook()
tool.parameters_form()   # all the parameters, in tabs
tool.run_data()          # reads the event list and downloads the data
tool.run_analysis()      # onsets, spikes, peak flux and fluence
tool.event_viewer()      # the plot and results of each event
tool.save_results()      # results.csv and the plots
```

1. In the form, set the path of the event list (by default `inputs/events_example.csv`), the event windows, the viewings, the resolutions, the energy channel groups and the parameters of the onset, peak flux and fluence calculations.
2. Run the steps, and check the events in the event viewer.
3. Find the results in `outputs/results.csv` and the plots in `plots/`.

The data are downloaded into `data/` the first time. The flux of the channel groups is cached in `intermediate_states/`, and loaded from there when the notebook is run again with the same events and data settings.

The [user guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md) describes the parameters, the input files, the steps of the notebook and the results.

## Example output

<img src="https://raw.githubusercontent.com/spearhead-he/sep-pact/main/docs/images/example_event.png" width="800" alt="Plot of the example event">

The plot of the example event (2021-11-01) has one panel per channel group: 1 MeV electrons, 5.99-18.83 MeV electrons, and 8, 25 and 50 MeV protons. Each panel shows the flux at the chosen resolution and viewing, with:
- the background window (green) and level (blue), and the onset threshold (red, dashed);
- the onset time (green line), calculated with the n-sigma method;
- the peak flux (red point);
- the fluence interval (brown), calculated following [Jiggens et al. (2018)](https://doi.org/10.1051/swsc/2018010);
- the interplanetary shocks of the [ipshocks database](https://ipshocks.helsinki.fi/) (purple, dotted).

A red title marks a channel group without an onset, or with an onset at the end of the background window. The [user guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md#plots) explains every element of the plot.

## Documentation

- [User guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/user_guide.md): the parameters, the input files and their formats, the steps of the notebook, and the results and plots.
- [Library guide](https://github.com/spearhead-he/sep-pact/blob/main/docs/library.md): using the package in scripts, its modules and their main functions.
- [Development](https://github.com/spearhead-he/sep-pact/blob/main/docs/development.md): the development installation, the tests and their commands, the baseline images and the continuous integration.
- [Changelog](https://github.com/spearhead-he/sep-pact/blob/main/CHANGELOG.md): the changes of each version.

## Contributing

Contributions to this tool are very much welcome and encouraged! Contributions can take the form of [issues](https://github.com/spearhead-he/sep-pact/issues) to report bugs and request new features or [pull requests](https://github.com/spearhead-he/sep-pact/pulls) to submit new code.

If you don't have a GitHub account, you can [sign-up for free here](https://github.com/signup), or you can also reach out to us with feedback by sending an email to [jan.gieseler@utu.fi](mailto:jan.gieseler@utu.fi).

## Acknowledgement

<img align="right" height="80px" src="https://github.com/user-attachments/assets/28c60e00-85b4-4cf3-a422-6f0524c42234"> 
<a href="https://spearhead-he.eu"><img align="right" height="80px" src="https://github.com/user-attachments/assets/854d45ef-8b25-4a7b-9521-bf8bc364246e"></a>

This tool is developed within the [SPEARHEAD (*SPEcification, Analysis & Re-calibration of High Energy pArticle Data*)](https://spearhead-he.eu/) project. SPEARHEAD has received funding from the European Union’s Horizon Europe programme under grant agreement No 101135044. 

The tool reflects only the authors’ view and the European Commission is not responsible for any use that may be made of the information it contains.
