import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np
import pytest

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_tel_trajectory

if TYPE_CHECKING:
    from tolteca_datamodels.lmt.tel import LmtTelAccessor

lmt = pytest.importorskip("tolteca_datamodels.lmt")

REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_tel_replay_reference.json").read_text()
)
# The reference values were recorded with astropy 5.3. Its Earth orientation
# data and ERFA place horizon coordinates up to 8e-9 deg from the current ones.
ALTAZ_ATOL_DEG = 1e-8


def _kids_times(reference: dict, t_end: float) -> u.Quantity:
    return np.arange(0.0, t_end, 1 / reference["f_smp"]) << u.s


@pytest.fixture(params=REFERENCE["files"], ids=lambda r: r["file"])
def reference(request: pytest.FixtureRequest) -> dict:
    return request.param


@pytest.fixture
def tel(reference: dict, data_lmt_path: Path) -> Iterator["LmtTelAccessor"]:
    with lmt.open_lmt_tel(data_lmt_path / "tel" / reference["file"]) as ds:
        yield ds.load().lmt_tel


def test_replay_at_file_samples_equals_v1(
    reference: dict, tel: "LmtTelAccessor"
) -> None:
    trajectory = get_tel_trajectory(tel, observer=get_lmt_observer())
    i = reference["file_index"]
    assert trajectory.t.size == reference["n_samples"]
    assert trajectory.time[0].isot == reference["t0_isot"]
    np.testing.assert_array_equal(trajectory.t[i].to_value(u.s), reference["file_t"])
    np.testing.assert_allclose(
        trajectory.coords_icrs.ra.degree[i], reference["file_ra"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        trajectory.coords_icrs.dec.degree[i], reference["file_dec"], rtol=0, atol=1e-12
    )


def test_replay_at_kids_rate_equals_v1(reference: dict, tel: "LmtTelAccessor") -> None:
    t_end = get_tel_trajectory(tel, observer=get_lmt_observer()).t[-1]
    t = _kids_times(reference, t_end.to_value(u.s))
    trajectory = get_tel_trajectory(tel, observer=get_lmt_observer(), t=t)
    i = reference["kids_index"]
    assert t.size == reference["n_kids"]
    np.testing.assert_allclose(
        trajectory.coords_icrs.ra.degree[i], reference["kids_ra"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        trajectory.coords_icrs.dec.degree[i], reference["kids_dec"], rtol=0, atol=1e-12
    )
    np.testing.assert_array_equal(
        trajectory.turnaround[i], np.array(reference["kids_holdflag"]) != 0
    )
    altaz = trajectory.coords_altaz[i]
    np.testing.assert_allclose(
        altaz.az.degree, reference["kids_az"], rtol=0, atol=ALTAZ_ATOL_DEG
    )
    np.testing.assert_allclose(
        altaz.alt.degree, reference["kids_alt"], rtol=0, atol=ALTAZ_ATOL_DEG
    )


def test_replay_interpolates_across_0h(reference: dict, tel: "LmtTelAccessor") -> None:
    # Constructed case: no reference file crosses 0h. The recorded right
    # ascensions are shifted so that the trajectory straddles it.
    observer = get_lmt_observer()
    ra = tel.ra
    shift = np.radians(reference["target_ra"])
    tel.data_source[ra.name] = (ra - shift) % (2 * np.pi)
    t = _kids_times(reference, 30.0)
    shifted = get_tel_trajectory(tel, observer=observer, t=t).coords_icrs.ra
    tel.data_source[ra.name] = ra
    original = get_tel_trajectory(tel, observer=observer, t=t).coords_icrs.ra
    expected = (original.degree - reference["target_ra"]) % 360.0
    assert shifted.degree.min() < 1
    assert shifted.degree.max() > 359
    np.testing.assert_allclose(
        np.unwrap(shifted.degree, period=360),
        np.unwrap(expected, period=360),
        atol=1e-9,
    )


def test_replay_rejects_times_outside_the_file(tel: "LmtTelAccessor") -> None:
    with pytest.raises(ValueError, match="above the interpolation range"):
        get_tel_trajectory(tel, observer=get_lmt_observer(), t=[0, 1e4] << u.s)
