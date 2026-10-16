"""End-to-end test: the example event list, from the download of the data to the results and the plot"""
from datetime import timedelta

import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT, SEPPACT_parameters
from spearhead.sep_pact.views import plot_event

# known results of event 20 of inputs/example.xlsx: onset, its resolution (minutes) and viewing, the onset flags,
# the peak flux and its time, and the fluence and its resolution (minutes)
EXPECTED = {
    ("electrons", "1 MeV"): ("2021-11-01 01:50", 2, "north", False, False, 72.64031219482422, "2021-11-01 02:58", 312964, 30),
    ("electrons", "5.9930 - 18.8300 MeV"): ("2021-11-01 02:40", 5, "sun", False, False, 0.02491745166480541,
                                            "2021-11-01 05:00", 205, 30),
    ("protons", "8 MeV"): ("2021-11-01 02:50", 2, "sun", False, False, 27.10921478271484, "2021-11-01 04:12", 250838, 30),
    ("protons", "25 MeV"): ("2021-11-01 02:46", 2, "sun", False, False, 0.5183103680610657, "2021-11-01 04:06", 3021, 10),
    ("protons", "50 MeV"): ("2021-11-01 01:30", 30, "south", False, True, 0.02269012108445168, "2021-11-01 04:00", 189, 30),
}


@pytest.fixture(scope="module")
def tool(tmp_path_factory):
    folder = tmp_path_factory.mktemp("end_to_end")
    params = SEPPACT_parameters(dir_saves=str(folder / "cache"), dir_plots=str(folder / "plots"),
                                dir_outputs=str(folder / "outputs"))
    tool = SEPPACT(params)
    tool.run_inputs()
    tool.run_data(redownload=True)
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


@pytest.mark.network
@pytest.mark.parametrize("particle, group", list(EXPECTED))
def test_example_event(tool, particle, group):
    onset, resolution, viewing, copied, at_bg_end, peak, peak_time, fluence, fluence_resolution = EXPECTED[(particle, group)]

    def value(quantity, field):
        return tool.df_optimals.loc[20, (particle, "HET", group, quantity, field)]

    assert value("Onset Time", "Onset Time") == pd.Timestamp(onset)
    assert value("Onset Time", "Resolution") == timedelta(minutes=resolution)
    assert value("Onset Time", "Viewing") == viewing
    assert value("Onset Time", "Onset Copied") == copied
    assert value("Onset Time", "Onset at BG End") == at_bg_end
    assert value("Peak Flux", "Peak Flux") == pytest.approx(peak, rel=1e-6)
    assert value("Peak Flux", "Peak Flux Time") == pd.Timestamp(peak_time)
    assert value("Fluence", "Fluence") == pytest.approx(fluence, abs=1)
    assert value("Fluence", "Resolution") == timedelta(minutes=fluence_resolution)


@pytest.mark.network
@pytest.mark.mpl_image_compare(tolerance=5, style="default")
def test_example_event_plot(tool):
    return plot_event(tool, 20)
