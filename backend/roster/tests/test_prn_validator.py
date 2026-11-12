"""The one PRN rule: settings.IDENTITY["PRN_REGEX"], matched against the whole value."""

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from roster.models import PRN_VALIDATOR


@pytest.mark.parametrize("prn", ["220200921", "000000000"])
def test_nine_digits_pass(prn):
    PRN_VALIDATOR(prn)


@pytest.mark.parametrize(
    "prn",
    [
        "220200921\n",  # "$" alone would accept this; fullmatch must not
        " 220200921",
        "22020092",
        "2202009211",
        "22020092X",
        "PRN2022CS001",
        "",
    ],
)
def test_anything_else_fails(prn):
    with pytest.raises(ValidationError):
        PRN_VALIDATOR(prn)


def test_the_rule_is_read_from_settings_at_call_time():
    # If the registrar changes the format, it is a settings change, not a code change.
    with override_settings(IDENTITY={"PRN_REGEX": r"^[0-9]{10}$"}):
        PRN_VALIDATOR("2202009211")
        with pytest.raises(ValidationError):
            PRN_VALIDATOR("220200921")
    PRN_VALIDATOR("220200921")
