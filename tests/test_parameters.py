"""Tests of SEPPACT_parameters: defaults, checks of the values and of the parameters that depend on each other"""
from datetime import timedelta

import pytest

from spearhead.sep_pact import SEPPACT, SEPPACT_parameters
from spearhead.sep_pact.conf import default_group_options


def test_defaults():
    p = SEPPACT_parameters()
    assert p.file_events == "example.xlsx"
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
