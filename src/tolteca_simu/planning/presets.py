"""Named mapping patterns with default values and permitted ranges."""

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self

import astropy.units as u
from pydantic import ConfigDict, Field, TypeAdapter, model_validator
from tollan.config import FrozenBaseModel
from tollan.config.types import UnitField
from tollan.utils.yaml import yaml_load

from tolteca_simu.mapping import MappingPattern

__all__ = ["MappingPreset", "MappingPresets", "PresetParam", "get_default_presets_path"]

_pattern_adapter = TypeAdapter(MappingPattern)

# Preset parameters that are not pattern parameters.
_T_EXP = "t_exp"
_SPEED_LISSAJOUS = "speed_lissajous"


def get_default_presets_path() -> Path:
    """Return the path of the presets shipped with the package.

    Returns
    -------
    pathlib.Path
        The TolTEC planner presets, converted from production revision
        ``rev20251014.0``.
    """
    return Path(
        str(files("tolteca_simu").joinpath("data/toltec_obs_planner_presets.yaml"))
    )


class PresetParam(FrozenBaseModel):  # numpydoc ignore=PR02
    """Default value and permitted range of one preset parameter.

    Parameters
    ----------
    value : float
        Default value.
    unit : astropy.units.Unit, optional
        Unit of the value and range; None for a count.
    min, max : float, optional
        Inclusive permitted range; None leaves that side open.
    editable : bool
        Whether the observer may change the value.
    visible : bool
        Whether the planner shows the parameter.
    description : str, optional
        Help text for the parameter.
    """

    model_config = ConfigDict(extra="forbid")
    value: float = Field(description="Default value.")
    unit: UnitField | None = Field(default=None, description="Unit; None for a count.")
    min: float | None = Field(default=None, description="Inclusive lower limit.")
    max: float | None = Field(default=None, description="Inclusive upper limit.")
    editable: bool = Field(default=True, description="Whether the value may change.")
    visible: bool = Field(default=True, description="Whether the planner shows it.")
    description: str | None = Field(default=None, description="Help text.")


class MappingPreset(FrozenBaseModel):  # numpydoc ignore=PR02
    """A named mapping pattern with default values and permitted ranges.

    Parameters
    ----------
    key : str
        Unique identifier.
    label : str
        Name shown to observers.
    conditions : dict
        Instrument settings required for the preset to apply, such as
        ``{"polarized": True}``.
    description, description_long : str, optional
        Short and long descriptions.
    pattern : str
        Mapping pattern type; see `tolteca_simu.mapping.MappingPattern`.
    params : dict of PresetParam
        Pattern parameters, plus the optional ``t_exp`` (exposure time) and
        ``speed_lissajous`` (average speed of the major Lissajous figure).
    """

    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="Unique identifier.")
    label: str = Field(description="Name shown to observers.")
    conditions: dict[str, bool | str | float] = Field(
        default_factory=dict, description="Instrument settings the preset requires."
    )
    description: str | None = Field(default=None, description="Short description.")
    description_long: str | None = Field(default=None, description="Long description.")
    pattern: Literal["raster", "lissajous", "double_lissajous", "rastajous"] = Field(
        description="Mapping pattern type."
    )
    params: dict[str, PresetParam] = Field(description="Parameters by name.")

    @model_validator(mode="after")
    def _defaults_make_a_pattern(self) -> Self:
        self.make_mapping({name: p.value for name, p in self.params.items()})
        return self

    def make_mapping(
        self, values: Mapping[str, float]
    ) -> tuple[MappingPattern, u.Quantity | None]:
        """Return the mapping pattern and exposure time for parameter values.

        Parameters
        ----------
        values : dict
            Value of every parameter, in the parameter's unit.

        Returns
        -------
        tuple
            The mapping pattern, with Lissajous frequencies scaled to
            ``speed_lissajous`` when given, and ``t_exp``, or None.

        Raises
        ------
        ValueError
            If a parameter is missing, unknown, or outside its range.
        """
        if set(values) != set(self.params):
            msg = f"Expected parameters {sorted(self.params)}, got {sorted(values)}"
            raise ValueError(msg)
        quantities: dict[str, Any] = {}
        for name, param in self.params.items():
            value = values[name]
            if (param.min is not None and value < param.min) or (
                param.max is not None and value > param.max
            ):
                msg = f"{name}={value} is outside [{param.min}, {param.max}]"
                raise ValueError(msg)
            if param.unit is not None:
                quantities[name] = value << param.unit
            else:
                # Counts such as n_scans validate as integers.
                quantities[name] = int(value) if float(value).is_integer() else value
        t_exp = quantities.pop(_T_EXP, None)
        speed = quantities.pop(_SPEED_LISSAJOUS, None)
        pattern = _pattern_adapter.validate_python({"type": self.pattern, **quantities})
        if speed is not None:
            pattern = pattern.with_lissajous_speed(speed)
        return pattern, t_exp


class MappingPresets(FrozenBaseModel):  # numpydoc ignore=PR02
    """The mapping presets offered by a planner.

    Parameters
    ----------
    presets : list of MappingPreset
        Presets in display order, with unique keys.
    """

    model_config = ConfigDict(extra="forbid")
    presets: list[MappingPreset] = Field(min_length=1, description="The presets.")

    @model_validator(mode="after")
    def _keys_are_unique(self) -> Self:
        keys = [preset.key for preset in self.presets]
        if len(set(keys)) != len(keys):
            msg = f"Preset keys are not unique: {keys}"
            raise ValueError(msg)
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load presets from a YAML file.

        Parameters
        ----------
        path : pathlib.Path
            File with a ``presets`` list.

        Returns
        -------
        MappingPresets
            The validated presets.
        """
        return cls.model_validate(yaml_load(path))

    def get(self, key: str) -> MappingPreset:
        """Return the preset with a key.

        Parameters
        ----------
        key : str
            Preset key.

        Returns
        -------
        MappingPreset
            The preset.

        Raises
        ------
        KeyError
            If no preset has the key.
        """
        for preset in self.presets:
            if preset.key == key:
                return preset
        raise KeyError(key)
