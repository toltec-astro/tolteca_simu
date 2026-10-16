"""The LMT as an observing site."""

from functools import cache

from astroplan import Observer
from astropy.coordinates import EarthLocation
from tolteca_datamodels.lmt.types import LmtInfo

__all__ = ["get_lmt_observer"]


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
