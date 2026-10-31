"""Sky sources given as surface brightness.

Point-source catalogs and FITS images follow v1 tolteca ``simu.sources``.
Catalogs are rendered to images with one Gaussian beam per label, and images are
evaluated at the nearest pixel.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Self

import astropy.units as u
import numpy as np
from astropy.coordinates import Latitude, Longitude, SkyCoord
from astropy.io import fits
from astropy.modeling.functional_models import GAUSSIAN_SIGMA_TO_FWHM, Gaussian2D
from astropy.table import Table
from astropy.wcs import WCS
from numpy.typing import ArrayLike

from tolteca_simu.sky import SkyBoundingBox

__all__ = ["ImageSource", "PointSourceCatalog", "SourceImage"]

_SURFACE_BRIGHTNESS_UNIT = u.MJy / u.sr
_PIXEL_SIZE_DEFAULT = 0.5 << u.arcsec
# The rendered image extends beyond the sources by this many of the largest FWHM.
_PADDING_FWHMS = 10


@dataclass(frozen=True)
class SourceImage:
    """Surface brightness on a sky grid.

    Attributes
    ----------
    data : numpy.ndarray
        Image values, with rows along latitude.
    wcs : astropy.wcs.WCS
        Celestial WCS of the image.
    unit : astropy.units.UnitBase
        Unit of the values.
    """

    data: np.ndarray
    wcs: WCS
    unit: u.UnitBase

    @classmethod
    def from_hdu(cls, hdu: fits.ImageHDU) -> Self:
        """Return the image held in a FITS HDU.

        Parameters
        ----------
        hdu : astropy.io.fits.ImageHDU
            Image with a celestial WCS on its first two axes and its unit in
            ``SIGUNIT`` or ``BUNIT``.

        Returns
        -------
        SourceImage
            The image. Further axes of length one are dropped.

        Raises
        ------
        ValueError
            If the header gives no unit.
        """
        header = hdu.header
        unit = header.get("SIGUNIT", header.get("BUNIT"))
        if unit is None:
            msg = f"FITS extension {hdu.name!r} has no SIGUNIT or BUNIT"
            raise ValueError(msg)
        wcs = WCS(header).sub(2)
        return cls(data=hdu.data.reshape(wcs.array_shape), wcs=wcs, unit=u.Unit(unit))

    @cached_property
    def sky_bbox(self) -> SkyBoundingBox:
        """Sky box enclosing the image."""
        return SkyBoundingBox.from_wcs(self.wcs, self.data.shape)

    def evaluate(self, ra: u.Quantity, dec: u.Quantity) -> u.Quantity:
        """Return the values at sky positions.

        Parameters
        ----------
        ra, dec : astropy.units.Quantity
            ICRS positions, of any shape.

        Returns
        -------
        astropy.units.Quantity
            The value of the nearest pixel, zero outside the image.
        """
        sky_bbox = self.sky_bbox
        ra_deg = Longitude(ra).wrap_at(sky_bbox.lon_wrap_angle).degree
        dec_deg = Latitude(dec).degree
        inside = (
            (ra_deg > sky_bbox.w.degree)
            & (ra_deg < sky_bbox.e.degree)
            & (dec_deg > sky_bbox.s.degree)
            & (dec_deg < sky_bbox.n.degree)
        )
        x, y = self.wcs.wcs_world2pix(ra_deg[inside], dec_deg[inside], 0)
        ii = np.rint(y).astype(int)
        jj = np.rint(x).astype(int)
        ny, nx = self.data.shape
        on_grid = (ii >= 0) & (ii < ny) & (jj >= 0) & (jj < nx)
        inside[inside] = on_grid
        values = np.zeros(ra_deg.shape)
        values[inside] = self.data[ii[on_grid], jj[on_grid]]
        return values << self.unit


@dataclass(frozen=True)
class ImageSource:
    """Surface brightness images, one per label.

    Attributes
    ----------
    images : dict of str to SourceImage
        Image per label, such as a TolTEC array name.
    """

    images: Mapping[str, SourceImage]

    @classmethod
    @contextmanager
    def open(cls, path: str | Path, extensions: Mapping[str, str]) -> Iterator[Self]:
        """Open images from a FITS file.

        Parameters
        ----------
        path : str or pathlib.Path
            The FITS file.
        extensions : mapping of str to str
            Extension name for each label.

        Yields
        ------
        ImageSource
            The images, read from the memory-mapped file. Evaluate the source
            within the context; the file is closed on exit.

        Raises
        ------
        KeyError
            If the file lacks an extension.
        ValueError
            If an extension gives no unit.
        """
        with fits.open(path) as hdul:
            yield cls(
                {
                    label: SourceImage.from_hdu(hdul[ext])
                    for label, ext in extensions.items()
                }
            )

    def evaluate(self, label: ArrayLike, ra: u.Quantity, dec: u.Quantity) -> u.Quantity:
        """Return the surface brightness at sky positions.

        Parameters
        ----------
        label : array_like of str
            Label of each row of positions, such as each detector's array name.
        ra, dec : astropy.units.Quantity
            ICRS positions; the first axis matches ``label``.

        Returns
        -------
        astropy.units.Quantity
            Surface brightness in MJy/sr, of the shape of ``ra``. Rows whose
            label has no image are zero.
        """
        label = np.asarray(label)
        result = np.zeros(np.shape(ra)) << _SURFACE_BRIGHTNESS_UNIT
        for name, image in self.images.items():
            rows = label == name
            result[rows] = image.evaluate(ra[rows], dec[rows])
        return result


@dataclass(frozen=True)
class PointSourceCatalog:
    """Point sources with fluxes per label.

    Attributes
    ----------
    names : numpy.ndarray
        Source names.
    positions : astropy.coordinates.SkyCoord
        ICRS source positions.
    fluxes : dict of str to astropy.units.Quantity
        Source fluxes per label, such as a TolTEC array name.

    Examples
    --------
    >>> from astropy.table import Table
    >>> table = Table({"ra": [180.0], "dec": [0.0], "flux_a1100": [20.0]})
    >>> catalog = PointSourceCatalog.from_table(
    ...     table, flux_columns={"a1100": "flux_a1100"}
    ... )
    >>> catalog.names.tolist(), catalog.fluxes["a1100"]
    (['src0'], <Quantity [20.] mJy>)
    """

    names: np.ndarray
    positions: SkyCoord
    fluxes: Mapping[str, u.Quantity]

    @classmethod
    def from_table(
        cls,
        table: Table,
        *,
        flux_columns: Mapping[str, str],
        name_column: str = "source_name",
        position_columns: tuple[str, str] = ("ra", "dec"),
    ) -> Self:
        """Return the sources of a table.

        Parameters
        ----------
        table : astropy.table.Table
            The catalog. It is not modified.
        flux_columns : mapping of str to str
            Flux column for each label. Columns without a unit are in mJy.
        name_column : str, optional
            Column of source names. Without it, sources are named ``src{i}``.
        position_columns : tuple of str, optional
            Columns of ICRS right ascension and declination. Columns without a
            unit are in degrees.

        Returns
        -------
        PointSourceCatalog
            The sources.

        Raises
        ------
        KeyError
            If the table lacks a position or flux column.
        """
        if name_column in table.colnames:
            names = np.asarray(table[name_column])
        else:
            names = np.array([f"src{i}" for i in range(len(table))])
        ra, dec = (_get_quantity(table, c, u.deg) for c in position_columns)
        return cls(
            names=names,
            positions=SkyCoord(ra, dec, frame="icrs"),
            fluxes={
                label: _get_quantity(table, column, u.mJy)
                for label, column in flux_columns.items()
            },
        )

    @classmethod
    def read(
        cls,
        path: str | Path,
        *,
        flux_columns: Mapping[str, str],
        name_column: str = "source_name",
        position_columns: tuple[str, str] = ("ra", "dec"),
    ) -> Self:
        """Read sources from a catalog file.

        Parameters
        ----------
        path : str or pathlib.Path
            An ASCII table that astropy can read, such as ECSV or whitespace
            separated columns under a commented header.
        flux_columns : mapping of str to str
            Flux column for each label, as in `from_table`.
        name_column : str, optional
            Column of source names, as in `from_table`.
        position_columns : tuple of str, optional
            Columns of ICRS right ascension and declination, as in `from_table`.

        Returns
        -------
        PointSourceCatalog
            The sources.
        """
        return cls.from_table(
            Table.read(path, format="ascii"),
            flux_columns=flux_columns,
            name_column=name_column,
            position_columns=position_columns,
        )

    def make_image_source(
        self,
        fwhms: Mapping[str, u.Quantity],
        pixel_size: u.Quantity = _PIXEL_SIZE_DEFAULT,
    ) -> ImageSource:
        """Render the sources as images, one Gaussian beam per source.

        Parameters
        ----------
        fwhms : mapping of str to astropy.units.Quantity
            Beam FWHM for each label; it includes every flux label. The images
            span the sources' extent plus ten of the largest FWHM.
        pixel_size : astropy.units.Quantity, optional
            Pixel size; 0.5 arcsec by default.

        Returns
        -------
        ImageSource
            One image per flux label on a common TAN grid, in MJy/sr; each beam
            integrates to the source flux.
        """
        pixel_scale = u.pixel_scale(pixel_size / u.pix)
        pixel_deg = pixel_size.to_value(u.deg)
        ra_deg = self.positions.ra.degree
        dec_deg = self.positions.dec.degree
        # Center a square grid on the sources, starting from the first one.
        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [1.5, 1.5]
        wcs.wcs.cdelt = np.array([-pixel_deg, pixel_deg])
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crval = [ra_deg[0], dec_deg[0]]
        x, y = wcs.wcs_world2pix(ra_deg, dec_deg, 0)
        padding = _PADDING_FWHMS * max(fwhms.values()).to_value(
            u.pix, equivalencies=pixel_scale
        )
        size = int(np.ceil(max(np.ptp(x), np.ptp(y)) + padding))
        wcs.wcs.crval = wcs.wcs_pix2world(
            (x.min() + x.max()) / 2, (y.min() + y.max()) / 2, 0
        )
        wcs.wcs.crpix = [size / 2 + 1, size / 2 + 1]
        x, y = wcs.wcs_world2pix(ra_deg, dec_deg, 0)
        images = {}
        for label, flux in self.fluxes.items():
            stddev = fwhms[label] / GAUSSIAN_SIGMA_TO_FWHM
            beam_area = 2 * np.pi * stddev * stddev
            amplitude = (flux * (1.0 / beam_area)).to_value(_SURFACE_BRIGHTNESS_UNIT)
            stddev_pix = stddev.to_value(u.pix, equivalencies=pixel_scale)
            beam = Gaussian2D(x_stddev=stddev_pix, y_stddev=stddev_pix)
            data = np.zeros((size, size))
            for x_mean, y_mean, a in zip(x, y, amplitude, strict=True):
                beam.amplitude = a
                beam.x_mean = x_mean
                beam.y_mean = y_mean
                beam.render(data)
            images[label] = SourceImage(
                data=data, wcs=wcs, unit=_SURFACE_BRIGHTNESS_UNIT
            )
        return ImageSource(images)


def _get_quantity(table: Table, column: str, unit: u.UnitBase) -> u.Quantity:
    """Return a column as a quantity, in ``unit`` when it has none."""
    col = table[column]
    return u.Quantity(col, unit if col.unit is None else col.unit)
