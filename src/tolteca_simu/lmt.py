"""The LMT as an observing site."""

from functools import cache
from typing import Literal

import astropy.units as u
from astroplan import Observer
from astropy.coordinates import EarthLocation

__all__ = ["LmtAtmModelName", "get_lmt_observer"]

type LmtAtmModelName = Literal["am_q25", "am_q50", "am_q75"]
"""Names of the LMT am atmosphere models: quartiles of the conditions."""

# LMT site facts, the same values as tolteca's
# `tolteca_datamodels.lmt.types.LmtInfo`. They are kept here until tolteca is
# published, so that the planner can be installed without it.
_LMT_NAME_LONG = "Large Millimeter Telescope"
_LMT_LOCATION = {"lon": "-97d18m52.6s", "lat": "+18d59m10s", "height": 4640 << u.m}
_LMT_TIMEZONE_LOCAL = "America/Mexico_City"


@cache
def get_lmt_observer() -> Observer:
    """Return the observer at the LMT.

    Returns
    -------
    astroplan.Observer
        Observer at the LMT location and in its local time zone.
    """
    return Observer(
        name=_LMT_NAME_LONG,
        location=EarthLocation.from_geodetic(**_LMT_LOCATION),
        timezone=_LMT_TIMEZONE_LOCAL,
    )
