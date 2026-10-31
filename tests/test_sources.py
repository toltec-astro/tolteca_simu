import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

from tolteca_simu.sources import ImageSource, PointSourceCatalog
from tolteca_simu.toltec import TOLTEC_ARRAYS

DATA = Path(__file__).parent / "data"
REFERENCE = json.loads((DATA / "v1_sources_reference.json").read_text())
ARRAYS: list[str] = list(TOLTEC_ARRAYS)
FWHMS: dict[str, u.Quantity] = {
    name: array.a_fwhm for name, array in TOLTEC_ARRAYS.items()
}
FLUX_COLUMNS = {name: f"flux_{name}" for name in ARRAYS}
EXTENSIONS = {name: f"{name.upper()}_I" for name in ARRAYS}
# Source pixel positions from the WCS differ by about 1e-10 pixel between
# astropy 5.3 (v1) and the current version; far in a beam tail this changes
# the rendered values by up to about 1e-9 of their size.
RENDER_RTOL = 1e-9


def _evaluate(source: ImageSource, reference: dict) -> np.ndarray:
    ra = np.tile(reference["eval_ra"], (len(ARRAYS), 1)) << u.deg
    dec = np.tile(reference["eval_dec"], (len(ARRAYS), 1)) << u.deg
    return source.evaluate(ARRAYS, ra, dec).to_value(u.MJy / u.sr)


@pytest.mark.parametrize("reference", REFERENCE["catalogs"], ids=lambda r: r["file"])
def test_catalog_images_equal_v1(reference: dict) -> None:
    catalog = PointSourceCatalog.read(
        DATA / reference["file"], flux_columns=FLUX_COLUMNS
    )
    assert catalog.names.tolist() == reference["names"]
    np.testing.assert_array_equal(catalog.positions.ra.degree, reference["ra"])
    np.testing.assert_array_equal(catalog.positions.dec.degree, reference["dec"])
    source = catalog.make_image_source(FWHMS)
    for name, image in source.images.items():
        ref = reference["images"][name]
        assert list(image.data.shape) == ref["shape"]
        header = image.wcs.to_header()
        for key in ("CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2"):
            assert header[key] == pytest.approx(ref["header"][key], rel=1e-14), key
        assert image.unit == u.Unit(ref["header"]["SIGUNIT"])
        np.testing.assert_allclose(image.data.sum(), ref["sum"], rtol=1e-12)
        np.testing.assert_allclose(image.data.max(), ref["max"], rtol=1e-12)
        np.testing.assert_allclose(
            image.data[ref["sample_i"], ref["sample_j"]],
            ref["sample_values"],
            rtol=RENDER_RTOL,
            atol=0,
        )
    values = _evaluate(source, reference)
    for i, name in enumerate(ARRAYS):
        np.testing.assert_allclose(
            values[i], reference["eval_values"][name], rtol=RENDER_RTOL, atol=0
        )


def test_catalog_flux_units_are_kept() -> None:
    table = Table.read(DATA / "point_source_flux_cat0.ecsv")
    in_jy = table.copy()
    for column in FLUX_COLUMNS.values():
        in_jy[column] = table[column] * 1e-3
        in_jy[column].unit = u.Jy
    catalog = PointSourceCatalog.from_table(table, flux_columns=FLUX_COLUMNS)
    catalog_jy = PointSourceCatalog.from_table(in_jy, flux_columns=FLUX_COLUMNS)
    for name in ARRAYS:
        np.testing.assert_allclose(
            catalog_jy.fluxes[name].to_value(u.mJy), catalog.fluxes[name].value
        )
    assert table["flux_a1100"].unit is None


def test_image_evaluation_equals_v1() -> None:
    reference = REFERENCE["image"]
    with ImageSource.open(DATA / reference["file"], EXTENSIONS) as source:
        values = _evaluate(source, reference)
    for i, name in enumerate(ARRAYS):
        np.testing.assert_array_equal(values[i], reference["eval_values"][name])


def test_labels_without_an_image_evaluate_to_zero() -> None:
    reference = REFERENCE["image"]
    with ImageSource.open(DATA / reference["file"], {"a1100": "A1100_I"}) as source:
        values = _evaluate(source, reference)
    assert values[0].any()
    assert not values[1:].any()


def test_image_without_a_unit_raises(tmp_path: Path) -> None:
    path = tmp_path / "no_unit.fits"
    with fits.open(DATA / REFERENCE["image"]["file"]) as hdul:
        hdu = hdul["A1100_I"].copy()
    del hdu.header["SIGUNIT"]
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(path)
    with (
        pytest.raises(ValueError, match="'A1100_I' has no SIGUNIT or BUNIT"),
        ImageSource.open(path, {"a1100": "A1100_I"}),
    ):
        pass


def test_missing_inputs_raise() -> None:
    with (
        pytest.raises(KeyError),
        ImageSource.open(DATA / REFERENCE["image"]["file"], {"a1100": "A1100_Q"}),
    ):
        pass
    with pytest.raises(KeyError):
        PointSourceCatalog.read(
            DATA / "aztec_sources_pope.asc", flux_columns={"a1100": "flux"}
        )
