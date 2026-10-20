"""Loading of the Solar Orbiter EPD data: channel energies, flux of the channel groups, cache and resampling

load() returns the data in the form of the observers of the VDA tool: for each particle, the flux with the channel
numbers as columns and the energies of the channels.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from os.path import exists as pexists
from os.path import join as pjoin
from typing import NamedTuple

import pandas as pd
from solo_epd_loader import epd_load

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


def flux_cache_file(events: pd.DataFrame,
                    level: str,
                    viewings: list[str],
                    group_options: dict,
                    folder: str) -> str:
    """Returns the cache file of the flux DataFrames, named after the settings that the data depend on"""
    settings = {
        "level": level,
        "viewings": viewings,
        "group_options": group_options,
        "events": events[["BG Start", "End Time", "Plot Start", "Plot End"]].astype(str).to_dict(orient="split")
    }
    key = hashlib.sha1(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:10]
    return pjoin(folder, f"dfs_flux_{level}_{key}.pkl")


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


def _count_files(path: str) -> int:
    """Returns the number of files in the folder and its subfolders (0 if it does not exist)"""
    return sum(len(files) for _, _, files in os.walk(path))


def download_data(events: pd.DataFrame,
                  level: str,
                  viewings: list[str],
                  group_options: dict,
                  energies: dict,
                  path: str,
                  cache_folder: str,
                  tries_max: int,
                  redownload: bool = False) -> dict:
    """Returns the flux of the channel groups per particle, sensor and event, loaded from the cache if it exists"""
    cache_file = flux_cache_file(events, level, viewings, group_options, cache_folder)
    if not redownload:
        if pexists(cache_file):
            print(f"Loading the flux of the channel groups from the cache {cache_file}.")
            return pd.read_pickle(cache_file)
        print(f"No cache {cache_file} for these events and settings.")
    particles, sensors, _, sensors_all = channel_layout(group_options)
    dfs_flux = {particle: {sensor: {"no_resample": pd.DataFrame([])} for sensor in sensors[particle]}
                for particle in particles}
    n_events = f"{len(events)} event{'' if len(events) == 1 else 's'}"
    print(f"Loading the {level} data of {n_events}; the files missing from {path} are downloaded.")
    for position, (event_no, row) in enumerate(events.iterrows(), start=1):
        current = {particle: {sensor: pd.DataFrame([]) for sensor in sensors[particle]} for particle in particles}
        print(f"Event {event_no}", end="... ")
        files_before = _count_files(path)
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
                    current[particle][sensor] = _add_flux(current[particle][sensor], df_temp)

        # Add the current event dataframes to the main dataframes
        for particle in particles:
            for sensor in sensors[particle]:
                previous = dfs_flux[particle][sensor]["no_resample"]
                dfs_flux[particle][sensor]["no_resample"] = current[particle][sensor].copy() if previous.empty \
                    else pd.concat([previous, current[particle][sensor]], axis="index")

        downloaded = _count_files(path) - files_before
        print(f"loaded{f', {downloaded} files downloaded' if downloaded else ''} ({position / len(events) * 100:.2f}%)")
    pd.to_pickle(dfs_flux, cache_file)
    return dfs_flux


def resample_flux(dfs_flux: dict, resample_freqs: list[timedelta]) -> dict:
    """Returns the flux of each particle and sensor resampled to every resolution, from the cached flux

    The cached flux (key "no_resample") is not kept.
    """
    resampled = {}
    for particle, by_sensor in dfs_flux.items():
        resampled[particle] = {}
        for sensor, frames in by_sensor.items():
            resampled[particle][sensor] = {
                resample_freq: frames["no_resample"].groupby(level="Event No").resample(resample_freq, level="Datetime").mean()
                for resample_freq in resample_freqs
            }
    return resampled
