"""Tests of the data: channel layout, grouping of the channels, the download with its cache, and the resampling"""
import os
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import spearhead.sep_pact.data as data
from spearhead.sep_pact.conf import default_group_options
from spearhead.sep_pact.data import (ParticleData, channel_layout, download_data, flux_cache_file, group_channels_de, load,
                                     load_energies, resample_flux)
from spearhead.sep_pact.inputs import read_events
from tests.helpers import OFFSET, T0, FakeEPD, epd_energies, make_params, profile, write_events


@pytest.fixture
def events(tmp_path):
    params = make_params(tmp_path)
    return read_events(write_events(tmp_path / "inputs", {1: {"Onset Time": T0}}), params)


def test_channel_layout():
    particles, sensors, channels, sensors_all = channel_layout(default_group_options())
    assert particles == ["electrons", "protons"]
    assert sensors == {"electrons": {"HET"}, "protons": {"HET"}}
    assert channels == {"electrons": {"HET": [0, 1, 3]}, "protons": {"HET": [1, 2, 3, 18, 19, 27]}}
    assert sensors_all == {"HET"}


def test_group_channels_weighted_by_energy_width():
    df = pd.DataFrame({"H_Flux_1": [1.0, 2.0], "H_Flux_2": [4.0, 8.0], "H_Flux_3": [5.0, 5.0]})
    grouped = group_channels_de(df, [["H_Flux_1", "H_Flux_2"], ["H_Flux_3"]], [[1.0, 3.0], [0.5]], ["low", "high"])
    assert list(grouped.columns) == ["low", "high"]
    assert grouped["low"].tolist() == pytest.approx([(1 * 1 + 4 * 3) / 4, (2 * 1 + 8 * 3) / 4])
    assert grouped["high"].tolist() == pytest.approx([5.0, 5.0])


def test_load_returns_the_flux_and_energies_of_each_channel(monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD({("protons", "sun"): T0}))
    loaded = load("HET", T0, T0, "sun", "data")
    assert list(loaded) == ["protons", "electrons"]
    protons = loaded["protons"]
    assert isinstance(protons, ParticleData)
    assert list(protons.flux.columns) == list(range(36))  # only the flux, with the channel numbers as columns
    assert list(protons.energies.columns) == ["Low Energy", "Bin Width"]
    assert protons.energies.loc[3, "Bin Width"] == pytest.approx(epd_energies()["H_Bins_Width"][3])
    assert protons.flux[5].max() > 50


def test_load_selected_particles(monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    assert list(load("HET", T0, T0, "sun", "data", particles=["electrons"])) == ["electrons"]


def test_load_ion_columns(monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD(proton_prefix="Ion"))
    protons = load("HET", T0, T0, "sun", "data")["protons"]
    assert list(protons.flux.columns) == list(range(36))
    assert protons.energies.loc[0, "Low Energy"] == pytest.approx(epd_energies("Ion")["Ion_Bins_Low_Energy"][0])


def test_load_energies(monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    energies = load_energies({"HET"}, "l2", T0, T0, "sun", "data")
    assert list(energies) == ["HET"] and list(energies["HET"]) == ["protons", "electrons"]
    assert energies["HET"]["electrons"]["Bin Width"].tolist() == pytest.approx(epd_energies()["Electron_Bins_Width"])


def test_flux_cache_file_depends_on_the_settings(events, tmp_path):
    groups = default_group_options()
    name = flux_cache_file(events, "l2", ["sun"], groups, "cache")
    assert name == flux_cache_file(events, "l2", ["sun"], default_group_options(), "cache")
    assert os.path.basename(name).startswith("dfs_flux_l2_") and name.endswith(".pkl")
    groups["protons"]["8 MeV"]["channels"] = [1, 2]
    assert flux_cache_file(events, "l2", ["sun"], groups, "cache") != name
    assert flux_cache_file(events, "l2", ["sun", "north"], default_group_options(), "cache") != name
    later = events.copy()
    later["End Time"] += timedelta(hours=1)
    assert flux_cache_file(later, "l2", ["sun"], default_group_options(), "cache") != name


def energy_tables() -> dict:
    """Returns the energies of the fake loader in the form of load_energies(), without calling the loader"""
    energies = epd_energies()
    return {"HET": {particle: pd.DataFrame({"Low Energy": energies[f"{prefix}_Bins_Low_Energy"],
                                            "Bin Width": energies[f"{prefix}_Bins_Width"]})
                    for particle, prefix in (("protons", "H"), ("electrons", "Electron"))}}


def download(events, tmp_path, **kwargs):
    return download_data(events, "l2", ["sun", "north"], default_group_options(), energy_tables(), "data",
                         str(tmp_path), 2, **kwargs)


def test_download_groups_the_channels_of_each_viewing(events, tmp_path, monkeypatch):
    fake = FakeEPD({("protons", "north"): T0})
    monkeypatch.setattr(data, "epd_load", fake)
    flux = download(events, tmp_path)["protons"]["HET"]["no_resample"]
    assert list(flux.columns) == [("sun", "8 MeV"), ("sun", "25 MeV"), ("sun", "50 MeV"),
                                  ("north", "8 MeV"), ("north", "25 MeV"), ("north", "50 MeV")]
    assert flux.index.names == ["Event No", "Datetime"]
    times = flux.loc[1].index
    # the period of data of the event, with the sub-second part of the times removed
    assert times[0] >= events.loc[1, "Plot Start"] and times[-1] <= events.loc[1, "Plot End"]
    assert (times.microsecond == 0).all()
    assert flux[("sun", "8 MeV")].max() == pytest.approx(1.0)
    # the flux is the one of the original times, before their sub-second part was removed
    expected = profile(times + pd.Timedelta(OFFSET.microseconds, unit="us"), T0)
    np.testing.assert_allclose(flux[("north", "25 MeV")].to_numpy(), expected, rtol=1e-5)


def test_download_of_ion_columns(events, tmp_path, monkeypatch):
    fake = FakeEPD({("protons", "sun"): T0}, proton_prefix="Ion")
    monkeypatch.setattr(data, "epd_load", fake)
    flux = download(events, tmp_path)["protons"]["HET"]["no_resample"]
    assert flux[("sun", "8 MeV")].max() > 50


def test_download_writes_and_reads_the_cache(events, tmp_path, monkeypatch):
    fake = FakeEPD({("electrons", "sun"): T0})
    monkeypatch.setattr(data, "epd_load", fake)
    first = download(events, tmp_path)
    calls = len(fake.calls)
    assert calls == 2  # one per viewing
    assert os.path.exists(flux_cache_file(events, "l2", ["sun", "north"], default_group_options(), str(tmp_path)))
    second = download(events, tmp_path)
    assert len(fake.calls) == calls
    pd.testing.assert_frame_equal(first["electrons"]["HET"]["no_resample"], second["electrons"]["HET"]["no_resample"])
    download(events, tmp_path, redownload=True)
    assert len(fake.calls) == 2 * calls


def test_download_retries_with_the_event_period(events, tmp_path, monkeypatch):
    fake = FakeEPD(fail=1)
    monkeypatch.setattr(data, "epd_load", fake)
    download(events, tmp_path)
    assert fake.calls[0]["startdate"] == events.loc[1, "Plot Start"]
    assert fake.calls[1]["startdate"] == events.loc[1, "BG Start"]
    assert fake.calls[1]["enddate"] == events.loc[1, "End Time"]


def test_download_fails_after_the_last_try(events, tmp_path, monkeypatch):
    fake = FakeEPD(fail=2)
    monkeypatch.setattr(data, "epd_load", fake)
    with pytest.raises(ValueError, match="No data"):
        download(events, tmp_path)


def test_resample_flux(events, tmp_path, monkeypatch):
    fake = FakeEPD({("protons", "sun"): T0})
    monkeypatch.setattr(data, "epd_load", fake)
    dfs_flux = download(events, tmp_path)
    resampled = resample_flux(dfs_flux, [timedelta(minutes=2), timedelta(minutes=10)])
    assert list(resampled["protons"]["HET"]) == [timedelta(minutes=2), timedelta(minutes=10)]
    raw = dfs_flux["protons"]["HET"]["no_resample"].loc[1, ("sun", "8 MeV")]
    two = resampled["protons"]["HET"][timedelta(minutes=2)].loc[1, ("sun", "8 MeV")]
    start = pd.Timestamp(T0)
    assert two[start] == pytest.approx(raw[start:start + timedelta(seconds=119)].mean())
    assert two.index[1] - two.index[0] == timedelta(minutes=2)
