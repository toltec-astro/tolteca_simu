"""Sky bounding boxes and image grids."""

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.coordinates import Angle, Latitude, Longitude
from astropy.wcs import WCS

__all__ = ["SkyBoundingBox", "get_lon_extent", "make_wcs"]


def get_lon_extent(lon: Longitude) -> tuple[Longitude, Longitude, Angle]:
    """Return the west and east extent of longitudes, wrapped compactly.

    Parameters
    ----------
    lon : astropy.coordinates.Longitude
        Longitudes.

    Returns
    -------
    tuple
        West and east longitudes, and the wrap angle giving the smallest span;
        the input's own wrap angle wins ties.
    """
    lon = Longitude(np.ravel(lon))
    wrap_angle = Angle([lon.wrap_angle.degree, 360.0, 180.0] << u.deg)
    lon_deg_wrapped = np.vstack([lon.wrap_at(a).degree for a in wrap_angle])
    west_deg = np.min(lon_deg_wrapped, axis=1)
    east_deg = np.max(lon_deg_wrapped, axis=1)
    i_w = np.argmin(east_deg - west_deg)
    lon_wrap_angle = wrap_angle[i_w]
    return (
        Longitude(west_deg[i_w] << u.deg, wrap_angle=lon_wrap_angle),
        Longitude(east_deg[i_w] << u.deg, wrap_angle=lon_wrap_angle),
        lon_wrap_angle,
    )


@dataclass(frozen=True)
class SkyBoundingBox:
    """A longitude-latitude box on the sky.

    Attributes
    ----------
    w, e : astropy.coordinates.Longitude
        West and east edges.
    s, n : astropy.coordinates.Latitude
        South and north edges.
    lon_wrap_angle : astropy.coordinates.Angle
        Wrap angle of the longitudes.
    """

    w: Longitude
    e: Longitude
    s: Latitude
    n: Latitude
    lon_wrap_angle: Angle

    @property
    def center(self) -> Angle:
        """Longitude and latitude of the box center."""
        return Angle([(self.w + self.e) * 0.5, (self.s + self.n) * 0.5])

    @property
    def width(self) -> Angle:
        """Longitude span, not scaled by the latitude."""
        return Angle(self.e - self.w)

    @property
    def height(self) -> Angle:
        """Latitude span."""
        return Angle(self.n - self.s)

    @classmethod
    def from_lonlat(cls, lon: Longitude, lat: Latitude) -> "SkyBoundingBox":
        """Return the box enclosing longitudes and latitudes.

        Parameters
        ----------
        lon : astropy.coordinates.Longitude
            Longitudes.
        lat : astropy.coordinates.Latitude
            Latitudes.

        Returns
        -------
        SkyBoundingBox
            The enclosing box.
        """
        west, east, lon_wrap_angle = get_lon_extent(lon)
        return cls(
            w=west,
            e=east,
            s=Latitude(np.min(lat)),
            n=Latitude(np.max(lat)),
            lon_wrap_angle=lon_wrap_angle,
        )

    def pad_with(self, dx: Angle, dy: Angle) -> "SkyBoundingBox":
        """Return the box padded on each side.

        Parameters
        ----------
        dx : astropy.coordinates.Angle
            On-sky padding along longitude, divided by the cosine of the center
            latitude.
        dy : astropy.coordinates.Angle
            Padding along latitude.

        Returns
        -------
        SkyBoundingBox
            The padded box, re-wrapped if it crosses the wrap angle.
        """
        dlon = dx / np.cos((self.n + self.s) * 0.5)
        w, e, lon_wrap_angle = get_lon_extent(
            Longitude([self.w - dlon, self.e + dlon], wrap_angle=self.lon_wrap_angle)
        )
        return SkyBoundingBox(
            w=w,
            e=e,
            s=Latitude(self.s - dy),
            n=Latitude(self.n + dy),
            lon_wrap_angle=lon_wrap_angle,
        )


def make_wcs(
    sky_bbox: SkyBoundingBox,
    pixscale: u.Quantity,
    n_pix_max: float | None = None,
    adaptive_pixscale_factor: float = 1,
) -> tuple[WCS, tuple[float, float]]:
    """Return a TAN image grid covering a sky box.

    The grid has ``ceil(width / pixel)`` by ``ceil(height / pixel)`` pixels,
    with the longitude span measured in longitude degrees. When that exceeds
    ``n_pix_max``, the pixel size grows by a multiple of
    ``adaptive_pixscale_factor``.

    Parameters
    ----------
    sky_bbox : SkyBoundingBox
        The box to cover; its center is the reference point.
    pixscale : astropy.units.Quantity
        Pixel scale in angle per pixel.
    n_pix_max : float, optional
        Largest number of pixels.
    adaptive_pixscale_factor : float, optional
        Step of the pixel size multiplier when the grid is reduced.

    Returns
    -------
    tuple
        The WCS, and the grid size ``(nx, ny)``, which may be fractional when
        the grid is reduced.
    """
    pixsize = (1 << u.pix).to(u.arcsec, equivalencies=u.pixel_scale(pixscale))
    nx = int(np.ceil((sky_bbox.width / pixsize).to_value(u.dimensionless_unscaled)))
    ny = int(np.ceil((sky_bbox.height / pixsize).to_value(u.dimensionless_unscaled)))
    size: tuple[float, float] = (nx, ny)
    if n_pix_max is not None and nx * ny > n_pix_max:
        s = (nx * ny / n_pix_max) ** 0.5
        s = np.ceil(s / adaptive_pixscale_factor) * adaptive_pixscale_factor
        size = (nx / s, ny / s)
        pixsize = pixsize * s
    wcsobj = WCS(naxis=2)
    wcsobj.wcs.crpix = [size[0] / 2, size[1] / 2]
    wcsobj.wcs.cdelt = np.array([-pixsize.to_value(u.deg), pixsize.to_value(u.deg)])
    wcsobj.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcsobj.wcs.crval = [v.degree for v in sky_bbox.center]
    return wcsobj, size
