"""Loading of the Solar Orbiter EPD data: channel energies, flux of the channel groups, cache and resampling

load() returns the data in the form of the observers of the VDA tool: for each particle, the flux with the channel
numbers as columns and the energies of the channels.
"""
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager, redirect_stderr
from datetime import datetime, timedelta
from io import StringIO
from os.path import exists as pexists
from os.path import join as pjoin
from typing import NamedTuple

import pandas as pd
from solo_epd_loader import epd_load

from .inputs import count

# a progress bar of tqdm, e.g. "file.cdf:  37%|███▋      | 557k/1.52M [00:00<00:00, 1.06MB/s]"
DOWNLOAD_BAR = re.compile(r"\[[\d:]+(<[\d:?]+)?, [^\]]*/s\]")


@contextmanager
def without_download_bars():
    """Hides the progress bars of the downloads of solo-epd-loader, one per file, which tqdm writes to stderr; the other
    messages written to stderr meanwhile, e.g. warnings, are written after"""
    captured = StringIO()
    try:
        with redirect_stderr(captured):
            yield
    finally:
        # tqdm redraws a bar on the same line with carriage returns
        lines = captured.getvalue().replace("\r", "\n").split("\n")
        if other := [line for line in lines if line.strip() and not DOWNLOAD_BAR.search(line)]:
            print("\n".join(other), file=sys.stderr)


# prefix of the flux columns of each particle in the EPD data; the protons of EPT are "Ion"
PARTICLE_PREFIX = {
    "protons": "H",
    "electrons": "Electron"
}


class ParticleData(NamedTuple):
    # Flux with the channel numbers as columns
    flux: pd.DataFrame
    # "Low Energy" and "Bin Width" (MeV) of each channel number
    energies: pd.DataFrame


def load(sensor: str,
         startdate: datetime,
         enddate: datetime,
         viewing: str,
         path: str,
         particles: list[str] | None = None,
         level: str = "l2") -> dict[str, ParticleData]:
    """Returns the EPD data of each particle (all by default) as ParticleData, downloaded if they are not in path

    Raises ValueError if there are no data for the period.
    """
    # the folder of the files of the loader, made here, or the loader announces it in the middle of the line of the
    # loading
    os.makedirs(pjoin(path, level.lower(), "epd", sensor.lower()), exist_ok=True)
    with without_download_bars():
        df_protons, df_electrons, energies = epd_load(sensor=sensor,
                                                      level=level,
                                                      startdate=startdate,
                                                      enddate=enddate,
                                                      viewing=viewing,
                                                      path=path,
                                                      autodownload=True)
    data = {}
    for particle, df_particle in (("protons", df_protons), ("electrons", df_electrons)):
        if particles is not None and particle not in particles:
            continue
        prefix = PARTICLE_PREFIX[particle]
        if particle == "protons" and f"{prefix}_Flux" not in df_particle.columns.get_level_values(0):
            prefix = "Ion"
        flux = df_particle[f"{prefix}_Flux"]
        # e.g. "H_Flux_12" is channel 12
        flux = flux.set_axis([int(c.rsplit("_", 1)[1]) for c in flux.columns], axis="columns")
        data[particle] = ParticleData(
            flux,
            pd.DataFrame({"Low Energy": energies[f"{prefix}_Bins_Low_Energy"],
                          "Bin Width": energies[f"{prefix}_Bins_Width"]},
                         index=flux.columns),
        )
    return data


def channel_layout(group_options: dict) -> tuple[list[str], dict, dict, set]:
    """Returns the particles, the sensors per particle, the channels per particle and sensor, and all the sensors"""
    particles = list(group_options.keys())

    sensors = {
        particle: set([spec["sensor"] for spec in group_options[particle].values()])
        for particle in particles
    }

    channels = {
        particle: {
            sensor: [channel
                     for sublist in [spec["channels"]
                                     for spec in group_options[particle].values()
                                     if spec["sensor"] == sensor]
                     for channel in sublist]
            for sensor in sensors[particle]
        }
        for particle in particles
    }

    sensors_all = set([s for particle in group_options.values() for spec in particle.values() for s in [spec["sensor"]]])
    return particles, sensors, channels, sensors_all


def load_energies(sensors: set,
                  level: str,
                  startdate: datetime,
                  enddate: datetime,
                  viewing: str,
                  path: str) -> dict:
    """Returns the channel energies of each sensor and particle ("Low Energy" and "Bin Width" of each channel number)

    The energies are read for one period and viewing, as they are assumed not to change with either.
    """
    return {sensor: {particle: particle_data.energies
                     for particle, particle_data in load(sensor, startdate, enddate, viewing, path, level=level).items()}
            for sensor in sensors}


def load_event_energies(event_no: int, row: pd.Series, sensors: set, level: str, viewing: str, path: str) -> dict:
    """Returns load_energies() for the data period of an event (Plot Start to Plot End), and prints one line on it: the
    event, then "done" with the number of files downloaded, or "failed" (the error is raised)"""
    print(f"Reading the energies of the {'/'.join(sorted(sensors))} channels from the data of event {event_no} "
          f"({row['Plot Start']:%Y-%m-%d} to {row['Plot End']:%Y-%m-%d})...", end=" ")
    files_before = count_files(path)
    try:
        energies = load_energies(sensors, level, row["Plot Start"], row["Plot End"], viewing, path)
    except Exception:
        print("failed.")
        raise
    downloaded = count_files(path) - files_before
    print(f"done, {count(downloaded, 'file')} downloaded." if downloaded else "done.")
    return energies


def group_channels_de(df_to_group: pd.DataFrame,
                      groups: list[list[str]],
                      energy_bins_widths: list[list[float]],
                      names: list[str]) -> pd.DataFrame:
    """Returns the flux of each group of columns, as the mean of its columns weighted by their energy widths"""
    grouped_all = {}
    for columns, energy_bins_width, name in zip(groups, energy_bins_widths, names):
        de = sum(energy_bins_width)
        grouped_series = df_to_group.loc[slice(None), columns[0]]*energy_bins_width[0]
        for column, eb_width in zip(columns[1:], energy_bins_width[1:]):
            grouped_series = grouped_series.add(df_to_group.loc[slice(None), column]*eb_width, fill_value=0)
        grouped_all[name] = grouped_series/de
    df_grouped = pd.DataFrame(grouped_all)
    return df_grouped


# the cache of the flux of the channel groups in dir_saves: {key of an event and the data settings: its flux}
CACHE_FILE = "flux_cache.pkl"
# the cache is saved after this many newly loaded events, at the end, and when the data step stops
SAVE_EVERY = 10


def event_cache_key(row: pd.Series, level: str, viewings: list[str], group_options: dict) -> str:
    """Returns the key of the flux of an event in the cache, from the settings that it depends on: the data level, the
    viewings, the channel groups and the times of the event that its data are loaded for"""
    settings = {
        "level": level,
        "viewings": viewings,
        "group_options": group_options,
        "event": row[["BG Start", "End Time", "Plot Start", "Plot End"]].astype(str).to_dict(),
    }
    return hashlib.sha1(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()


def _renumbered(flux: dict, event_no: int) -> dict:
    """Returns the flux of an event from the cache, {particle: {sensor: DataFrame}}, with its number in the event list,
    which can differ from the one it was cached with"""
    return {particle: {sensor: frame.rename(index=lambda _: event_no, level="Event No")
                       for sensor, frame in by_sensor.items()} for particle, by_sensor in flux.items()}


def _write_cache(path: str, entries: dict) -> None:
    """Writes the cache through a temporary file, so that a stopped write does not damage it"""
    pd.to_pickle(entries, f"{path}.tmp")
    os.replace(f"{path}.tmp", path)


def _load_with_retries(row: pd.Series,
                       sensor: str,
                       level: str,
                       viewing: str,
                       path: str,
                       tries_max: int) -> tuple[dict, datetime, datetime]:
    """Returns the data of an event and the period they were loaded for

    The first try loads the period of data of the event (Plot Start to Plot End), the next ones only the background
    start to the end time. The error of the last try is raised.
    """
    tries = 0
    data = {}
    startdate = row["Plot Start"]
    enddate = row["Plot End"]
    while len(data) == 0 and tries < tries_max:
        try:
            tries += 1
            data = load(sensor, startdate, enddate, viewing, path, level=level)
        except ValueError:
            if tries >= tries_max:
                raise
            print(f"\nNo {sensor} {level} {viewing} data from {startdate} to {enddate}; trying the background start to "
                  "the end time.")
            startdate = row["BG Start"]
            enddate = row["End Time"]
    return data, startdate, enddate


def _group_event_flux(particle_data: ParticleData,
                      startdate: datetime,
                      enddate: datetime,
                      groups: dict,
                      widths: pd.Series) -> pd.DataFrame:
    """Returns the flux of the channel groups ({label: spec}) of one sensor in the period, at whole seconds"""
    flux = particle_data.flux[startdate:enddate]
    flux.index = flux.index.map(lambda x: x.replace(microsecond=0, nanosecond=0))
    return group_channels_de(flux,
                             [spec["channels"] for spec in groups.values()],
                             [[widths[channel] for channel in spec["channels"]] for spec in groups.values()],
                             list(groups))


def _add_flux(frames: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Returns the flux of the frames with the new flux added, summing the values of duplicate times"""
    frames = new.copy() if frames.empty else pd.concat([frames, new], axis="index")
    return frames.groupby(level=[0, 1]).sum(min_count=1).sort_index()


def count_files(path: str) -> int:
    """Returns the number of files in the folder and its subfolders (0 if it does not exist)"""
    return sum(len(files) for _, _, files in os.walk(path))


def _load_event(event_no: int, row: pd.Series, level: str, viewings: list[str], group_options: dict, energies: dict,
                path: str, tries_max: int) -> dict:
    """Returns the flux of the channel groups of an event, {particle: {sensor: DataFrame}}, indexed by event number and
    time, with the columns (viewing, group)"""
    particles, sensors, _, sensors_all = channel_layout(group_options)
    flux = {particle: {sensor: pd.DataFrame([]) for sensor in sensors[particle]} for particle in particles}
    for viewing in viewings:
        for sensor in sensors_all:
            data, startdate, enddate = _load_with_retries(row, sensor, level, viewing, path, tries_max)
            for particle in particles:
                groups = {label: spec for label, spec in group_options[particle].items() if spec["sensor"] == sensor}
                if not groups:
                    continue
                df_temp = _group_event_flux(data[particle], startdate, enddate, groups,
                                            energies[sensor][particle]["Bin Width"])
                df_temp = pd.concat({viewing: pd.concat({event_no: df_temp}, axis="index")}, axis="columns")
                df_temp.index.names = ["Event No", "Datetime"]
                flux[particle][sensor] = _add_flux(flux[particle][sensor], df_temp)
    return flux


def download_data(events: pd.DataFrame,
                  level: str,
                  viewings: list[str],
                  group_options: dict,
                  energies: dict,
                  path: str,
                  cache_folder: str,
                  tries_max: int,
                  cache: bool = False,
                  redownload: bool = False) -> tuple[dict, dict]:
    """Returns the flux of the channel groups per particle and sensor ({"no_resample": DataFrame}) of the events that
    could be loaded, and {event number: error} of the events left out

    The data are loaded from the files in path, the missing ones downloaded. With cache, the flux of each event is
    kept in CACHE_FILE in cache_folder, and loaded from there in later runs (not with redownload); the cache is saved
    every SAVE_EVERY newly loaded events, at the end, and when the loading stops. An event whose data cannot be
    loaded is left out; if none can be, the error of the first one is raised.
    """
    cache_file = pjoin(cache_folder, CACHE_FILE)
    if cache:
        os.makedirs(cache_folder, exist_ok=True)
    entries = pd.read_pickle(cache_file) if cache and pexists(cache_file) else {}
    print(f"Loading the {level} data of {count(len(events), 'event')}; the files missing from {path} are downloaded"
          + (f", and the flux is cached in {cache_file}." if cache else "."))
    loaded, skipped, unsaved = {}, {}, 0
    try:
        for position, (event_no, row) in enumerate(events.iterrows(), start=1):
            progress = f"({position / len(events) * 100:.2f}%)"
            key = event_cache_key(row, level, viewings, group_options)
            if cache and not redownload and key in entries:
                loaded[event_no] = _renumbered(entries[key], event_no)
                print(f"Event {event_no}... loaded from the cache {progress}")
                continue
            print(f"Event {event_no}", end="... ")
            files_before = count_files(path)
            try:
                loaded[event_no] = _load_event(event_no, row, level, viewings, group_options, energies, path, tries_max)
            except Exception as error:
                skipped[event_no] = error
                print(f"left out: {error} {progress}")
                continue
            downloaded = count_files(path) - files_before
            print(f"loaded{f', {downloaded} files downloaded' if downloaded else ''} {progress}")
            if cache:
                entries[key] = loaded[event_no]
                unsaved += 1
                if unsaved == SAVE_EVERY:
                    _write_cache(cache_file, entries)
                    unsaved = 0
    finally:
        if unsaved:
            _write_cache(cache_file, entries)
    if not loaded:
        raise next(iter(skipped.values()))
    particles, sensors, _, _ = channel_layout(group_options)
    return {particle: {sensor: {"no_resample": pd.concat([flux[particle][sensor] for flux in loaded.values()])}
                       for sensor in sensors[particle]} for particle in particles}, skipped


def resample_flux(dfs_flux: dict, resample_freqs: list[timedelta]) -> dict:
    """Returns the flux of each particle and sensor resampled to every resolution, from the cached flux, in its type

    The cached flux (key "no_resample") is not kept.
    """
    resampled = {}
    for particle, by_sensor in dfs_flux.items():
        resampled[particle] = {}
        for sensor, frames in by_sensor.items():
            flux = frames["no_resample"]
            # in the type of the data (float32 for EPD), as before pandas 3.1, whose mean is float64
            resampled[particle][sensor] = {
                resample_freq: flux.groupby(level="Event No").resample(resample_freq, level="Datetime").mean()
                .astype(flux.dtypes.to_dict())
                for resample_freq in resample_freqs
            }
    return resampled
