"""Tests of the data: channel layout, grouping of the channels, the download with the events left out and the cache,
and the resampling"""
import os
import sys
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import spearhead.sep_pact.data as data
from spearhead.sep_pact.conf import default_group_options
from spearhead.sep_pact.data import (CACHE_FILE, ParticleData, channel_layout, download_data, event_cache_key,
                                     group_channels_de, load, load_energies, resample_flux)
from spearhead.sep_pact.inputs import read_events
from tests.helpers import (DOWNLOAD_BAR_OUTPUT, OFFSET, T0, DownloadingEPD, FailingEPD, FakeEPD, epd_energies,
                           make_params, profile, write_events)


@pytest.fixture
def events(tmp_path):
    params = make_params(tmp_path)
    return read_events(write_events(tmp_path / "inputs", {1: {"Reference Time": T0}}), params)


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


def test_event_cache_key_depends_on_the_settings(events):
    row = events.loc[1]
    groups = default_group_options()
    key = event_cache_key(row, "l2", ["sun"], groups)
    assert key == event_cache_key(row.copy(), "l2", ["sun"], default_group_options())
    groups["protons"]["8 MeV"]["channels"] = [1, 2]
    assert event_cache_key(row, "l2", ["sun"], groups) != key
    assert event_cache_key(row, "l2", ["sun", "north"], default_group_options()) != key
    later = row.copy()
    later["End Time"] += timedelta(hours=1)
    assert event_cache_key(later, "l2", ["sun"], default_group_options()) != key


def energy_tables() -> dict:
    """Returns the energies of the fake loader in the form of load_energies(), without calling the loader"""
    energies = epd_energies()
    return {"HET": {particle: pd.DataFrame({"Low Energy": energies[f"{prefix}_Bins_Low_Energy"],
                                            "Bin Width": energies[f"{prefix}_Bins_Width"]})
                    for particle, prefix in (("protons", "H"), ("electrons", "Electron"))}}


def download_with_skipped(events, tmp_path, **kwargs) -> tuple:
    return download_data(events, "l2", ["sun", "north"], default_group_options(), energy_tables(), "data",
                         str(tmp_path), 2, **kwargs)


def download(events, tmp_path, **kwargs) -> dict:
    return download_with_skipped(events, tmp_path, **kwargs)[0]


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


def test_download_of_a_particle_without_groups(events, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    groups = {"electrons": default_group_options()["electrons"], "protons": {}}
    flux, skipped = download_data(events, "l2", ["sun"], groups, energy_tables(), "data", str(tmp_path), 2)
    assert list(flux["electrons"]["HET"]["no_resample"].columns) == [("sun", "1 MeV"), ("sun", "5.9930 - 18.8300 MeV")]
    assert flux["protons"] == {} and skipped == {}


def test_download_without_the_cache_writes_nothing(events, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    download(events, tmp_path / "cache")
    assert not os.path.exists(tmp_path / "cache")


def test_download_writes_and_reads_the_cache(events, tmp_path, monkeypatch):
    fake = FakeEPD({("electrons", "sun"): T0})
    monkeypatch.setattr(data, "epd_load", fake)
    cache = tmp_path / "cache"
    first = download(events, cache, cache=True)
    calls = len(fake.calls)
    assert calls == 2  # one per viewing
    assert os.listdir(cache) == [CACHE_FILE]
    second = download(events, cache, cache=True)
    assert len(fake.calls) == calls
    pd.testing.assert_frame_equal(first["electrons"]["HET"]["no_resample"], second["electrons"]["HET"]["no_resample"])
    download(events, cache, cache=True, redownload=True)
    assert len(fake.calls) == 2 * calls


def times_of(*days) -> pd.DataFrame:
    """Events with a Reference Time T0 + day, numbered from 1"""
    return pd.concat([events_at(day, n) for n, day in enumerate(days, start=1)])


def events_at(day: int, event_no: int) -> pd.DataFrame:
    start = pd.Timestamp(T0) + timedelta(days=day)
    return pd.DataFrame({"Start Time": [start], "BG Start": [start], "BG End": [start + timedelta(hours=1)],
                         "End Time": [start + timedelta(hours=30)], "Plot Start": [start],
                         "Plot End": [start + timedelta(hours=30)]}, index=pd.Index([event_no], name="Event No"))


def test_cache_keeps_the_entries_of_other_events(tmp_path, monkeypatch):
    fake = FakeEPD()
    monkeypatch.setattr(data, "epd_load", fake)
    download(times_of(0, 10), tmp_path, cache=True)
    calls = len(fake.calls)
    # a list with one of the events, now number 1, and a new one: only the new one is loaded
    flux = download(times_of(10, 20), tmp_path, cache=True)
    assert len(fake.calls) == calls + 2
    assert len(pd.read_pickle(tmp_path / CACHE_FILE)) == 3
    frame = flux["protons"]["HET"]["no_resample"]
    assert frame.index.get_level_values("Event No").unique().tolist() == [1, 2]
    pd.testing.assert_frame_equal(frame.loc[1], download(times_of(10), tmp_path)["protons"]["HET"]["no_resample"].loc[1])


def test_cache_is_saved_every_10_events(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    saves = []
    write = data._write_cache
    monkeypatch.setattr(data, "_write_cache", lambda path, entries: saves.append(len(entries)) or write(path, entries))
    download(times_of(*range(0, 50, 2)), tmp_path, cache=True)
    # after 10 and 20 events, and the last 5 at the end
    assert saves == [10, 20, 25]
    saves.clear()
    # all from the cache: nothing to save
    download(times_of(*range(0, 50, 2)), tmp_path, cache=True)
    assert saves == []


class StoppingEPD(FakeEPD):
    """FakeEPD that stops the loading (as Ctrl+C or the stop button) at a given call"""

    def __init__(self, stop_at: int):
        super().__init__()
        self.stop_at = stop_at

    def __call__(self, *args, **kwargs) -> tuple:
        if len(self.calls) == self.stop_at:
            raise KeyboardInterrupt
        return super().__call__(*args, **kwargs)


def test_cache_is_saved_when_the_loading_stops(tmp_path, monkeypatch):
    # two calls per event (one per viewing): stopped in the third event
    monkeypatch.setattr(data, "epd_load", StoppingEPD(stop_at=4))
    with pytest.raises(KeyboardInterrupt):
        download(times_of(0, 10, 20), tmp_path, cache=True)
    assert len(pd.read_pickle(tmp_path / CACHE_FILE)) == 2
    assert not os.path.exists(tmp_path / f"{CACHE_FILE}.tmp")


def test_download_leaves_out_the_events_without_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(data, "epd_load", FailingEPD([pd.Timestamp(T0) + timedelta(days=10, hours=5)]))
    flux, skipped = download_with_skipped(times_of(0, 10, 20), tmp_path, cache=True)
    assert list(skipped) == [2] and "No data found" in str(skipped[2])
    assert flux["protons"]["HET"]["no_resample"].index.get_level_values("Event No").unique().tolist() == [1, 3]
    out = capsys.readouterr().out
    assert "Event 2... " in out and "left out: No data found from 2021-01-11 12:00:00 (66.67%)" in out
    # the event left out is not in the cache, and is tried again
    assert len(pd.read_pickle(tmp_path / CACHE_FILE)) == 2


def test_download_fails_if_no_event_has_data(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "epd_load", FakeEPD(fail=100))
    with pytest.raises(ValueError, match="No data found"):
        download(times_of(0, 10), tmp_path)


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
    assert len(fake.calls) == 2


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


def test_download_messages(events, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(data, "epd_load", DownloadingEPD())
    folder = str(tmp_path / "data")
    events = events.rename(index={1: 20})

    def load_data(**kwargs):
        download_data(events, "l2", ["sun", "north"], default_group_options(), energy_tables(), folder, str(tmp_path), 2,
                      **kwargs)
        return capsys.readouterr().out

    out = load_data()
    assert f"Loading the l2 data of 1 event; the files missing from {folder} are downloaded." in out
    # one file per viewing; the progress is the position of the event in the list, not its number
    assert "Event 20... loaded, 2 files downloaded (100.00%)" in out
    assert f"and the flux is cached in {tmp_path / CACHE_FILE}." in load_data(cache=True)
    assert "Event 20... loaded from the cache (100.00%)" in load_data(cache=True)


def test_download_message_without_new_files(events, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(data, "epd_load", FakeEPD())
    download_data(events, "l2", ["sun"], default_group_options(), energy_tables(), str(tmp_path / "data"),
                  str(tmp_path), 2)
    assert "Event 1... loaded (100.00%)" in capsys.readouterr().out


def test_download_message_of_a_retry(events, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(data, "epd_load", FakeEPD(fail=1))
    download_data(events, "l2", ["sun"], default_group_options(), energy_tables(), str(tmp_path / "data"),
                  str(tmp_path), 2)
    assert "No HET l2 sun data from" in capsys.readouterr().out


def test_without_download_bars_keeps_the_other_messages(capsys):
    with data.without_download_bars():
        sys.stderr.write(DOWNLOAD_BAR_OUTPUT)
        sys.stderr.write("a warning\n")
        print("on stdout")
    out, err = capsys.readouterr()
    assert out == "on stdout\n" and err == "a warning\n"


def test_without_download_bars_after_an_error(capsys):
    with pytest.raises(ValueError, match="No data"):
        with data.without_download_bars():
            sys.stderr.write(DOWNLOAD_BAR_OUTPUT + "a warning before the error\n")
            raise ValueError("No data")
    assert capsys.readouterr().err == "a warning before the error\n"


def test_download_data_without_the_download_bars(events, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(data, "epd_load", DownloadingEPD())
    download_data(events, "l2", ["sun", "north"], default_group_options(), energy_tables(), str(tmp_path / "data"),
                  str(tmp_path), 2)
    out, err = capsys.readouterr()
    # one line per event, with the number of files downloaded, and the warnings of the loader
    assert "Event 1... loaded, 2 files downloaded (100.00%)" in out
    assert "B/s]" not in out + err and "UserWarning: a warning of the loader" in err
