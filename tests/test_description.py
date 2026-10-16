import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time

from tolteca_simu.mapping import LissajousPattern
from tolteca_simu.planning import ObservationDescription, parse_target

LISSAJOUS = LissajousPattern(
    x_length=4 * u.arcmin,
    y_length=4 * u.arcmin,
    x_omega=0.5 * u.rad / u.s,
    y_omega=0.4 * u.rad / u.s,
    delta=45 * u.deg,
    rot=0 * u.deg,
)


@pytest.mark.parametrize(
    ("text", "ra_deg", "dec_deg"),
    [
        ("17.7d -2.1d", 17.7, -2.1),
        ("10h09m08s +20d19m18s", 152.28333333333333, 20.321666666666665),
    ],
)
def test_parse_target_coordinates(text: str, ra_deg: float, dec_deg: float) -> None:
    coord = parse_target(text)
    assert coord.ra.to_value(u.deg) == pytest.approx(ra_deg, abs=1e-12)
    assert coord.dec.to_value(u.deg) == pytest.approx(dec_deg, abs=1e-12)


def test_description_records_coordinate_not_name() -> None:
    resolved = SkyCoord(83.6324 * u.deg, 22.0174 * u.deg)
    description = ObservationDescription(
        target_name="M1",
        target=resolved,
        t0=Time("2026-01-15 06:00:00"),
        mapping=LISSAJOUS,
        ref_frame="icrs",
        t_exp=10 * u.min,
    )
    data = description.model_dump(mode="json")
    assert data["target_name"] == "M1"
    assert data["target"].endswith("d")
    assert "M1" not in data["target"]
    reloaded = ObservationDescription.model_validate(data)
    assert reloaded.target.separation(resolved).to_value(u.arcsec) < 1e-9
    assert reloaded.t0 == description.t0
    assert reloaded.mapping == LISSAJOUS
    assert reloaded.t_exp == 10 * u.min


def test_exposure_time_defaults_to_one_pass() -> None:
    description = ObservationDescription(
        target_name="M1",
        target=SkyCoord(83.6324 * u.deg, 22.0174 * u.deg),
        t0=Time("2026-01-15 06:00:00"),
        mapping=LISSAJOUS,
        ref_frame="altaz",
    )
    assert description.get_t_exp() == LISSAJOUS.t_pattern
