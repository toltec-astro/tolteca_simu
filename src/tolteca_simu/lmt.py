"""The LMT as an observing site."""

from functools import cache
from typing import Literal

from astroplan import Observer
from astropy.coordinates import EarthLocation
from tolteca_datamodels.lmt.types import LmtInfo

__all__ = ["LmtAtmModelName", "get_lmt_observer"]

type LmtAtmModelName = Literal["am_q25", "am_q50", "am_q75"]
"""Names of the LMT am atmosphere models: quartiles of the conditions."""


@cache
def get_lmt_observer() -> Observer:
    """Return the observer at the LMT.

    Returns
    -------
    astroplan.Observer
        Observer at the LMT location and in its local time zone, from
        `tolteca_datamodels.lmt.types.LmtInfo`.
    """
    return Observer(
        name=LmtInfo.name_long,
        location=EarthLocation.from_geodetic(**LmtInfo.location),
        timezone=LmtInfo.timezone_local,
    )
