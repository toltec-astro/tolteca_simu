import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time

from tolteca_simu.planning import ObservationDescription, parse_target


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
        target_name="M1", target=resolved, t0=Time("2026-01-15 06:00:00")
    )
    data = description.model_dump(mode="json")
    assert data["target_name"] == "M1"
    assert data["target"].endswith("d")
    assert "M1" not in data["target"]
    reloaded = ObservationDescription.model_validate(data)
    assert reloaded.target.separation(resolved).to_value(u.arcsec) < 1e-9
    assert reloaded.t0 == description.t0
