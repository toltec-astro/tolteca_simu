import astropy.units as u
import pytest
from pydantic import ValidationError

from tolteca_simu.planning import MappingPresets
from tolteca_simu.planning.presets import get_default_presets_path

PRESETS = MappingPresets.from_yaml(get_default_presets_path())


def test_default_presets_are_production_rev20251014() -> None:
    assert [p.key for p in PRESETS.presets] == [
        "toltec_polarimetry_raster",
        "toltec_blank_field_raster",
        "toltec_blank_field_rastajous",
        "toltec_blank_field_double_lissajous",
        "toltec_blank_field_lissajous",
    ]
    polarimetry = PRESETS.get("toltec_polarimetry_raster")
    assert polarimetry.conditions == {"polarized": True}
    t_turnaround = polarimetry.params["t_turnaround"]
    assert not t_turnaround.editable
    assert not t_turnaround.visible


def test_presets_round_trip() -> None:
    data = PRESETS.model_dump(mode="json")
    assert MappingPresets.model_validate(data) == PRESETS


def test_preset_rejects_values_outside_range() -> None:
    preset = PRESETS.get("toltec_blank_field_lissajous")
    values = {name: p.value for name, p in preset.params.items()}
    values["t_exp"] = 90
    with pytest.raises(ValueError, match="t_exp=90 is outside"):
        preset.make_mapping(values)


def test_preset_requires_every_parameter() -> None:
    preset = PRESETS.get("toltec_blank_field_lissajous")
    values = {name: p.value for name, p in preset.params.items()}
    del values["delta"]
    with pytest.raises(ValueError, match="Expected parameters"):
        preset.make_mapping(values)


def test_preset_exposure_time() -> None:
    preset = PRESETS.get("toltec_blank_field_double_lissajous")
    _, t_exp = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    assert t_exp == 30 * u.min


def test_presets_reject_duplicate_keys() -> None:
    data = PRESETS.model_dump(mode="json")
    data["presets"].append(data["presets"][0])
    with pytest.raises(ValidationError, match="not unique"):
        MappingPresets.model_validate(data)
