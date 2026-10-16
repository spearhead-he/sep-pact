"""The plots, as matplotlib figures"""
from datetime import timedelta
from os.path import join as pjoin

import numpy as np
import pandas as pd
from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .analysis import reference_iter, shocks_in_range


def plot_filename(folder: str, event_no: int) -> str:
    """Returns the file name of the plot of an event"""
    return pjoin(folder, f"event_{event_no:03}.png")


def _plot_no_onset(ax, tool, event_no: int, particle: str, sensor: str, mevlbl: str, ax_title_params: dict) -> None:
    """Plots a channel group without an onset: the flux in fallback_viewing at the coarsest resolution, with a red title"""
    p = tool.params
    bg_start = tool.events.loc[event_no, "BG Start"]
    bg_end = tool.events.loc[event_no, "BG End"]
    calc_end = tool.events.loc[event_no, "End Time"]
    ts_length = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Length")]
    n_zeroes = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Zeroes")]
    ratio = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Ratio")]
    ax_title_params["color"] = "red"
    ax.set_title(f"{mevlbl} {particle}/{sensor} ({p.fallback_viewing} viewing, {int(p.resample_freqs[-1].total_seconds()/60)} mins resolution)",
                 **ax_title_params)
    flux = tool.dfs_flux[particle][sensor][p.resample_freqs[-1]].loc[event_no, (p.fallback_viewing, mevlbl)]
    ax.plot(flux.index, flux.values, label="flux", color="orange", alpha=0.3)
    bot_lim, top_lim = ax.get_ylim()
    ax.fill_between([bg_start, bg_end], bot_lim, top_lim, color="green", alpha=0.3, label="background sample")
    ax.fill_between([bg_end, calc_end], bot_lim, top_lim, color="black", alpha=0.1, label="Event range")
    ratio_txt = f"ratio={f'{ratio:.2f}' if not pd.isna(ratio) else 'N/A'}"
    n_zeroes_txt = f"#zeroes={n_zeroes if not pd.isna(n_zeroes) else 'N/A'}"
    n_non_zeroes_txt = f"#non-zeroes={ts_length-n_zeroes if not pd.isna(ts_length) and not pd.isna(n_zeroes) else 'N/A'}"
    qties_txt = f"{ratio_txt}, {n_zeroes_txt}, {n_non_zeroes_txt}"
    ax.text(flux.index[-1],
            bot_lim * (1 + (np.log10(top_lim) - np.log10(bot_lim)) / 8),
            qties_txt,
            horizontalalignment="right",
            verticalalignment="bottom")
    ax.set_ylim([bot_lim, top_lim])


def _plot_channel(ax, tool, event_no: int, particle: str, sensor: str, mevlbl: str, ax_title_params: dict) -> None:
    """Plots a channel group with an onset: the flux, background, onset, peak flux, fluence and shocks"""
    p = tool.params
    opt = tool.df_optimals
    bg_start = tool.events.loc[event_no, "BG Start"]
    bg_end = tool.events.loc[event_no, "BG End"]
    calc_end = tool.events.loc[event_no, "End Time"]
    ts_length = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Length")]
    n_zeroes = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Zeroes")]
    ratio = tool.df_ts_quality.loc[event_no, (particle, sensor, mevlbl, "Ratio")]

    best_resample_ot = opt.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Resolution")]
    best_viewing_ot = opt.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Viewing")]
    best_resample_lbl_ot = f"{int(best_resample_ot.total_seconds()/60)} mins"
    best_resample_pf = opt.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Resolution")]
    best_viewing_pf = opt.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Viewing")]
    best_resample_flu = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Resolution")]
    best_viewing_flu = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Viewing")]
    # a channel with an onset can still have no peak flux or no fluence
    has_peak = not pd.isna(best_resample_pf)
    has_fluence = not pd.isna(best_resample_flu)

    onset_copied = opt.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Onset Copied")]
    onset_copied = not pd.isna(onset_copied) and bool(onset_copied)
    onset_at_bg_end = opt.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Onset at BG End")]
    onset_at_bg_end = not pd.isna(onset_at_bg_end) and bool(onset_at_bg_end)
    if onset_at_bg_end:
        ax_title_params["color"] = "red"
    ax.set_title(f"{mevlbl} {particle}/{sensor} ({best_viewing_ot} viewing, {best_resample_lbl_ot} resolution)", **ax_title_params)
    top_lim = 1e6

    # set variables
    flux = tool.dfs_flux[particle][sensor][best_resample_ot].loc[event_no, (best_viewing_ot, mevlbl)]
    flux2 = None
    if has_peak and (best_viewing_ot != best_viewing_pf or best_resample_ot != best_resample_pf):
        flux2 = tool.dfs_flux[particle][sensor][best_resample_pf].loc[event_no, (best_viewing_pf, mevlbl)]
    flux3 = None
    if has_fluence and best_resample_pf != best_resample_flu:
        flux3 = tool.dfs_flux[particle][sensor][best_resample_flu].loc[event_no, (best_viewing_flu, mevlbl)]
    bg_level = tool.dfs_events[particle][sensor][best_resample_ot].loc[event_no, (best_viewing_ot, mevlbl, "BG Level")]
    onset_time = opt.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Onset Time")]
    if len(shocks := shocks_in_range(tool.shocktimes, onset_time, calc_end)) > 0:
        calc_end = shocks[0]
    threshold = tool.dfs_events[particle][sensor][best_resample_ot].loc[event_no, (best_viewing_ot, mevlbl, "Threshold")]

    peak_time = opt.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux Time")]
    peak_flux = opt.loc[event_no, (particle, sensor, mevlbl, "Peak Flux", "Peak Flux")]
    if not pd.isna(peak_time):
        top_lim = float(f"1e{int(f'{peak_flux:e}'.split('e')[1]) + 2}")
    elif flux.max() > 0:
        top_lim = float(f"1e{int(f'{flux.max():e}'.split('e')[1]) + 2}")
    if not pd.isna(bg_level) and bg_level > 0:
        bot_lim = float(f"1e{int(f'{bg_level:e}'.split('e')[1]) - 1}")
    else:
        bot_lim = float(f"1e{int(f'{top_lim:e}'.split('e')[1]) - 4}")

    fluence_start = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Fluence Start")]
    fluence_end = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Fluence End")]
    fluence = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Fluence")]
    fluence_threshold = opt.loc[event_no, (particle, sensor, mevlbl, "Fluence", "Fluence Threshold")]

    # data plot
    ax.fill_between([onset_time, calc_end], bot_lim, top_lim, color="black", alpha=0.1, label="Event range")
    ax.plot(flux.index, flux.values, label="flux", color="orange")
    if flux2 is not None:
        ax.plot(flux2.index, flux2.values, label="flux", color="orange", linestyle="--", alpha=0.5)
    if flux3 is not None:
        ax.plot(flux3.index, flux3.values, label="flux", color="brown", linestyle=":", alpha=0.5)
    ax.fill_between([bg_start, bg_end], bot_lim, top_lim, color="green", alpha=0.3, label="background sample")
    ax.axhline(y=bg_level, color="blue", linestyle="--", label="background level")
    ax.axvline(x=onset_time, color="green", linestyle="--", label=f"onset time ({onset_time.strftime('%Y-%m-%d %H:%M')})")
    if not pd.isna(peak_time):
        ax.scatter(peak_time, peak_flux, color="red", zorder=5, label=f"peak flux ({peak_flux:.2E}/{peak_time.strftime('%Y-%m-%d %H:%M')})")
        ax.axhline(y=peak_flux * p.fluence_peak_fraction, color="purple", linestyle="--", label=f"{p.fluence_peak_fraction:g} peak flux")
    if not pd.isna(fluence_threshold):
        ax.axhline(y=fluence_threshold, color="purple", linestyle="--", alpha=0.5)
    ax.axhline(y=threshold, color="red", linestyle="--", label=f"{p.onset_sigma:g}σ threshold")
    if not pd.isna(fluence_start) and not pd.isna(fluence_end):
        ax.fill_between([fluence_start, fluence_end], bot_lim, top_lim, color="brown", alpha=0.2, label=f"fluence ({fluence:.2E})")
    shocktimes_in_plot = shocks_in_range(tool.shocktimes, flux.index[0], flux.index[-1])
    for shocktime in shocktimes_in_plot:
        ax.axvline(x=shocktime, color="purple", linestyle=":", label=f"shock time ({shocktime.strftime('%Y-%m-%d %H:%M')})")

    # text labels
    if has_peak:
        ax.text(peak_time + timedelta(minutes=15),
                peak_flux,
                f"{peak_flux:.2E}/{peak_time.strftime('%H:%M')}/{best_viewing_pf}/{int(best_resample_pf.total_seconds()/60)} mins",
                color="red")
    onset_notes = []
    if onset_copied:
        onset_notes.append(f"from {tool.reference_channel['mev']} {tool.reference_channel['particle']}")
    if onset_at_bg_end:
        onset_notes.append("at BG end")
    ax.text(onset_time + timedelta(minutes=15),
            bot_lim * 10,
            f"{onset_time.strftime('%Y-%m-%d %H:%M')}" + (f" ({', '.join(onset_notes)})" if onset_notes else ""),
            color="green")
    if has_fluence:
        ax.text(fluence_start + abs(fluence_end - fluence_start)/2,
                top_lim / 5,
                f"{fluence:.2E}/{best_viewing_flu}/{int(best_resample_flu.total_seconds()/60)} mins",
                color="brown",
                horizontalalignment="center")
    ax.text(flux.index[-1],
            bot_lim * (1 + (np.log10(top_lim) - np.log10(bot_lim)) / 8),
            f"ratio={ratio:.2f}, #zeroes={n_zeroes}, #non-zeroes={ts_length-n_zeroes}",
            horizontalalignment="right",
            verticalalignment="bottom")
    for shocktime in shocktimes_in_plot:
        ax.text(shocktime + timedelta(minutes=15),
                bot_lim * 10,
                f"{shocktime.strftime('%H:%M')}",
                color="purple")

    # extra ax parameters
    ax.set_ylim([bot_lim, top_lim])
    ax.set_xlim([flux.index[0], flux.index[-1]])


def plot_event(tool, event_no: int, filename: str | None = None) -> Figure:
    """Returns the plot of an event, with one panel per channel group, and saves it to filename if one is given

    tool is a SEPPACT whose steps have run, up to run_fluences().
    """
    p = tool.params
    num_plots = len([True for k in p.group_options.keys() for _ in p.group_options[k]])
    fig_height = 2.5*num_plots
    fig, axs = plt.subplots(figsize=(15, fig_height),
                            nrows=num_plots,
                            ncols=1,
                            sharex=True)
    if num_plots == 1:
        axs = [axs]
    time_formatter = mdates.ConciseDateFormatter(mdates.AutoDateLocator())
    i_ax = 0
    for particle in reference_iter(tool.particles, tool.reference_channel):
        for sensor in reference_iter(tool.sensors[particle], tool.reference_channel):
            for mevlbl in reference_iter(p.group_options[particle].keys(), tool.reference_channel):
                ax_title_params = {
                    "y": 0.85,
                    "loc": "right",
                    "fontdict": {"fontweight": "bold"},
                    "color": "black"
                }
                axs[i_ax].grid()
                axs[i_ax].set_yscale("log")
                if pd.isna(tool.df_optimals.loc[event_no, (particle, sensor, mevlbl, "Onset Time", "Resolution")]):
                    _plot_no_onset(axs[i_ax], tool, event_no, particle, sensor, mevlbl, ax_title_params)
                else:
                    _plot_channel(axs[i_ax], tool, event_no, particle, sensor, mevlbl, ax_title_params)
                i_ax += 1

    fig.suptitle(f"Event {event_no}", y=1.0005)
    fig.supylabel(r"Flux (particle/(cm$^2$ s sr MeV))")
    fig.supxlabel("Time (UTC)")
    axs[-1].xaxis.set_major_formatter(time_formatter)
    hl = [
        ("Data", Line2D([0], [0], color="orange")),
        ("Event Range", Patch(facecolor="black", alpha=0.1)),
        ("BG sample", Patch(facecolor="green", alpha=0.3)),
        ("BG Level", Line2D([0], [0], color="blue", linestyle="--")),
        ("Peak Flux", Line2D([0], [0], marker="o", color="white", markerfacecolor="red")),
        (f"{p.fluence_peak_fraction:g} × Peak Flux", Line2D([0], [0], color="purple", linestyle="--")),
        (f"{p.onset_sigma:g}σ Threshold", Line2D([0], [0], color="red", linestyle="--")),
        ("Onset Time", Line2D([0], [0], color="green", linestyle="--")),
        ("Fluence", Patch(facecolor="brown", alpha=0.2)),
        ("Shock Time", Line2D([0], [0], color="purple", linestyle=":")),
    ]
    labels = [item[0] for item in hl]
    handles = [item[1] for item in hl]
    fig.legend(handles, labels, bbox_to_anchor=(0.5, 0.985), loc="upper center", ncol=10)
    fig.tight_layout()
    if filename is not None:
        fig.savefig(filename)
    return fig
