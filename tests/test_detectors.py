import dataclasses
import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.coordinates.erfa_astrom import ErfaAstromInterpolator, erfa_astrom
from astropy.table import QTable
from astropy.time import Time

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import (
    MappingPresets,
    Trajectory,
    get_tel_trajectory,
    get_trajectory,
)
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.sources import PointSourceCatalog
from tolteca_simu.toltec import (
    TOLTEC_ARRAYS,
    DetectorPositions,
    get_detector_positions,
)

DATA = Path(__file__).parent / "data"
REFERENCE = json.loads((DATA / "v1_detector_positions_reference.json").read_text())
# The reference values were recorded with astropy 5.3. Its Earth orientation
# data and ERFA place horizon coordinates up to 8e-9 deg from the current ones,
# as for the boresight replay.
POSITION_ATOL_DEG = 1e-8
# Catalog images match v1 within this relative tolerance (see test_sources.py).
SURFACE_BRIGHTNESS_RTOL = 1e-9
ARRAY_NAMES = {array.index: name for name, array in TOLTEC_ARRAYS.items()}
# The fitted map from horizon to ICRS offsets reproduces transforming each
# position on its own to within 1e-13 deg (measured, 2026-10-31).
PER_POSITION_ATOL_DEG = 1e-12


@pytest.fixture(scope="module")
def apt(cal_data_path: Path) -> QTable:
    table = CalDataStore(cal_data_path).get_toltec_apt(REFERENCE["apt"])
    return table[REFERENCE["detector_index"]]


@pytest.fixture(scope="module")
def replayed(data_lmt_path: Path) -> Trajectory:
    lmt = pytest.importorskip("tolteca_datamodels.lmt")
    reference = REFERENCE["replay"]
    t = np.arange(0.0, 10.0, 1 / reference["f_smp"]) << u.s
    with lmt.open_lmt_tel(data_lmt_path / "tel" / reference["file"]) as ds:
        tel = ds.load().lmt_tel
    return get_tel_trajectory(tel, observer=get_lmt_observer(), t=t)


@pytest.fixture(scope="module")
def planned() -> Trajectory:
    reference = REFERENCE["planned"]
    preset = MappingPresets.from_yaml(get_default_presets_path()).get(
        reference["preset"]
    )
    pattern, _ = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    return get_trajectory(
        pattern,
        SkyCoord(reference["target"]),
        Time(reference["t0"]),
        t_exp=10 << u.s,
        ref_frame="altaz",
        observer=get_lmt_observer(),
        f_smp=reference["f_smp"] << u.Hz,
    )


def _assert_positions_equal_v1(positions: DetectorPositions, reference: dict) -> None:
    i = reference["time_index"]
    altaz = positions.coords_altaz[:, i]
    icrs = positions.coords_icrs[:, i]
    for name, values in (
        ("az", altaz.az),
        ("alt", altaz.alt),
        ("ra", icrs.ra),
        ("dec", icrs.dec),
    ):
        diff = values.degree - np.asarray(reference[name])
        if name in {"az", "ra"}:
            diff = (diff + 180.0) % 360.0 - 180.0
        assert np.abs(diff).max() < POSITION_ATOL_DEG, name


def test_replayed_positions_equal_v1(apt: QTable, replayed: Trajectory) -> None:
    positions = get_detector_positions(apt["x_t"], apt["y_t"], replayed)
    assert positions.coords_icrs.shape == (len(apt), REFERENCE["replay"]["n_times"])
    _assert_positions_equal_v1(positions, REFERENCE["replay"])


def test_planned_positions_equal_v1(apt: QTable, planned: Trajectory) -> None:
    positions = get_detector_positions(apt["x_t"], apt["y_t"], planned)
    assert positions.coords_icrs.shape == (len(apt), REFERENCE["planned"]["n_times"])
    _assert_positions_equal_v1(positions, REFERENCE["planned"])


def test_sources_along_replay_equal_v1(apt: QTable, replayed: Trajectory) -> None:
    reference = REFERENCE["replay"]
    catalog = PointSourceCatalog.read(
        DATA / reference["catalog"],
        flux_columns={name: f"flux_{name}" for name in TOLTEC_ARRAYS},
    )
    source = catalog.make_image_source(
        {name: array.a_fwhm for name, array in TOLTEC_ARRAYS.items()}
    )
    positions = get_detector_positions(apt["x_t"], apt["y_t"], replayed)
    labels = [ARRAY_NAMES[index] for index in np.asarray(apt["array"])]
    assert labels == reference["array_name"]
    i = reference["surface_brightness_time_index"]
    icrs = positions.coords_icrs[:, i]
    values = source.evaluate(labels, icrs.ra, icrs.dec)
    np.testing.assert_allclose(
        values.to_value(u.MJy / u.sr),
        reference["surface_brightness"],
        rtol=SURFACE_BRIGHTNESS_RTOL,
        atol=0,
    )


def _part(trajectory: Trajectory, part: slice) -> Trajectory:
    return dataclasses.replace(
        trajectory,
        **{
            field.name: getattr(trajectory, field.name)[part]
            for field in dataclasses.fields(trajectory)
        },
    )


def test_split_time_range_gives_the_same_positions(
    apt: QTable, planned: Trajectory
) -> None:
    # Spec: splitting an evaluation in time does not change the result.
    whole = get_detector_positions(apt["x_t"], apt["y_t"], planned)
    n = planned.t.size // 3
    parts = [
        get_detector_positions(apt["x_t"], apt["y_t"], _part(planned, part))
        for part in (slice(None, n), slice(n, None))
    ]
    for frame, attrs in (
        ("coords_altaz", ("az", "alt")),
        ("coords_icrs", ("ra", "dec")),
    ):
        for attr in attrs:
            joined = np.hstack([getattr(getattr(p, frame), attr).degree for p in parts])
            np.testing.assert_array_equal(
                joined, getattr(getattr(whole, frame), attr).degree
            )


def test_positions_follow_the_detector_order(apt: QTable, planned: Trajectory) -> None:
    positions = get_detector_positions(apt["x_t"], apt["y_t"], planned)
    reversed_ = get_detector_positions(apt["x_t"][::-1], apt["y_t"][::-1], planned)
    np.testing.assert_array_equal(
        reversed_.coords_icrs.ra.degree, positions.coords_icrs.ra.degree[::-1]
    )


@pytest.mark.parametrize("name", ["replayed", "planned"])
def test_positions_equal_per_position_transforms(
    apt: QTable, name: str, request: pytest.FixtureRequest
) -> None:
    trajectory: Trajectory = request.getfixturevalue(name)
    positions = get_detector_positions(apt["x_t"], apt["y_t"], trajectory)
    # Each detector and time transformed on its own, through astropy's frames.
    altaz = trajectory.coords_altaz
    alt = altaz.alt.radian
    x = apt["x_t"][:, np.newaxis]
    y = apt["y_t"][:, np.newaxis]
    with erfa_astrom.set(ErfaAstromInterpolator(300 << u.s)):
        expected_altaz = SkyCoord(
            np.cos(alt) * x - np.sin(alt) * y,
            np.sin(alt) * x + np.cos(alt) * y,
            frame=altaz.skyoffset_frame(),
        ).transform_to(altaz.frame)
        expected_icrs = expected_altaz.transform_to("icrs")
    for frame, expected in (
        ("coords_altaz", expected_altaz),
        ("coords_icrs", expected_icrs),
    ):
        separation = getattr(positions, frame).separation(expected)
        assert separation.max().to_value(u.deg) < PER_POSITION_ATOL_DEG, frame
