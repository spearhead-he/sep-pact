"""SEP-PACT: onset time, peak flux and fluence of Solar Energetic Particle events with Solar Orbiter EPD/HET data.

Modules:
- analysis: SEPPACT, which runs the steps of the analysis and keeps their results, and the functions of each step
  (onset detection, data quality, spikes, peak flux, fluence)
- conf: SEPPACT_parameters, the parameters of the analysis
- inputs: reading of the event list, the shock list and the file of onset corrections
- background: BackgroundWindows, the background windows per event, particle and sensor, and the rows of particles and
  sensors in the event list (independent of the rest of the package)
- data: loading of the EPD data, the flux of the channel groups, its cache and resampling
- views: the plots, as matplotlib figures
- notebook: SEPPACT_notebook, the interface of sep-pact.ipynb: the parameters form, the steps, the event times and
  the onset corrections (needs the notebook extra)
"""
from .analysis import SEPPACT
from .conf import SEPPACT_parameters

__version__ = "0.3.0"

__all__ = ["SEPPACT", "SEPPACT_parameters", "__version__"]
