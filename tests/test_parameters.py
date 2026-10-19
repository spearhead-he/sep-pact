"""Tests of SEPPACT_parameters: defaults, checks of the values and of the parameters that depend on each other"""
from datetime import timedelta

import pytest

from spearhead.sep_pact import SEPPACT, SEPPACT_parameters
from spearhead.sep_pact.conf import default_group_options


def test_defaults():
    p = SEPPACT_parameters()
    assert p.file_events == "inputs/events_example.csv"
    assert p.file_shocks == "inputs/shocks.dat"
    assert p.viewings == ["sun", "asun", "north", "south"]
    assert p.resample_freqs == [timedelta(minutes=2), timedelta(minutes=5), timedelta(minutes=10), timedelta(minutes=30)]
    assert p.group_options == default_group_options()
    assert p.spike_thresholds[timedelta(minutes=10)] == 2.5
    assert p.onset_sigma == 2 and p.onset_points == 3
    assert p.reference_onset_window == timedelta(hours=2.5)
    assert p.fallback_viewing == "sun"


def test_mutable_defaults_are_not_shared():
    a = SEPPACT_parameters()
    b = SEPPACT_parameters()
    a.viewings.append("sun")
    a.group_options["protons"]["8 MeV"]["channels"].append(4)
    assert b.viewings == ["sun", "asun", "north", "south"]
    assert b.group_options["protons"]["8 MeV"]["channels"] == [1, 2, 3]


def test_reference_channel():
    assert SEPPACT_parameters().reference_channel == {"particle": "electrons", "mev": "1 MeV", "sensor": "HET"}


def test_no_reference_channel():
    groups = {"protons": {"8 MeV": {"sensor": "HET", "channels": [1, 2, 3]}}}
    assert SEPPACT_parameters(group_options=groups).reference_channel is None


def test_unknown_name_fails_with_the_list_of_parameters():
    p = SEPPACT_parameters()
    with pytest.raises(AttributeError, match="no parameter 'onset_sigmaa'.*onset_sigma"):
        p.onset_sigmaa = 3


def test_unknown_keyword_fails():
    with pytest.raises(TypeError):
        SEPPACT_parameters(onset_sigmaa=3)


@pytest.mark.parametrize("name, value, error, message", [
    ("viewings", ["sun", "up"], ValueError, r"invalid: \['up'\]"),
    ("viewings", [], ValueError, "non-empty"),
    ("fallback_viewing", "up", ValueError, "fallback_viewing must be one of"),
    ("resample_freqs", [timedelta(minutes=30), timedelta(minutes=2)], ValueError, "ascending order"),
    ("resample_freqs", [5], TypeError, "list of datetime.timedelta"),
    ("bg_end_before_onset", 5, TypeError, "bg_end_before_onset must be a datetime.timedelta"),
    ("onset_points", 0, ValueError, "at least 1"),
    ("fluence_points", 1.5, ValueError, "at least 1"),
    ("download_tries", 0, ValueError, "at least 1"),
    ("fluence_peak_fraction", 0, ValueError, r"in \(0, 1\]"),
    ("fluence_peak_fraction", 1.5, ValueError, r"in \(0, 1\]"),
])
def test_invalid_values(name, value, error, message):
    p = SEPPACT_parameters()
    with pytest.raises(error, match=message):
        setattr(p, name, value)


def test_invalid_value_in_the_constructor():
    with pytest.raises(ValueError, match="invalid"):
        SEPPACT_parameters(viewings=["up"])


@pytest.mark.parametrize("groups, message", [
    ({"ions": {"8 MeV": {"sensor": "HET", "channels": [1]}}}, "particle 'ions'"),
    ({"protons": {"8 MeV": {"sensor": "EPT", "channels": [1]}}}, "sensor 'EPT'"),
    ({"protons": {"8 MeV": {"sensor": "HET", "channels": []}}}, "has no channels"),
    ({"protons": {"8 MeV": {"sensor": "HET", "channels": [1], "reference_channel": True},
                  "25 MeV": {"sensor": "HET", "channels": [18], "reference_channel": True}}},
     "More than one reference channel"),
])
def test_invalid_group_options(groups, message):
    with pytest.raises(ValueError, match=message):
        SEPPACT_parameters(group_options=groups)


def test_missing_spike_threshold():
    with pytest.raises(ValueError, match="no threshold for the resolutions"):
        SEPPACT_parameters(resample_freqs=[timedelta(minutes=15)])


def test_check_after_changing_dependent_parameters():
    p = SEPPACT_parameters()
    p.resample_freqs = [timedelta(minutes=15)]
    with pytest.raises(ValueError, match="no threshold"):
        p.check()
    p.spike_thresholds = {timedelta(minutes=15): 2.5}
    p.check()


def test_seppact_checks_the_parameters():
    p = SEPPACT_parameters()
    p.resample_freqs = [timedelta(minutes=15)]
    with pytest.raises(ValueError, match="no threshold"):
        SEPPACT(p)


def test_removed_parameter_fails_with_its_replacement(monkeypatch):
    import spearhead.sep_pact.conf as conf
    monkeypatch.setitem(conf.REMOVED_PARAMETERS, "old_name", ("0.2.0", "Use new_name instead."))
    p = SEPPACT_parameters()
    with pytest.raises(AttributeError, match="The old_name parameter was removed in 0.2.0. Use new_name instead."):
        p.old_name = 1


def test_dir_inputs_is_removed():
    p = SEPPACT_parameters()
    with pytest.raises(AttributeError, match="The dir_inputs parameter was removed in 0.2.0. Give the event list and the "
                                             "shock list as paths, in file_events and file_shocks."):
        p.dir_inputs = "inputs"


@pytest.mark.parametrize("value", [0, 0.5, 11, -2, "3", True])
def test_panel_height_out_of_range(value):
    p = SEPPACT_parameters()
    with pytest.raises(ValueError, match="panel_height must be a number of inches from 1 to 10"):
        p.panel_height = value


@pytest.mark.parametrize("value", [1, 2.5, 10])
def test_panel_height_in_range(value):
    p = SEPPACT_parameters(panel_height=value)
    assert p.panel_height == value
