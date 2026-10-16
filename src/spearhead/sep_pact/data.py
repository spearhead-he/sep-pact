"""Loading of the Solar Orbiter EPD data: channel energies, flux of the channel groups, cache and resampling"""
import hashlib
import json
from datetime import datetime, timedelta
from os.path import exists as pexists
from os.path import join as pjoin

import pandas as pd
from solo_epd_loader import epd_load

# prefix of the flux columns of each particle in the EPD data
PARTICLE_PREFIX = {
    "protons": "H",
    "electrons": "Electron"
}


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
    """Returns the channel energies of each sensor, with the proton keys named like the flux columns ("H")

    The energies are read for one period and viewing, as they are assumed not to change with either.
    """
    energies = {}
    for sensor in sensors:
        _, _, energies[sensor] = epd_load(sensor=sensor,
                                          level=level,
                                          startdate=startdate,
                                          enddate=enddate,
                                          viewing=viewing,
                                          path=path,
                                          autodownload=True)
        for key in list(energies[sensor].keys()):
            if "Ion" in key:
                energies[sensor][key.replace("Ion", PARTICLE_PREFIX["protons"])] = energies[sensor].pop(key)
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
            print(f"Loading the flux DataFrames from {cache_file}.")
            return pd.read_pickle(cache_file)
        else:
            print(f"{cache_file} does not exist. Proceeding with download.")
    particles, sensors, channels, sensors_all = channel_layout(group_options)
    dfs_flux = {
        particle: {
            sensor: {"no_resample": pd.DataFrame([])}
            for sensor in sensors[particle]
        }
        for particle in particles
    }
    print(f"Downloading {level} data...")
    total_events = len(events)
    for event_no, row in events.iterrows():
        dfs_cur_event = {
            particle: {
                sensor: {"no_resample": pd.DataFrame([])}
                for sensor in sensors[particle]
            }
            for particle in particles
        }
        print(f"Event {event_no}", end="... ")
        for viewing in viewings:
            for sensor in sensors_all:
                tries = 0
                df_flux_cur_event = {}
                plot_startdate = row["Plot Start"]
                plot_enddate = row["Plot End"]
                while len(df_flux_cur_event) == 0 and tries < tries_max:
                    try:
                        tries += 1
                        df_flux_cur_event["protons"], df_flux_cur_event["electrons"], _ = epd_load(sensor=sensor,
                                                                                                   level=level,
                                                                                                   startdate=plot_startdate,
                                                                                                   enddate=plot_enddate,
                                                                                                   viewing=viewing,
                                                                                                   path=path,
                                                                                                   autodownload=True)
                        # Unify column names for protons. They can originally be "Ion" or "H"
                        df_flux_cur_event["protons"].columns = pd.MultiIndex.from_tuples(
                            [tuple([name.replace("Ion", PARTICLE_PREFIX["protons"]) for name in i])
                             for i in df_flux_cur_event["protons"].columns])
                    except ValueError:
                        if tries >= tries_max:
                            raise
                        print("\n", sensor, level, plot_startdate, plot_enddate, viewing)
                        plot_startdate = row["BG Start"]
                        plot_enddate = row["End Time"]
                        print("Retrying with shortened time range\n", sensor, level, plot_startdate, plot_enddate, viewing)
                if len(df_flux_cur_event) == 0:
                    print("FAILED/No Data\n", sensor, level, plot_startdate, plot_enddate, viewing)

                for particle in particles:
                    # Keep only the needed columns
                    try:
                        wanted_channels = channels[particle][sensor]
                    except KeyError:
                        continue
                    prefix = PARTICLE_PREFIX[particle]
                    wanted_columns = [multicol
                                      for multicol in df_flux_cur_event[particle].columns
                                      if any([f"{prefix}_Flux" in col for col in multicol])
                                      and any([f"{prefix}_Flux_{ch}" == col for ch in wanted_channels for col in multicol])]
                    unwanted_columns = set(df_flux_cur_event[particle].columns).difference(set(wanted_columns))
                    df_flux_cur_event[particle].drop(columns=unwanted_columns, inplace=True)

                    # Add the values to the current event dataframes
                    if len(df_flux_cur_event[particle].columns) > 0:
                        df_temp = df_flux_cur_event[particle][plot_startdate:plot_enddate]
                        df_temp.columns = df_temp.columns.droplevel(0)
                        df_temp.index = df_temp.index.map(lambda x: x.replace(microsecond=0, nanosecond=0))

                        # group energy channels
                        specs = [(mevlbl, mev_specs) for mevlbl, mev_specs in group_options[particle].items()
                                 if mev_specs["sensor"] == sensor]
                        groups = [[f"{prefix}_Flux_{channel}" for channel in mev_specs["channels"]] for _, mev_specs in specs]
                        widths = energies[sensor][f"{prefix}_Bins_Width"]
                        energy_bins_widths = [[widths[channel] for channel in mev_specs["channels"]] for _, mev_specs in specs]
                        names = [mevlbl for mevlbl, _ in specs]
                        df_temp = group_channels_de(df_temp, groups, energy_bins_widths, names)

                        # Add multiindices
                        df_temp = pd.concat({event_no: df_temp}, axis="index")
                        df_temp = pd.concat({viewing: df_temp}, axis="columns")
                        df_temp.index.names = ["Event No", "Datetime"]

                        # Add the values to the current event dataframes
                        current = dfs_cur_event[particle][sensor]["no_resample"]
                        current = df_temp.copy() if current.empty else pd.concat([current, df_temp], axis="index")
                        # Remove duplicate indices by grouping
                        current = current.groupby(level=[0, 1]).sum(min_count=1)
                        dfs_cur_event[particle][sensor]["no_resample"] = current.sort_index()

        # Add the current event dataframes to the main dataframes
        for particle in particles:
            for sensor in sensors[particle]:
                current = dfs_cur_event[particle][sensor]["no_resample"]
                dfs_flux[particle][sensor]["no_resample"] = current.copy() \
                    if dfs_flux[particle][sensor]["no_resample"].empty \
                    else pd.concat([dfs_flux[particle][sensor]["no_resample"], current], axis="index")

        print(f"Downloaded/Loaded ({event_no/total_events*100:.2f}%)")
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
