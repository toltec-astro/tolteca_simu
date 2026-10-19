import re
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time
from dash_aladin_lite import GraphicLayer, Layer, Polyline
from pydantic import TypeAdapter

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import (
    MappingPresets,
    ObservationDescription,
    get_trajectory,
)
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec import TOLTEC_ARRAYS
from tolteca_simu.toltec.planning import ToltecPlanner
from tolteca_simu.toltec.settings import ToltecSettings
from tolteca_simu.web.toltec_obs_planner.views import make_view_description
from tolteca_simu.web.toltec_obs_planner.views_aladin import AladinViewsPanel
from tolteca_simu.web.toltec_obs_planner.views_firefly import FireflyViewsPanel

APT = "toltec/apt/apt_GW_v8_with_fg_pg_loc_ori_flipped_flag_fixed.ecsv"
NUMBER = r"(-?\d+\.\d+)"
LINE = re.compile(rf"^icrs;line\({NUMBER},{NUMBER},{NUMBER},{NUMBER}\) # color=red$")
CIRCLE = re.compile(rf'^icrs;circle\({NUMBER},{NUMBER},{NUMBER}"\) # color=#4dabf7$')
POLYGON = re.compile(r"^icrs;polygon\(([-\d.,]+)\) # color=#66cccc width=2$")


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


def _parse(pattern: re.Pattern, regions: list[str]) -> np.ndarray:
    matches = [pattern.match(region) for region in regions]
    assert all(matches)
    return np.array([[float(v) for v in m.groups()] for m in matches if m])


@pytest.fixture(scope="module")
def view_description(planned: tuple) -> dict:
    description, trajectory, result = planned
    return make_view_description(description.target, trajectory, result, "time")


def test_description_frames_the_trajectory(
    planned: tuple, view_description: dict
) -> None:
    description, trajectory, _ = planned
    center = SkyCoord(*view_description["center"], unit=u.deg)
    assert center.separation(description.target).to_value(u.arcsec) < 1e-6
    vertices = np.asarray(view_description["trajectory"])
    assert 2 < len(vertices) <= 2000
    first = trajectory.coords_icrs[0]
    start = SkyCoord(*vertices[0], unit=u.deg)
    assert start.separation(SkyCoord(first.ra, first.dec)).to_value(u.arcsec) < 1e-6
    coords = SkyCoord(vertices[:, 0], vertices[:, 1], unit=u.deg)
    size = view_description["size_deg"]
    assert coords.separation(center).max().to_value(u.deg) < size / 2


def test_description_marks_detectors_and_outline(
    planned: tuple, view_description: dict
) -> None:
    _, _, result = planned
    detectors = result.footprint.coords_icrs
    positions = np.asarray(view_description["detectors"]["positions"])
    assert positions[:, 0] == pytest.approx(detectors.ra.degree)
    assert positions[:, 1] == pytest.approx(detectors.dec.degree)
    beam_radius = (TOLTEC_ARRAYS[result.array_name].a_fwhm / 2).to_value(u.deg)
    assert view_description["detectors"]["radius_deg"] == pytest.approx(beam_radius)
    vertices = np.asarray(view_description["outline"])
    assert 2 < len(vertices) <= 500
    # The outline lies on the map, within the covered pixels.
    x, y = result.coverage.wcs.world_to_pixel_values(vertices[:, 0], vertices[:, 1])
    shape = result.coverage.data_on_scan.shape
    assert x.min() >= 0
    assert x.max() <= shape[1] - 1
    assert y.min() >= 0
    assert y.max() <= shape[0] - 1
    assert view_description["coverage_title"] == (
        "Coverage (s/pixel): TolTEC 1.1 mm array"
    )


def test_firefly_regions_follow_the_description(view_description: dict) -> None:
    views = FireflyViewsPanel.make_views(view_description)
    ra, dec, frame = views["world_pt"].split(";")
    assert frame == "EQ_J2000"
    assert [float(ra), float(dec)] == view_description["center"]
    segments = _parse(LINE, views["regions"]["trajectory"])
    # Segments join end to end along the trajectory vertices.
    assert segments[1:, :2] == pytest.approx(segments[:-1, 2:])
    trajectory = np.asarray(view_description["trajectory"])
    assert segments[:, :2] == pytest.approx(trajectory[:-1], abs=1e-6)
    circles = _parse(CIRCLE, views["regions"]["detectors"])
    detectors = view_description["detectors"]
    assert circles[:, :2] == pytest.approx(np.asarray(detectors["positions"]), abs=1e-6)
    assert circles[:, 2] == pytest.approx(detectors["radius_deg"] * 3600, abs=0.005)
    (outline,) = views["regions"]["outline"]
    match = POLYGON.match(outline)
    assert match
    vertices = np.array(match.group(1).split(","), dtype=float).reshape(-1, 2)
    assert vertices == pytest.approx(np.asarray(view_description["outline"]), abs=1e-6)


def test_aladin_layers_follow_the_description(view_description: dict) -> None:
    views = AladinViewsPanel.make_views(view_description)
    adapter = TypeAdapter(list[Layer])
    sky = {layer.id: layer for layer in adapter.validate_python(views["sky"]["layers"])}
    coverage = adapter.validate_python(views["coverage"]["layers"])
    assert list(sky) == ["trajectory", "detectors", "outline"]
    assert [layer.id for layer in coverage] == ["outline"]
    ra, dec = view_description["center"]
    for name in ("sky", "coverage"):
        assert views[name]["target"] == f"{ra} {dec}"
        assert views[name]["fov"] == view_description["size_deg"]
    detectors = sky["detectors"]
    assert isinstance(detectors, GraphicLayer)
    assert not detectors.visible
    assert len(detectors.shapes) == len(view_description["detectors"]["positions"])
    trajectory = sky["trajectory"]
    assert isinstance(trajectory, GraphicLayer)
    (polyline,) = trajectory.shapes
    assert isinstance(polyline, Polyline)
    assert np.asarray(polyline.vertices) == pytest.approx(
        np.asarray(view_description["trajectory"])
    )
    assert views["coverage_title"] == view_description["coverage_title"]
