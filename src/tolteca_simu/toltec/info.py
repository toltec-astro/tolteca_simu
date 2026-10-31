"""TolTEC array facts used for planning.

These values follow v1 tolteca (``common/toltec`` and ``simu/toltec/toltec_info``)
until TolTECA gives them an owner.
"""

from dataclasses import dataclass
from typing import Literal

import astropy.units as u

__all__ = ["TOLTEC_ARRAYS", "TOLTEC_PLATE_SCALE", "ToltecArrayInfo", "ToltecArrayName"]

type ToltecArrayName = Literal["a1100", "a1400", "a2000"]
"""Names of the TolTEC arrays: ``a1100``, ``a1400`` and ``a2000``."""

# The beam FWHM is 5 arcsec at 1.1 mm and scales with wavelength.
_FWHM_A1100 = 5.0 << u.arcsec
_WL_CENTER_A1100 = 1.1 << u.mm

TOLTEC_PLATE_SCALE = (4.0 << u.arcmin) / (127.049101 << u.mm)
"""Sky offset per focal-plane distance: the field of view over the array size."""


@dataclass(frozen=True)
class ToltecArrayInfo:
    """Facts of one TolTEC detector array.

    Attributes
    ----------
    name : str
        Array name.
    index : int
        Array index in array property tables.
    name_long : str
        Display name.
    wl_center : astropy.units.Quantity
        Band center wavelength.
    mounting_angle : astropy.units.Quantity
        Rotation of the array in the instrument frame.
    """

    name: ToltecArrayName
    index: int
    name_long: str
    wl_center: u.Quantity
    mounting_angle: u.Quantity

    @property
    def a_fwhm(self) -> u.Quantity:
        """Beam FWHM along the major axis."""
        return _FWHM_A1100 * (self.wl_center / _WL_CENTER_A1100)

    @property
    def b_fwhm(self) -> u.Quantity:
        """Beam FWHM along the minor axis."""
        return _FWHM_A1100 * (self.wl_center / _WL_CENTER_A1100)


TOLTEC_ARRAYS: dict[ToltecArrayName, ToltecArrayInfo] = {
    "a1100": ToltecArrayInfo(
        "a1100", 0, "TolTEC 1.1 mm array", 1.1 << u.mm, 90.0 << u.deg
    ),
    "a1400": ToltecArrayInfo(
        "a1400", 1, "TolTEC 1.4 mm array", 1.4 << u.mm, -90.0 << u.deg
    ),
    "a2000": ToltecArrayInfo(
        "a2000", 2, "TolTEC 2.0 mm array", 2.0 << u.mm, -90.0 << u.deg
    ),
}
"""The TolTEC arrays by name, in index order."""
