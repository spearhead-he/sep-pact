"""Notebook interface of SEP-PACT: the parameters form, its widgets and the steps of the analysis.

SEPPACT_notebook is the interface of sep-pact.ipynb. The analysis itself is in analysis.py, its parameters in conf.py
and the plots in views.py.
"""
import html
import os
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import pandas as pd
from IPython.display import display
from ipywidgets import widgets
from matplotlib import pyplot as plt

from .analysis import SEPPACT
from .conf import SEPPACT_parameters
from .data import load_energies
from .inputs import (EVENT_LIST_LAYOUTS, count, event_list_layout, make_events, read_corrections, read_events,
                     shock_warnings)
from .shocks import SHOCK_FILE_FORMATS, SHOCK_SOURCES, combine_shocks, download_shocks, read_shock_file
from .views import PLOT_WIDTH, plot_background, plot_event, plot_height

# the resolutions that can be chosen, in minutes
RESOLUTION_CHOICES = (1, 2, 5, 10, 15, 30, 60)
# the first date range added in the form: the data of the example event
EXAMPLE_DATE_RANGE = (datetime(2021, 10, 31, 19), datetime(2021, 11, 3, 2, 5))
# the first custom shock added in the form, during the example event
EXAMPLE_SHOCK_TIME = datetime(2021, 11, 2, 12)
# spike threshold of a resolution without one in the parameters
DEFAULT_SPIKE_THRESHOLD = 2.0
# number of channels listed at once in the channel selection of a group
CHANNEL_ROWS = 8
# the meaning of the panel titles, shown with the plot of an event
TITLES_NOTE = ("Panel titles in red: channel groups without an onset (their flux is shown in the fallback viewing at the "
               "coarsest resolution). In orange: channel groups with the onset at the end of the background window, "
               "where the event may have started earlier. (corrected): an onset set below.")
# widths of the descriptions of the fields, in their own column, and of the fields
LABEL_WIDTH = "460px"
NUMBER_WIDTH = "100px"
TEXT_WIDTH = "420px"


def _figure_png(fig) -> bytes:
    """Returns a figure of views.py as a .png image, and closes it"""
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def _is_connection_error(error) -> bool:
    """Whether the error is a failed connection to a data server (e.g. aborted, refused, SSL error or timeout)"""
    return any(cls.__name__ in ("ConnectionError", "SSLError", "Timeout", "TimeoutError") for cls in type(error).__mro__)


def _error_text(text: str) -> str:
    return f'<span style="color: red"><b>Error:</b> {html.escape(text)}</span>'


def _note(text: str) -> widgets.HTML:
    return widgets.HTML(f"<i>{html.escape(text)}</i>")


def _set_enabled(widget, enabled: bool) -> None:
    """Grays out (or activates again) the widget and all the widgets in it"""
    if hasattr(widget, "disabled"):
        widget.disabled = not enabled
    for child in getattr(widget, "children", ()):
        _set_enabled(child, enabled)


def _while_busy(controls, wgt_status: widgets.HTML, message: str, work) -> None:
    """Runs work with the controls disabled and the message, with an hourglass, in wgt_status"""
    for control in controls:
        control.disabled = True
    wgt_status.value = html.escape(f"\u23f3 {message}")
    try:
        work()
    finally:
        for control in controls:
            control.disabled = False


def _section(title: str, *children) -> widgets.VBox:
    return widgets.VBox([widgets.HTML(f"<b>{title}</b>"), *children])


class SEPPACT_notebook:
    """Notebook interface of the SEP-PACT analysis: parameters_form(), then the steps run_data(),
    event_times(), run_analysis(), event_viewer() and save_results()

    The parameters are those of the form (parameters, a SEPPACT_parameters); the analysis (seppact, a SEPPACT) is
    created by run_data() with a copy of them, and keeps its results as attributes.
    """

    def __init__(self, parameters: SEPPACT_parameters | None = None) -> None:
        self.parameters = parameters if parameters is not None else SEPPACT_parameters()
        self.seppact = None
        self.save_plots = True
        # the input widget of each parameter of the form, and the errors of the values not accepted
        self.widgets = {}
        self.errors = {}
        # the channel groups of the form: [{"particle", "label", "channels", "reference"}], in the order of the plots
        self._groups = []
        self._energies = None
        # the note on the plot height, which depends on the panel height and the number of channel groups
        self._wgt_height_note = None
        # the shocks of the shock lists online, downloaded once: {source: times}
        self._online_shocks = {}
        self._style = {"description_width": "initial"}

    # the results of the analysis, for further work in the notebook
    @property
    def events(self) -> pd.DataFrame:
        return self.seppact.events

    @property
    def df_series(self) -> pd.DataFrame:
        return self.seppact.df_series

    @property
    def df_results(self) -> pd.DataFrame:
        return self.seppact.df_results

    @property
    def df_spikes(self) -> pd.DataFrame:
        return self.seppact.df_spikes

    # --- Parameters form ---
    def parameters_form(self) -> widgets.Tab:
        """All the parameters of the analysis, in tabs"""
        tabs = {
            "Events": self._events_tab(),
            "Data": self._data_tab(),
            "Energy channels": self._channels_tab(),
            "Onsets": self._onsets_tab(),
            "Peak and fluence": self._peak_fluence_tab(),
            "Plots and outputs": self._plots_tab(),
        }
        form = widgets.Tab(children=list(tabs.values()))
        for i, title in enumerate(tabs):
            form.set_title(i, title)
        return form

    def _set_parameter(self, parameter: str, value, wgt_error: widgets.HTML) -> bool:
        """Sets the parameter, or shows why the value is not accepted; returns whether it was set"""
        try:
            setattr(self.parameters, parameter, value)
        except (ValueError, TypeError) as e:
            self.errors[parameter] = str(e)
            wgt_error.value = _error_text(str(e))
            return False
        self.errors.pop(parameter, None)
        wgt_error.value = ""
        return True

    def _field(self, widget, parameter: str, to_parameter=lambda value: value, description: str = "") -> widgets.VBox:
        """The widget of a parameter, after its description, with the error of its value below it

        The description is in its own column, so that the width of the widget does not depend on it.
        """
        wgt_error = widgets.HTML()
        widget.observe(lambda traitlet: self._set_parameter(parameter, to_parameter(traitlet["new"]), wgt_error),
                       names="value")
        self.widgets[parameter] = widget
        row = widgets.HBox([widgets.HTML(html.escape(description), layout=widgets.Layout(width=LABEL_WIDTH)), widget]) \
            if description else widget
        return widgets.VBox([row, wgt_error])

    def _text(self, parameter: str, description: str, placeholder: str = "") -> widgets.VBox:
        widget = widgets.Text(value=getattr(self.parameters, parameter), placeholder=placeholder,
                              layout=widgets.Layout(width=TEXT_WIDTH))
        return self._field(widget, parameter, description=description)

    def _number(self, parameter: str, description: str, step: float = 1) -> widgets.VBox:
        # by the type of the parameter, e.g. a float parameter whose default is written as an integer
        widget_class = widgets.IntText if SEPPACT_parameters.__dataclass_fields__[parameter].type is int \
            else widgets.FloatText
        widget = widget_class(value=getattr(self.parameters, parameter), step=step,
                              layout=widgets.Layout(width=NUMBER_WIDTH))
        return self._field(widget, parameter, description=description)

    def _duration(self, parameter: str, description: str, unit: str) -> widgets.VBox:
        """A duration parameter (timedelta) as a number of minutes, hours or days"""
        widget = widgets.FloatText(value=getattr(self.parameters, parameter) / timedelta(**{unit: 1}),
                                   layout=widgets.Layout(width=NUMBER_WIDTH))
        return self._field(widget, parameter, lambda value: timedelta(**{unit: value}), f"{description} ({unit}):")

    # --- Events tab ---
    def _events_tab(self) -> widgets.VBox:
        wgt_ranges = self._date_ranges_widget()
        field_events = self._input_file("file_events", "Event list:", self._events_info,
                                        "Path to a CSV file - leave blank to use the date ranges below")

        def gray_out_ranges(_=None):
            # the date ranges are used only without an event list
            _set_enabled(wgt_ranges, not self.parameters.file_events)

        self.widgets["file_events"].observe(gray_out_ranges, names="value")
        gray_out_ranges()
        section_shocks = self._shocks_section()
        self.widgets["file_events"].observe(lambda _: self._update_shocks(), names="value")
        layouts = "; ".join(", ".join(columns) for columns in EVENT_LIST_LAYOUTS.values())
        return widgets.VBox([
            _section("Event list", field_events,
                     _note(f"A CSV file with the column Event No, then one of: {layouts}; optionally Particle and Sensor, "
                           "for the background windows of particles and sensors. See the user guide.")),
            _section("Date ranges, used without an event list", wgt_ranges),
            section_shocks,
            _section("Event windows",
                     self._duration("start_before_reference", "Data start before the Reference Time", "hours"),
                     self._duration("end_after_reference", "Data end after the Reference Time", "hours"),
                     _note("For event lists with a Reference Time."),
                     self._duration("bg_start_after_start", "Default background start after the Start Time", "minutes"),
                     self._duration("bg_end_after_start", "Default background end after the Start Time", "minutes"),
                     _note("For the events without a background window."),
                     self._duration("min_plot_window", "Shortest data period", "days")),
        ])

    def _input_file(self, parameter: str, description: str, info, placeholder: str) -> widgets.VBox:
        """The path of an input file, with what it contains or why it cannot be read"""
        field = self._text(parameter, description, placeholder)
        wgt_info = widgets.HTML(info(getattr(self.parameters, parameter)))
        self.widgets[parameter].observe(lambda traitlet: setattr(wgt_info, "value", info(traitlet["new"])),
                                        names="value")
        self.widgets[f"{parameter}_info"] = wgt_info
        return widgets.VBox([field, wgt_info])

    def _events_info(self, path: str) -> str:
        if not path:
            n = len(self.parameters.date_ranges)
            return html.escape(f"No event list: the {count(n, 'date range')} below {'is' if n == 1 else 'are'} used.")
        if not os.path.isfile(path):
            return _error_text(f"File not found: {path}")
        try:
            columns = pd.read_csv(path, nrows=0, index_col=0, skipinitialspace=True).columns.str.strip()
            layout = event_list_layout(path, list(columns))
            events = read_events(path, self.parameters)
        except (ValueError, KeyError) as e:
            return _error_text(str(e))
        return html.escape(f"{count(len(events), 'event')} ({layout}), from {events['Start Time'].min():%Y-%m-%d %H:%M} "
                           f"to {events['End Time'].max():%Y-%m-%d %H:%M}")

    def _date_ranges_widget(self) -> widgets.VBox:
        """One row with the start and end of each event, and a button to add events"""
        wrapper_rows = widgets.VBox()
        wgt_error = widgets.HTML()
        ranges = [list(date_range) for date_range in self.parameters.date_ranges]

        def apply():
            self._set_parameter("date_ranges", [tuple(date_range) for date_range in ranges], wgt_error)
            # the summary of the events, below the path of the event list, and the shocks during them
            if "file_events_info" in self.widgets:
                self.widgets["file_events_info"].value = self._events_info(self.parameters.file_events)
            if "shock_list" in self.widgets:
                self._update_shocks()

        def set_time(i, j, value):
            ranges[i][j] = value
            apply()

        def remove(i):
            del ranges[i]
            show_rows()
            apply()

        def add(_):
            ranges.append(list(ranges[-1]) if ranges else [EXAMPLE_DATE_RANGE[0], EXAMPLE_DATE_RANGE[1]])
            show_rows()
            apply()

        def show_rows():
            rows = []
            for i, (start, end) in enumerate(ranges):
                wgt_start = widgets.NaiveDatetimePicker(value=start, description=f"Event {i + 1} start:",
                                                        style=self._style)
                wgt_start.observe(lambda traitlet, i=i: set_time(i, 0, traitlet["new"]), names="value")
                wgt_end = widgets.NaiveDatetimePicker(value=end, description="end:", style=self._style)
                wgt_end.observe(lambda traitlet, i=i: set_time(i, 1, traitlet["new"]), names="value")
                btn_remove = widgets.Button(description="Remove event", tooltip=f"Remove event {i + 1}")
                btn_remove.on_click(lambda _, i=i: remove(i))
                rows.append(widgets.HBox([wgt_start, wgt_end, btn_remove]))
            wrapper_rows.children = rows

        btn_add = widgets.Button(description="Add event")
        btn_add.on_click(add)
        show_rows()
        self.widgets["date_ranges"] = wrapper_rows
        self.widgets["add_event"] = btn_add
        return widgets.VBox([wrapper_rows, btn_add, wgt_error])

    # --- Shocks, in the Events tab ---
    def _shocks_section(self) -> widgets.VBox:
        """The shock list online, the shock list file and the custom shocks, with what each one has, and the list of
        the shocks during the events, from which shocks can be removed"""
        wgt_source = widgets.Dropdown(options=[(name, name) for name in SHOCK_SOURCES] + [("None", None)],
                                      value=self.parameters.shock_source, layout=widgets.Layout(width=NUMBER_WIDTH))
        field_source = self._field(wgt_source, "shock_source", description="Shock list online:")
        field_file = self._text("file_shocks", "Shock list file:", "Path to a file - leave blank for none")
        wgt_list = widgets.SelectMultiple(rows=8, layout=widgets.Layout(width=TEXT_WIDTH))
        btn_remove = widgets.Button(description="Remove selected", tooltip="Leave the selected shocks out")
        btn_restore = widgets.Button(description="Restore all", tooltip="Use all the shocks again")
        wgt_error = widgets.HTML()

        def remove(_):
            removed = self.parameters.removed_shocks + [t.to_pydatetime() for t in wgt_list.value]
            self._set_parameter("removed_shocks", removed, wgt_error)
            self._update_shocks()

        def restore(_):
            self._set_parameter("removed_shocks", [], wgt_error)
            self._update_shocks()

        btn_remove.on_click(remove)
        btn_restore.on_click(restore)
        self.widgets.update({"shock_source_info": widgets.HTML(), "file_shocks_info": widgets.HTML(),
                             "shock_list": wgt_list, "remove_shocks": btn_remove, "restore_shocks": btn_restore,
                             "shock_list_info": widgets.HTML()})
        wgt_times = self._shock_times_widget()
        for parameter in ("shock_source", "file_shocks"):
            self.widgets[parameter].observe(lambda _: self._update_shocks(), names="value")
        self._update_shocks()
        sources = "; ".join(SHOCK_SOURCES.values())
        return _section("Shocks",
                        _note("The analysis of a channel group ends at the first shock after its onset. The shocks are "
                              "those of the shock list online, of the shock list file and the custom ones."),
                        field_source, self.widgets["shock_source_info"], _note(f"Shock lists online: {sources}."),
                        field_file, self.widgets["file_shocks_info"],
                        _note(f"The file is {', or '.join(SHOCK_FILE_FORMATS)}; inputs/ has an example of each "
                              "(shocks_ipshocks_example.dat, shocks_irfu_example.txt, shocks_example.csv)."),
                        widgets.HTML("Custom shocks:"), wgt_times,
                        widgets.HTML("Shocks during the events (select several with Ctrl+click):"), wgt_list,
                        widgets.HBox([btn_remove, btn_restore]), wgt_error, self.widgets["shock_list_info"])

    def _shock_times_widget(self) -> widgets.VBox:
        """One row with each custom shock time, and a button to add shocks"""
        wrapper_rows = widgets.VBox()
        wgt_error = widgets.HTML()
        times = list(self.parameters.shock_times)

        def apply():
            self._set_parameter("shock_times", [t for t in times if t is not None], wgt_error)
            self._update_shocks()

        def set_time(i, value):
            times[i] = value
            apply()

        def remove(i):
            del times[i]
            show_rows()
            apply()

        def add(_):
            times.append(times[-1] if times and times[-1] is not None else EXAMPLE_SHOCK_TIME)
            show_rows()
            apply()

        def show_rows():
            rows = []
            for i, time in enumerate(times):
                wgt_time = widgets.NaiveDatetimePicker(value=time, description=f"Shock {i + 1}:", style=self._style)
                wgt_time.observe(lambda traitlet, i=i: set_time(i, traitlet["new"]), names="value")
                btn_remove = widgets.Button(description="Remove shock", tooltip=f"Remove shock {i + 1}")
                btn_remove.on_click(lambda _, i=i: remove(i))
                rows.append(widgets.HBox([wgt_time, btn_remove]))
            wrapper_rows.children = rows

        btn_add = widgets.Button(description="Add shock")
        btn_add.on_click(add)
        show_rows()
        self.widgets["shock_times"] = wrapper_rows
        self.widgets["add_shock"] = btn_add
        return widgets.VBox([wrapper_rows, btn_add, wgt_error])

    @staticmethod
    def _shocks_text(times: pd.Series, what: str) -> str:
        return html.escape(f"{count(len(times), 'shock')} in {what}, from {times.min():%Y-%m-%d} to {times.max():%Y-%m-%d}.")

    def _shock_sources(self) -> dict:
        """Returns the times of the shocks of each source of the form, {source: times}, and shows what each one has,
        or why it cannot be read"""
        p, sources = self.parameters, {}
        info_source, info_file = self.widgets["shock_source_info"], self.widgets["file_shocks_info"]
        info_source.value = html.escape("No shock list online.")
        if p.shock_source:
            try:
                if p.shock_source not in self._online_shocks:
                    self._online_shocks[p.shock_source] = download_shocks(p.shock_source)
                sources[p.shock_source] = self._online_shocks[p.shock_source]
                info_source.value = self._shocks_text(sources[p.shock_source], f"{p.shock_source} (Solar Orbiter)")
            except (OSError, ValueError) as e:
                info_source.value = _error_text(f"The shock list {p.shock_source} could not be downloaded ({e}). "
                                                "The data server may be unavailable; try again later.")
        info_file.value = html.escape("No shock list file.")
        if p.file_shocks:
            try:
                sources[os.path.basename(p.file_shocks)] = read_shock_file(p.file_shocks)
                info_file.value = self._shocks_text(sources[os.path.basename(p.file_shocks)], "the file")
            except (OSError, ValueError, KeyError) as e:
                info_file.value = _error_text(str(e))
        if p.shock_times:
            sources["custom"] = pd.Series(pd.to_datetime(p.shock_times), dtype="datetime64[ns]")
        return sources

    def _update_shocks(self) -> None:
        """Shows the shocks during the events (all of them without valid events), the number of removed shocks and the
        warnings about the shocks"""
        sources = self._shock_sources()
        shocks = combine_shocks(sources, self.parameters.removed_shocks)
        n_removed = len(combine_shocks(sources)) - len(shocks)
        try:
            # without the messages of the event list, which its summary shows
            with redirect_stdout(StringIO()):
                events = make_events(self.parameters)
        except (ValueError, KeyError, OSError):
            events = None
        during = shocks
        if events is not None:
            in_events = shocks["Shock Time"].map(lambda t: ((events["Plot Start"] <= t) & (events["Plot End"] >= t)).any())
            during = shocks[in_events.astype(bool)]
        self.widgets["shock_list"].options = [(f"{t:%Y-%m-%d %H:%M:%S} ({source})", t)
                                              for t, source in zip(during["Shock Time"], during["Source"])]
        lines = [html.escape(f"{count(len(during), 'shock')} during the events" if events is not None
                             else f"{count(len(during), 'shock')} (the events cannot be read)")
                 + html.escape(f"; {count(n_removed, 'shock')} removed." if n_removed else ".")]
        if events is not None:
            lines += [f'<span style="color: darkorange">{html.escape(w)}</span>' for w in shock_warnings(shocks, events)]
        self.widgets["shock_list_info"].value = "<br>".join(lines)

    @staticmethod
    def _corrections_info(path: str) -> str:
        if not path:
            return html.escape("No corrections: the onsets are chosen automatically.")
        if not os.path.isfile(path):
            return _error_text(f"File not found: {path}")
        try:
            corrections, _ = read_corrections(path)
        except (ValueError, KeyError) as e:
            return _error_text(str(e))
        return html.escape(f"{count(len(corrections), 'correction')}, applied after the automatic choice.")

    # --- Data tab ---
    def _data_tab(self) -> widgets.VBox:
        return widgets.VBox([
            _section("Viewings", self._viewings_widget()),
            _section("Resolutions, and the spike threshold of each (orders of magnitude)", self._resolutions_widget()),
            _section("Download",
                     self._text("dir_data", "Data folder:", "Folder of the downloaded EPD files"),
                     self._text("dir_saves", "Cache folder:", "Folder of the cached flux"),
                     self._number("download_tries", "Download tries:")),
        ])

    def _viewings_widget(self) -> widgets.VBox:
        wgt_error = widgets.HTML()
        checkboxes = {viewing: widgets.Checkbox(value=viewing in self.parameters.viewings, description=viewing,
                                                indent=False, layout=widgets.Layout(width="max-content"))
                      for viewing in SEPPACT_parameters.VIEWINGS}

        def update(_):
            # in the order of VIEWINGS
            self._set_parameter("viewings", [v for v, checkbox in checkboxes.items() if checkbox.value], wgt_error)

        for checkbox in checkboxes.values():
            checkbox.observe(update, names="value")
        self.widgets["viewings"] = checkboxes
        return widgets.VBox([widgets.HBox(list(checkboxes.values())), wgt_error])

    def _resolutions_widget(self) -> widgets.VBox:
        """One row per resolution: whether it is used, and its spike threshold"""
        wgt_error = widgets.HTML()
        choices = sorted(set(RESOLUTION_CHOICES) | {int(f / timedelta(minutes=1)) for f in self.parameters.resample_freqs})
        rows = {}
        for minutes in choices:
            resolution = timedelta(minutes=minutes)
            rows[minutes] = (
                widgets.Checkbox(value=resolution in self.parameters.resample_freqs, description=f"{minutes} min",
                                 indent=False, layout=widgets.Layout(width="80px")),
                widgets.FloatText(value=self.parameters.spike_thresholds.get(resolution, DEFAULT_SPIKE_THRESHOLD),
                                  step=0.5, layout=widgets.Layout(width=NUMBER_WIDTH)),
            )

        def update(_):
            selected = [minutes for minutes, (checkbox, _) in rows.items() if checkbox.value]
            for checkbox, threshold in rows.values():
                threshold.disabled = not checkbox.value
            self.parameters.spike_thresholds = {timedelta(minutes=m): rows[m][1].value for m in selected}
            self._set_parameter("resample_freqs", [timedelta(minutes=m) for m in selected], wgt_error)

        for checkbox, threshold in rows.values():
            checkbox.observe(update, names="value")
            threshold.observe(update, names="value")
            threshold.disabled = not checkbox.value
        self.widgets["resample_freqs"] = rows
        return widgets.VBox([widgets.HBox([checkbox, widgets.HTML("spike threshold:"), threshold])
                             for checkbox, threshold in rows.values()] + [wgt_error])

    # --- Energy channels tab ---
    def _channels_tab(self) -> widgets.VBox:
        self._wrapper_channels = widgets.VBox([self._channels_section()])
        return self._wrapper_channels

    def _read_energies(self) -> str:
        """Reads the energies of the HET channels from the data of the first event; returns the error, if any"""
        self._energies = None
        try:
            events = make_events(self.parameters)
            self._energies = load_energies({"HET"}, self.parameters.level, events.iloc[0]["Plot Start"],
                                           events.iloc[0]["Plot End"], self.parameters.viewings[0],
                                           self.parameters.dir_data)["HET"]
        except Exception as e:
            if _is_connection_error(e):
                advice = "the data server may be unavailable, read the channels again later."
            else:
                advice = "check the events, then read the channels again."
            return f"{e}. The energies of the HET channels could not be read from the data of the first event: {advice}"
        return ""

    def _channels_section(self) -> widgets.VBox:
        error = self._read_energies()
        self._groups = [{"particle": particle, "label": label, "channels": list(spec["channels"]),
                         "reference": "reference_channel" in spec}
                        for particle, groups in self.parameters.group_options.items() for label, spec in groups.items()]
        wgt_groups = self._channel_groups_widget()
        if not error:
            return _section("Channel groups (select several channels with Ctrl+click)", wgt_groups)
        btn_retry = widgets.Button(description="Read the channels again", layout=widgets.Layout(width="max-content"))
        btn_retry.on_click(lambda _: setattr(self._wrapper_channels, "children", [self._channels_section()]))
        # without the energies of the channels the groups cannot be changed
        for button in wgt_groups.children[0].children:
            button.disabled = True
        return _section("Channel groups", widgets.HBox([widgets.HTML(_error_text(error)), btn_retry]),
                        widgets.VBox([self._group_text(group) for group in self._groups]))

    @staticmethod
    def _group_text(group: dict) -> widgets.HTML:
        reference = ", reference channel" if group["reference"] else ""
        channels = ", ".join(map(str, group["channels"]))
        return widgets.HTML(html.escape(f"{group['label']} {group['particle']}: channels {channels}{reference}"))

    def _channel_options(self, particle: str) -> list:
        """The channels of the particle, with their energy range"""
        energies = self._energies[particle]
        return [(f"{c}: {row['Low Energy']:.4g} - {row['Low Energy'] + row['Bin Width']:.4g} MeV", c)
                for c, row in energies.iterrows()]

    def _channel_groups_widget(self) -> widgets.VBox:
        """One row per channel group, with buttons to add and remove groups"""
        wrapper_rows = widgets.VBox()
        wgt_error = widgets.HTML()

        def apply():
            self._apply_groups(wgt_error)

        def show_rows():
            wrapper_rows.children = [self._group_row(group, apply, remove) for group in self._groups]

        def remove(group):
            self._groups.remove(group)
            show_rows()
            apply()

        def add(particle):
            number = 1 + sum(group["particle"] == particle for group in self._groups)
            # after the last group of the particle, to keep the groups of a particle together
            position = max([i + 1 for i, group in enumerate(self._groups) if group["particle"] == particle], default=0)
            self._groups.insert(position, {"particle": particle, "label": f"{particle} group {number}", "channels": [],
                                           "reference": False})
            show_rows()
            apply()

        buttons = []
        for particle in SEPPACT_parameters.PARTICLES:
            button = widgets.Button(description=f"Add {particle[:-1]} group", layout=widgets.Layout(width="max-content"))
            button.on_click(lambda _, particle=particle: add(particle))
            buttons.append(button)
        if self._energies is not None:
            show_rows()
        self.widgets["group_options"] = wrapper_rows
        return widgets.VBox([widgets.HBox(buttons), wrapper_rows, wgt_error])

    def _group_row(self, group: dict, apply, remove) -> widgets.HBox:
        """The particle, label, channels and reference flag of a channel group, and a button to remove it"""
        wgt_label = widgets.Text(value=group["label"], description="Label:", style={"description_width": "initial"},
                                 layout=widgets.Layout(width="260px"))
        # channels missing from the data are left out
        available = self._energies[group["particle"]].index
        wgt_channels = widgets.SelectMultiple(options=self._channel_options(group["particle"]),
                                              value=[c for c in group["channels"] if c in available],
                                              rows=CHANNEL_ROWS, layout=widgets.Layout(width="260px"))
        wgt_reference = widgets.Checkbox(value=group["reference"], description="Reference channel", indent=False,
                                         layout=widgets.Layout(width="max-content"))
        btn_remove = widgets.Button(description="Remove", tooltip=f"Remove {group['label']}")
        group["widgets"] = {"label": wgt_label, "channels": wgt_channels, "reference": wgt_reference}

        def set_value(key, value):
            group[key] = list(value) if key == "channels" else value
            if key == "reference" and value:
                # at most one reference channel
                for other in self._groups:
                    if other is not group and other["reference"]:
                        other["reference"] = False
                        other["widgets"]["reference"].value = False
            apply()

        for key, widget in group["widgets"].items():
            widget.observe(lambda traitlet, key=key: set_value(key, traitlet["new"]), names="value")
        btn_remove.on_click(lambda _: remove(group))
        return widgets.HBox([widgets.HTML(f"<b>{group['particle']}</b>", layout=widgets.Layout(width="80px")),
                             widgets.VBox([wgt_label, wgt_reference, btn_remove]), wgt_channels],
                            layout=widgets.Layout(border="solid 1px", margin="2px", padding="4px"))

    def _apply_groups(self, wgt_error: widgets.HTML) -> None:
        """Sets group_options from the channel groups of the form, or shows why they are not accepted"""
        group_options = {}
        for group in self._groups:
            groups = group_options.setdefault(group["particle"], {})
            label = group["label"].strip()
            if not label or label in groups:
                error = f"Each group of {group['particle']} needs its own label; {label!r} is empty or repeated."
                self.errors["group_options"] = error
                wgt_error.value = _error_text(error)
                return
            groups[label] = {"sensor": "HET", "channels": sorted(group["channels"])}
            if group["reference"]:
                groups[label]["reference_channel"] = True
        if self._set_parameter("group_options", group_options, wgt_error):
            self._update_height_note()

    # --- Onsets, peak and fluence tabs ---
    def _onsets_tab(self) -> widgets.VBox:
        return widgets.VBox([
            _section("Onset detection",
                     self._number("onset_sigma", "Threshold, in standard deviations above the background:", 0.5),
                     self._number("onset_points", "Consecutive points above the threshold:"),
                     self._duration("reference_onset_window", "Largest distance from the reference onset", "hours")),
            _section("Data quality after the onset",
                     self._number("quality_tolerance", "Largest ratio of transitions to zero or missing values:", 0.05),
                     self._field(widgets.Checkbox(value=self.parameters.quality_adjustable, indent=False,
                                                  description="Tolerance grows with the resolution",
                                                  layout=widgets.Layout(width="max-content")),
                                 "quality_adjustable")),
            _section("Onset corrections",
                     self._input_file("file_corrections", "Corrections file:", self._corrections_info,
                                      "Path to a file saved in the Events step, or empty")),
        ])

    def _peak_fluence_tab(self) -> widgets.VBox:
        return widgets.VBox([
            _section("Peak flux",
                     self._duration("peak_window_min", "Search in the first half of the event if it is at least",
                                    "hours")),
            _section("Fluence",
                     self._number("fluence_peak_fraction", "Fluence threshold, as a fraction of the peak flux:", 0.1),
                     self._number("fluence_points", "Consecutive points at or below the threshold that bound the "
                                                    "interval:"),
                     _note("The fluence is the integral of the flux from where it last rises above the threshold "
                           "before the peak to where it first falls back to it after the peak.")),
        ])

    def _plots_tab(self) -> widgets.VBox:
        wgt_fallback = widgets.Dropdown(options=SEPPACT_parameters.VIEWINGS, value=self.parameters.fallback_viewing,
                                        layout=widgets.Layout(width=NUMBER_WIDTH))
        wgt_save = widgets.Checkbox(value=self.save_plots, description="Save the plots of the events", indent=False,
                                    layout=widgets.Layout(width="max-content"))
        wgt_save.observe(lambda traitlet: setattr(self, "save_plots", traitlet["new"]), names="value")
        self.widgets["save_plots"] = wgt_save
        self._wgt_height_note = widgets.HTML()
        field_height = self._number("panel_height", "Height of the panel of each channel group (inches):", 0.5)
        self.widgets["panel_height"].observe(lambda _: self._update_height_note(), names="value")
        self._update_height_note()
        return widgets.VBox([
            _section("Plots", self._field(wgt_fallback, "fallback_viewing",
                                          description="Viewing of channel groups without an onset:"),
                     field_height, self._wgt_height_note, wgt_save),
            _section("Outputs",
                     self._text("dir_plots", "Plots folder:", "Folder of the plots, one per event"),
                     self._text("dir_outputs", "Results folder:", "Folder of results.csv")),
        ])

    def _height_note(self) -> str:
        """What the panel height gives: the size of the plots, and whether the height is in the recommended range"""
        p = self.parameters
        low, high = SEPPACT_parameters.RECOMMENDED_PANEL_HEIGHTS
        n_groups = sum(len(groups) for groups in p.group_options.values())
        note = (f"Recommended: {low} to {high} inches. With {count(n_groups, 'channel group')}, the plots are "
                f"{PLOT_WIDTH} inches wide and {plot_height(p.panel_height, n_groups):g} inches high (the panels, and "
                "the title, legend and axis labels).")
        if p.panel_height < low:
            warning = "Below the recommended height, the labels in a panel overlap."
        elif p.panel_height > high:
            warning = "Above the recommended height, the plots are hard to view on a screen."
        else:
            return f"<i>{html.escape(note)}</i>"
        return f'<i>{html.escape(note)}</i><br><span style="color: darkorange"><b>Note:</b> {html.escape(warning)}</span>'

    def _update_height_note(self) -> None:
        if self._wgt_height_note is not None:
            self._wgt_height_note.value = self._height_note()

    # --- Steps ---
    def _form_errors(self) -> bool:
        """Shows the values of the form that are not accepted, if any; returns whether there are any"""
        if not self.errors:
            return False
        display(widgets.HTML("<br>".join(_error_text(f"{parameter}: {error}")
                                         for parameter, error in self.errors.items())
                             + "<br>Correct the parameters, then run this step again."))
        return True

    def run_data(self) -> None:
        """Reads the event list and the shock list, and downloads (or loads) the flux of the channel groups"""
        if self._form_errors():
            return
        try:
            self.seppact = SEPPACT(deepcopy(self.parameters))
            self.seppact.run_inputs()
            self.seppact.run_data()
        except Exception as e:
            self.seppact = None
            advice = " The data server may be unavailable; try again later." if _is_connection_error(e) else ""
            display(widgets.HTML(_error_text(f"{e}.{advice}")))
            return
        display(self.seppact.events)

    def _has_data(self) -> bool:
        """Whether the data step has run; shows an error if not"""
        if self.seppact is None or self.seppact.dfs_flux is None:
            display(widgets.HTML(_error_text("There are no data: run the data step first.")))
            return False
        return True

    def _event_choice(self, subset: list, subset_description: str) -> tuple[widgets.Checkbox, widgets.Dropdown]:
        """The event dropdown, with the event numbers and start times, and the checkbox that limits it to the subset
        of events; the first event is chosen, also without a click"""
        events = self.seppact.events
        wgt_subset = widgets.Checkbox(value=False, indent=False, layout=widgets.Layout(width="max-content"),
                                      description=f"Only the {count(len(subset), 'event')} {subset_description}")
        wgt_event = widgets.Dropdown(description="Event:", style=self._style)

        def set_options(_=None):
            numbers = subset if wgt_subset.value else list(events.index)
            wgt_event.options = [(f"{n} ({events.loc[n, 'Start Time']:%Y-%m-%d %H:%M})", n) for n in numbers]
            wgt_event.value = numbers[0] if numbers else None

        set_options()
        wgt_subset.observe(set_options, names="value")
        return wgt_subset, wgt_event

    def _window_options(self) -> list[tuple]:
        """The options of the window dropdown: the event, then each particle with more than one sensor and each
        particle and sensor of the channel groups, as (label, (particle, sensor))"""
        tool = self.seppact
        options = [("Event", ("", ""))]
        for particle in tool.particles:
            sensors = sorted(tool.sensors[particle])
            if len(sensors) > 1:
                options.append((f"{particle} (all sensors)", (particle, "")))
            options += [(f"{particle} {sensor}", (particle, sensor)) for sensor in sensors]
        return options

    def _times_status(self, event_no: int) -> str:
        """The background windows and the end time of an event, where they come from, the points of each window at each
        resolution and its warnings"""
        tool = self.seppact
        users = tool.bg_window_series(event_no)
        lines = []
        for key in [("", ""), *[key[1:] for key in tool.bg_windows.own_windows(event_no)]]:
            window = tool.bg_window(event_no, *key)
            of = f" of {' '.join(filter(None, key))}" if key[0] else ""
            text = f"Background{of} {window.start:%Y-%m-%d %H:%M} to {window.end:%Y-%m-%d %H:%M} ({window.source})"
            if key in users:
                counts = [tool.bg_window_points(event_no, *pair) for pair in users[key]]
                text += "; points: " + ", ".join(f"{min(count[freq] for count in counts)} at {freq.total_seconds() / 60:g} "
                                                 "min" for freq in tool.params.resample_freqs)
            lines.append(html.escape(text + "."))
        event = tool.events.loc[event_no]
        lines.append(html.escape(f"End time {event['End Time']:%Y-%m-%d %H:%M} ({event['End Time Source']})."))
        lines += [f'<span style="color: red">{html.escape(warning)}</span>' for warning in tool.bg_window_warnings(event_no)]
        if tool.df_series is not None:
            lines.append("<b>Run the analysis step again to use the changed times.</b>")
        return "<br>".join(lines)

    def _time_slider_points(self, event_no: int, key: tuple = ("", "")) -> tuple:
        """The times and indices of the sliders of an event, its data points at the finest resolution (of the particle
        and sensor of the window, or of the first ones): from the start to the end time for the background window of
        key (particle, sensor), with the points of the window (the closest ones inside it), and after all the
        background windows of the event to the end of the data for the end time, with the point of the end time (the
        closest one before it)"""
        tool = self.seppact
        event = tool.events.loc[event_no]
        particle = key[0] or next(iter(tool.particles))
        sensor = key[1] or sorted(tool.sensors[particle])[0]
        times = tool.dfs_flux[particle][sensor][tool.params.resample_freqs[0]].loc[event_no].index
        window = tool.bg_window(event_no, *key)
        bg_times = times[(times >= event["Start Time"]) & (times < event["End Time"])]
        i_start = min(int(bg_times.searchsorted(window.start)), len(bg_times) - 1)
        i_end = max(int(bg_times.searchsorted(window.end, side="right")) - 1, i_start)
        last_bg_end = tool.bg_windows.to_frame().xs(event_no, level="Event No")["BG End"].max()
        end_times = times[(times > last_bg_end) & (times <= event["Plot End"])]
        i_end_time = max(int(end_times.searchsorted(event["End Time"], side="right")) - 1, 0)
        return bg_times, (i_start, i_end), end_times, i_end_time

    def _save_events_widget(self) -> widgets.VBox:
        """The path of the event list with the times of the events and its Save button"""
        wgt_path = widgets.Text(value=os.path.join(self.seppact.params.dir_outputs, "events.csv"),
                                description="Event list:", style=self._style, layout=widgets.Layout(width=TEXT_WIDTH))
        btn_save = widgets.Button(description="Save", tooltip="Write the events with their times as an event list")
        wgt_saved = widgets.HTML()

        def save(_):
            try:
                if folder := os.path.dirname(wgt_path.value):
                    os.makedirs(folder, exist_ok=True)
                self.seppact.save_events(wgt_path.value)
            except OSError as e:
                wgt_saved.value = _error_text(str(e))
                return
            wgt_saved.value = html.escape(f"Saved the event list to {wgt_path.value}; give it as the event list to use "
                                          "these times again.")

        btn_save.on_click(save)
        self.widgets.update({"events_path": wgt_path, "save_events": btn_save, "events_saved": wgt_saved})
        return widgets.VBox([widgets.HBox([wgt_path, btn_save]), wgt_saved])

    def event_times(self) -> None:
        """The background windows and the end time of the event chosen in the dropdown, set with the sliders, and its
        plot

        The window dropdown chooses the window of the event, or of a particle and sensor. The sliders go over the data
        points of the event at the finest resolution: from the start to the end time for the background window, and
        from the end of the background windows to the end of the data for the end time.
        """
        if not self._has_data():
            return
        tool = self.seppact
        wgt_warned, wgt_event = self._event_choice([n for n in tool.events.index if tool.bg_window_warnings(n)],
                                                   "with background warnings")
        wgt_window = widgets.Dropdown(options=self._window_options(), value=("", ""), description="Window of:",
                                      style=self._style)
        wgt_bg = widgets.SelectionRangeSlider(options=[("", None)], description="Background:", continuous_update=False,
                                              style=self._style, layout=widgets.Layout(width="95%"))
        # a slider needs an option before it gets the times of the event
        wgt_end = widgets.SelectionSlider(options=[("", 0)], description="End time:", continuous_update=False,
                                          style=self._style, layout=widgets.Layout(width="95%"))
        btn_reset = widgets.Button(description="Reset", tooltip="The window of the event list, or the default one; for "
                                   "the event, also its end time")
        wgt_status = widgets.HTML()
        wgt_plot = widgets.Image(format="png", layout=widgets.Layout(max_width="100%", height="auto"))
        # the sliders are not applied to the event while they are set to the event's times
        updating = {"sliders": False}

        def show_event(_=None):
            if wgt_event.value is None:
                wgt_status.value, wgt_plot.value = "", b""
                return
            bg_times, bg_index, end_times, end_index = self._time_slider_points(wgt_event.value, wgt_window.value)
            updating["sliders"] = True
            wgt_bg.options = [(f"{t:%Y-%m-%d %H:%M}", t) for t in bg_times]
            wgt_bg.index = bg_index
            wgt_end.options = [(f"{t:%Y-%m-%d %H:%M}", t) for t in end_times]
            wgt_end.index = end_index
            updating["sliders"] = False
            wgt_status.value = self._times_status(wgt_event.value)
            wgt_plot.value = _figure_png(plot_background(tool, wgt_event.value))

        def set_time(set_event_time, *values):
            if updating["sliders"]:
                return
            try:
                set_event_time(wgt_event.value, *values)
            except ValueError as e:
                wgt_status.value = _error_text(str(e))
                return
            # the windows limit the end time, and the end time the windows
            show_event()

        def reset(_):
            tool.reset_bg_window(wgt_event.value, *wgt_window.value)
            if wgt_window.value == ("", ""):
                tool.reset_end_time(wgt_event.value)
            show_event()

        self.widgets.update({"bg_warned_only": wgt_warned, "bg_event": wgt_event, "bg_window_of": wgt_window,
                             "bg_window": wgt_bg, "end_time": wgt_end, "bg_reset": btn_reset, "bg_status": wgt_status,
                             "bg_plot": wgt_plot})
        wgt_event.observe(show_event, names="value")
        wgt_window.observe(show_event, names="value")
        wgt_bg.observe(lambda change: set_time(tool.set_bg_window, *change["new"], *wgt_window.value), names="value")
        wgt_end.observe(lambda change: set_time(tool.set_end_time, change["new"]), names="value")
        btn_reset.on_click(reset)
        show_event()
        display(widgets.VBox([wgt_warned, widgets.HBox([wgt_event, wgt_window, btn_reset]), wgt_bg, wgt_end, wgt_status,
                              wgt_plot, self._save_events_widget()]))

    def run_analysis(self) -> None:
        """Runs the onsets, spikes, peak flux and fluence steps, and summarises the chosen onsets"""
        if not self._has_data():
            return
        steps = [("Onsets", self.seppact.run_onsets), ("Spikes", self.seppact.run_spikes),
                 ("Peak flux", self.seppact.run_peaks), ("Fluence", self.seppact.run_fluences)]
        progress = widgets.IntProgress(value=0, max=len(steps), description="Analysis:", style=self._style)
        wgt_step = widgets.Label()
        display(widgets.HBox([progress, wgt_step]))
        for name, step in steps:
            wgt_step.value = f"{name}..."
            step()
            progress.value += 1
        wgt_step.value = "done"
        display(widgets.HTML(html.escape(self._summary())))

    def _summary(self) -> str:
        results = self.seppact.df_results
        copied = results["Onset Copied"].eq(True).sum()
        at_bg_end = results["Onset at BG End"].eq(True).sum()
        return (f"{results['Onset Time'].notna().sum()} of {len(results)} channel groups "
                f"({count(len(self.seppact.events), 'event')}) have an onset: {copied} copied from the reference "
                f"channel, and {at_bg_end} at the end of the background window.")

    def _flagged_events(self) -> list:
        """The events with a channel group whose onset is copied or at the end of the background window"""
        results = self.seppact.df_results
        flagged = (results["Onset Copied"].eq(True) | results["Onset at BG End"].eq(True)).groupby(level="Event No").any()
        return list(flagged[flagged].index)

    @staticmethod
    def _onset_option(resolution, viewing: str, row: pd.Series) -> str:
        """The label of a detected onset in the onset dropdown"""
        notes = [note for note, flag in (("not usable", not row["Usable"]), ("copied", row["Onset Copied"])) if flag]
        return (f"{row['Onset Time']:%Y-%m-%d %H:%M}, {resolution.total_seconds() / 60:g} min, {viewing}"
                + (f" ({', '.join(notes)})" if notes else ""))

    def _onset_correction_widget(self, wgt_event: widgets.Dropdown, refresh) -> widgets.VBox:
        """The channel group of the event and its onset: one of the detected onsets of its series, or no onset; refresh
        is called after a change"""
        tool = self.seppact
        wgt_group = widgets.Dropdown(description="Channel group:", style=self._style)
        wgt_onset = widgets.Dropdown(description="Onset:", style=self._style, layout=widgets.Layout(width=TEXT_WIDTH))
        btn_reset = widgets.Button(description="Reset to automatic", tooltip="The automatically chosen onset")
        wgt_status = widgets.HTML()
        # the dropdowns are not applied while they are set to the onset of the group
        updating = {"onset": False}

        def show_onset():
            key = (wgt_event.value, *wgt_group.value)
            # the rows of the channel group, indexed by (resolution, viewing)
            rows = dict(tool._iter_channel_rows(wgt_event.value))[key]
            chosen = tool.df_results.loc[key]
            updating["onset"] = True
            wgt_onset.options = [("No onset", None)] + [
                (self._onset_option(resolution, viewing, row), (resolution, viewing))
                for (resolution, viewing), row in rows.iterrows() if not pd.isna(row["Onset Time"])]
            wgt_onset.value = None if pd.isna(chosen["Onset Resolution"]) else \
                (chosen["Onset Resolution"], chosen["Onset Viewing"])
            updating["onset"] = False
            wgt_status.value = "Corrected" if key in tool.corrections else "Chosen automatically"

        def show_groups(_=None):
            if wgt_event.value is None:
                wgt_group.options = []
                return
            keys = list(tool.df_results.loc[wgt_event.value].index)
            wgt_group.options = [(f"{key[2]} {key[0]}/{key[1]}", key) for key in keys]
            # the first channel group, also when it was already chosen in the previous event
            if wgt_group.value != keys[0]:
                wgt_group.value = keys[0]
            else:
                show_onset()

        def recalculate(correct):
            """Applies the correction, with a busy note while the event is calculated again and its plot drawn"""
            _while_busy((wgt_group, wgt_onset, btn_reset), wgt_status,
                        f"Calculating the peak flux and fluence of event {wgt_event.value} again, and drawing its plot...",
                        lambda: (correct(), refresh()))
            show_onset()

        def set_onset(change):
            if not updating["onset"]:
                recalculate(lambda: tool.set_onset(wgt_event.value, *wgt_group.value, *(change["new"] or (None, None))))

        def reset(_):
            recalculate(lambda: tool.reset_onset(wgt_event.value, *wgt_group.value))

        wgt_group.observe(lambda _: show_onset() if wgt_group.value is not None else None, names="value")
        wgt_event.observe(show_groups, names="value")
        wgt_onset.observe(set_onset, names="value")
        btn_reset.on_click(reset)
        show_groups()
        self.widgets.update({"group": wgt_group, "onset": wgt_onset, "onset_reset": btn_reset, "onset_status": wgt_status})
        return widgets.VBox([widgets.HBox([wgt_group, wgt_onset, btn_reset]), wgt_status, _note(TITLES_NOTE)])

    def _save_corrections_widget(self) -> widgets.VBox:
        """The path of the onset corrections and their Save button"""
        wgt_path = widgets.Text(value=os.path.join(self.seppact.params.dir_outputs, "corrections.csv"),
                                description="Corrections:", style=self._style, layout=widgets.Layout(width=TEXT_WIDTH))
        btn_save = widgets.Button(description="Save", tooltip="Write the onset corrections")
        wgt_saved = widgets.HTML()

        def save(_):
            try:
                if folder := os.path.dirname(wgt_path.value):
                    os.makedirs(folder, exist_ok=True)
                self.seppact.save_corrections(wgt_path.value)
            except OSError as e:
                wgt_saved.value = _error_text(str(e))
                return
            wgt_saved.value = html.escape(f"Saved {count(len(self.seppact.corrections), 'correction')} to "
                                          f"{wgt_path.value}; give it as the corrections file (Onsets tab) to apply "
                                          "them again.")

        btn_save.on_click(save)
        self.widgets.update({"corrections_path": wgt_path, "save_corrections": btn_save, "corrections_saved": wgt_saved})
        return widgets.VBox([widgets.HBox([wgt_path, btn_save]), wgt_saved])

    def event_viewer(self) -> None:
        """The plot and the results of the event chosen in the dropdown, and the onset of each of its channel groups,
        which can be corrected

        The plot is an Image widget and the results an HTML widget, which are updated when the event changes. Outputs
        in an Output widget would be slow to run headless (e.g. nbmake): the runner sends them back to the kernel at
        every output, and stalls when they are large.
        """
        if self.seppact is None or self.seppact.df_results is None or "Fluence" not in self.seppact.df_results:
            display(widgets.HTML(_error_text("There are no results: run the analysis step first.")))
            return
        # the results table, made again after a correction
        table = {"results": self.seppact.results_table()}
        flagged = self._flagged_events()
        wgt_plot = widgets.Image(format="png", layout=widgets.Layout(max_width="100%", height="auto"))
        wgt_table = widgets.HTML()
        wgt_flagged, wgt_event = self._event_choice(flagged, "with copied onsets or onsets at the end of the "
                                                             "background window")
        btn_previous = widgets.Button(description="Previous", icon="arrow-left")
        btn_next = widgets.Button(description="Next", icon="arrow-right")

        def move(step):
            values = [value for _, value in wgt_event.options]
            if values:
                i = values.index(wgt_event.value) + step
                wgt_event.value = values[min(max(i, 0), len(values) - 1)]

        def show(_=None):
            if wgt_event.value is None:
                wgt_plot.value, wgt_table.value = b"", ""
                return
            results = table["results"]
            wgt_plot.value = _figure_png(plot_event(self.seppact, wgt_event.value))
            wgt_table.value = results[results["Event No"] == wgt_event.value].to_html(index=False, na_rep="", border=0)

        def refresh():
            table["results"] = self.seppact.results_table()
            show()

        self.widgets.update({"flagged_only": wgt_flagged, "event": wgt_event, "previous": btn_previous, "next": btn_next,
                             "plot": wgt_plot, "table": wgt_table})
        wgt_event.observe(show, names="value")
        btn_previous.on_click(lambda _: move(-1))
        btn_next.on_click(lambda _: move(1))
        wgt_correction = self._onset_correction_widget(wgt_event, refresh)
        display(widgets.VBox([wgt_flagged, widgets.HBox([wgt_event, btn_previous, btn_next]), wgt_correction, wgt_plot,
                              wgt_table, self._save_corrections_widget()]))
        show()

    def save_results(self) -> None:
        """Writes results.csv, and the plots of the events if they are to be saved"""
        if self.seppact is None or self.seppact.df_results is None or "Fluence" not in self.seppact.df_results:
            display(widgets.HTML(_error_text("There are no results: run the analysis step first.")))
            return
        p = self.seppact.params
        self.seppact.save_results()
        saved = [f"the results to {os.path.join(p.dir_outputs, 'results.csv')}"]
        if self.save_plots:
            self.seppact.plot_events()
            saved.append(f"the plots of {count(len(self.seppact.events), 'event')} to {p.dir_plots}")
        display(widgets.HTML(html.escape(f"Saved {' and '.join(saved)}.")))
