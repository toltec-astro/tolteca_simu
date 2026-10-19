import base64
import io
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from dash_aladin_lite import GraphicLayer, ImageLayer, Polygon, Polyline

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import (
    MappingPresets,
    ObservationDescription,
    get_trajectory,
)
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.planning import ToltecPlanner
from tolteca_simu.toltec.settings import ToltecSettings
from tolteca_simu.web.toltec_obs_planner.sky import make_sky_view

APT = "toltec/apt/apt_GW_v8_with_fg_pg_loc_ori_flipped_flag_fixed.ecsv"


@pytest.fixture(
    scope="module", params=["toltec_blank_field_lissajous", "toltec_blank_field_raster"]
)
def planned(request: pytest.FixtureRequest, cal_data_path: Path) -> tuple:
    preset = MappingPresets.from_yaml(get_default_presets_path()).get(request.param)
    pattern, t_exp = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    description = ObservationDescription(
        target_name="M82",
        target=SkyCoord("09h55m52.4s +69d40m47s"),
        t0=Time("2026-01-15 06:00:00"),
        mapping=pattern,
        ref_frame="altaz",
        t_exp=t_exp,
        atm_model_name="am_q25",
        instrument=ToltecSettings(polarized=False, array_name="a1100"),
        desired_sens=1 * u.mJy,
    )
    observer = get_lmt_observer()
    trajectory = get_trajectory(
        description.mapping,
        description.target,
        description.t0,
        t_exp=description.get_t_exp(),
        ref_frame=description.ref_frame,
        observer=observer,
    )
    planner = ToltecPlanner(
        CalDataStore(cal_data_path),
        apt_path=APT,
        tel_surface_rms=100 * u.um,
        det_noise_factors={"am_q25": {"a1100": 2.0, "a1400": 2.0, "a2000": 2.0}},
    )
    result = planner.plan(description, trajectory, observer)
    return description, trajectory, result


def _read_image(url: str) -> fits.PrimaryHDU:
    prefix = "data:application/fits;base64,"
    assert url.startswith(prefix)
    return fits.open(io.BytesIO(base64.b64decode(url.removeprefix(prefix))))[0]


@pytest.mark.parametrize("unit", ["depth", "time"])
def test_coverage_image_keeps_values_and_sky_positions(
    planned: tuple, unit: str
) -> None:
    description, trajectory, result = planned
    view = make_sky_view(description.target, trajectory, result, unit)
    image = view.layers[0]
    assert isinstance(image, ImageLayer)
    hdu = _read_image(image.url)
    assert hdu.header["BITPIX"] == -32  # 32-bit floats
    full = result.depth.depth if unit == "depth" else result.coverage.data_on_scan
    # Cropping keeps every covered pixel and its value.
    assert np.nansum(hdu.data) == pytest.approx(full.sum(), rel=1e-5)
    # The cropped WCS maps sky positions to the same values as the full map;
    # check at the pixel of maximum coverage.
    coverage = result.coverage.data_on_scan
    fy, fx = np.unravel_index(np.argmax(coverage), coverage.shape)
    world = result.coverage.wcs.pixel_to_world(fx, fy)
    ix, iy = (int(np.round(v)) for v in WCS(hdu.header).world_to_pixel(world))
    assert hdu.data[iy, ix] == pytest.approx(full[fy, fx], rel=1e-6)


def test_view_frames_the_map(planned: tuple) -> None:
    description, trajectory, result = planned
    view = make_sky_view(description.target, trajectory, result, "depth")
    layers = {layer.id: layer for layer in view.layers}
    assert list(layers) == ["coverage", "trajectory", "outline", "detectors"]
    target = description.target.icrs
    center = SkyCoord(*(float(v) for v in view.target.split()), unit=u.deg)
    assert center.separation(target).to_value(u.arcsec) < 1e-6
    detectors = layers["detectors"]
    assert isinstance(detectors, GraphicLayer)
    assert not detectors.visible
    assert len(detectors.shapes) == len(result.footprint.dlon)
    # The outline and every trajectory vertex lie within the view.
    for name in ("trajectory", "outline"):
        layer = layers[name]
        assert isinstance(layer, GraphicLayer)
        (shape,) = layer.shapes
        assert isinstance(shape, Polyline | Polygon)
        vertices = np.asarray(shape.vertices)
        assert 2 < len(vertices) <= 2000
        coords = SkyCoord(vertices[:, 0] * u.deg, vertices[:, 1] * u.deg)
        assert coords.separation(target).max().to_value(u.deg) < view.fov / 2
