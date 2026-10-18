import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time

from tolteca_simu.mapping import LissajousPattern
from tolteca_simu.planning import MappingPresets, ObservationDescription, parse_target
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.settings import ToltecSettings
from tolteca_simu.web.toltec_obs_planner.mapping import make_mapping_data

PRESETS = MappingPresets.from_yaml(get_default_presets_path())

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
        atm_model_name="am_q25",
        instrument=ToltecSettings(polarized=False, array_name="a1100"),
        desired_sens=1 * u.mJy,
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
    assert reloaded.instrument == description.instrument
    assert reloaded.desired_sens == 1 * u.mJy


def test_exposure_time_defaults_to_one_pass() -> None:
    description = ObservationDescription(
        target_name="M1",
        target=SkyCoord(83.6324 * u.deg, 22.0174 * u.deg),
        t0=Time("2026-01-15 06:00:00"),
        mapping=LISSAJOUS,
        ref_frame="altaz",
        atm_model_name="am_q25",
        instrument=ToltecSettings(polarized=False, array_name="a1100"),
        desired_sens=1 * u.mJy,
    )
    assert description.get_t_exp() == LISSAJOUS.t_pattern


@pytest.mark.parametrize("key", [p.key for p in PRESETS.presets])
def test_mapping_panel_data_validates(key: str) -> None:
    # Regression: NumPy 2 reprs of quantities do not parse as quantities.
    preset = PRESETS.get(key)
    pattern, t_exp = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    data = make_mapping_data(pattern, "icrs", t_exp, 0.5 * u.mJy)
    description = ObservationDescription.model_validate(
        data
        | {
            "target_name": "M1",
            "target": "83.6324d 22.0174d",
            "t0": "2026-01-15T06:00:00",
            "atm_model_name": "am_q25",
            "instrument": {"polarized": False, "array_name": "a1100"},
        }
    )
    assert description.mapping == pattern
    assert description.t_exp == t_exp
    assert description.desired_sens == 0.5 * u.mJy
