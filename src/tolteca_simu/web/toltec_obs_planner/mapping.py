"""Mapping pattern of the observation description, chosen from presets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import astropy.units as u
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, dcc
from dash_component_template import Template
from pydantic import ValidationError

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import MappingPreset, MappingPresets

__all__ = ["MappingPanel"]

_PARAM_ID_TYPE = "mapping-preset-param"
_REF_FRAMES = [
    {"label": "Az/Alt", "value": "altaz"},
    {"label": "RA/Dec", "value": "icrs"},
]
_DESIRED_SENS_DEFAULT = 1.0  # mJy/beam


def _is_enabled(preset: MappingPreset, conditions: dict[str, Any]) -> bool:
    return all(conditions.get(k) == v for k, v in preset.conditions.items())


def _ref_frame_options(*, polarized: bool) -> list[dict[str, Any]]:
    # Polarimetry maps in RA/Dec only.
    return [o | {"disabled": polarized and o["value"] == "altaz"} for o in _REF_FRAMES]


class MappingPanel(Template):
    """Preset choice, preset parameters, and the reference frame.

    The panel publishes, serialized as JSON, the mapping part of the observation
    description in its `mapping` store: ``mapping``, ``ref_frame``, ``t_exp``
    and ``desired_sens``. The store holds None while the parameters are invalid.
    Presets whose conditions the instrument settings do not meet are disabled.

    Parameters
    ----------
    presets : tolteca_simu.planning.MappingPresets
        The presets to offer; the first enabled one is selected initially.
    t_exp_max : astropy.units.Quantity
        Longest duration accepted for a preset without an exposure time.
    instrument : dash_component_template.LazyComponent
        Store holding the instrument settings, whose values are the conditions.
    """

    def __init__(
        self,
        presets: MappingPresets,
        t_exp_max: u.Quantity,
        instrument: LazyComponent,
    ) -> None:
        super().__init__()
        self._presets = presets
        self._t_exp_max = t_exp_max
        self._instrument = instrument
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Mapping", order=5)
        self._desired_sens = stack.child[dmc.NumberInput](
            label="Desired map RMS",
            description="Sets the number of passes of the pattern.",
            value=_DESIRED_SENS_DEFAULT,
            min=0,
            rightSection="mJy/beam",
            rightSectionWidth=72,
            size="xs",
        )
        data, value = self._make_preset_options({"polarized": False})
        self._preset_select = stack.child[dmc.Select](
            label="Mapping preset", data=data, value=value, allowDeselect=False
        )
        self._preset_text = stack.child[dmc.Text](size="xs", c="dimmed")
        self._forms = []
        for preset in presets.presets:
            form = stack.child[dmc.Stack](gap="xs")
            for name, param in preset.params.items():
                param_input = form.child[dmc.NumberInput](
                    id={"type": _PARAM_ID_TYPE, "preset": preset.key, "param": name},
                    label=name,
                    description=param.description,
                    value=param.value,
                    min=param.min,
                    max=param.max,
                    rightSection=None if param.unit is None else str(param.unit),
                    rightSectionWidth=72,
                    disabled=not param.editable,
                    size="xs",
                    display=None if param.visible else "none",
                )
            self._forms.append(form)
        # Any parameter input supplies the pattern-matching id of them all.
        self._param_input = param_input
        self._ref_frame = stack.child[dmc.SegmentedControl](
            data=_REF_FRAMES, value="altaz", size="xs"
        )
        self._status = stack.child[dmc.Text](size="xs")
        self.mapping = stack.child[dcc.Store](data=None)

    def _make_preset_options(
        self, conditions: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        enabled = [p.key for p in self._presets.presets if _is_enabled(p, conditions)]
        data: list[dict[str, Any]] = [
            {"value": p.key, "label": p.label, "disabled": p.key not in enabled}
            for p in self._presets.presets
        ]
        return data, enabled[0]

    def setup_callbacks(self, app: Dash) -> None:
        """Show the chosen preset and publish its mapping.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        keys = [preset.key for preset in self._presets.presets]
        texts = {p.key: p.description or "" for p in self._presets.presets}
        app.clientside_callback(
            f"""
            function(key) {{
                const keys = {json.dumps(keys)};
                const texts = {json.dumps(texts)};
                return [texts[key]].concat(keys.map(
                    k => (k === key ? {{}} : {{display: "none"}})));
            }}
            """,
            Output(self._preset_text(), "children"),
            [Output(form(), "style") for form in self._forms],
            Input(self._preset_select(), "value"),
        )
        params = self._param_input({"preset": ALL, "param": ALL})

        @app.callback(
            Output(self._preset_select(), "data"),
            Output(self._preset_select(), "value"),
            Output(self._ref_frame(), "data"),
            Output(self._ref_frame(), "value"),
            Input(self._instrument(), "data"),
            State(self._preset_select(), "value"),
            State(self._ref_frame(), "value"),
        )
        def _apply_conditions(
            instrument: dict[str, Any] | None, key: str, ref_frame: str
        ) -> tuple:
            conditions = {
                k: v for k, v in (instrument or {}).items() if isinstance(v, bool)
            }
            data, first_enabled = self._make_preset_options(conditions)
            if not _is_enabled(self._presets.get(key), conditions):
                key = first_enabled
            polarized = bool(conditions.get("polarized", False))
            frames = _ref_frame_options(polarized=polarized)
            if polarized:
                ref_frame = "icrs"
            return data, key, frames, ref_frame

        @app.callback(
            Output(self.mapping(), "data"),
            Output(self._status(), "children"),
            Output(self._status(), "c"),
            Input(self._preset_select(), "value"),
            Input(params, "value"),
            Input(self._ref_frame(), "value"),
            Input(self._desired_sens(), "value"),
            State(params, "id"),
        )
        def _make_mapping(
            key: str,
            values: list,
            ref_frame: str,
            desired_sens: float | None,
            ids: list[dict[str, str]],
        ) -> tuple[dict[str, Any] | None, str, str]:
            if desired_sens is None or desired_sens == "" or float(desired_sens) <= 0:
                return None, "Enter a positive desired map RMS.", "red"
            preset = self._presets.get(key)
            selected = {
                i["param"]: v
                for i, v in zip(ids, values, strict=True)
                if i["preset"] == key
            }
            if any(v is None or v == "" for v in selected.values()):
                return None, "Enter every parameter.", "red"
            try:
                pattern, t_exp = preset.make_mapping(selected)
            except (ValueError, ValidationError) as error:
                return None, f"Invalid parameters: {error}", "red"
            t_pattern = pattern.t_pattern
            if t_exp is not None:
                message = (
                    f"Total exposure time: {t_exp}. "
                    f"Time to finish one pass: {t_pattern:.2f}."
                )
            elif t_pattern > self._t_exp_max:
                message = (
                    f"The pattern takes {t_pattern:.2f} to finish, which exceeds "
                    f"the maximum of {self._t_exp_max}."
                )
                return None, message, "red"
            else:
                message = f"Time to finish the pattern: {t_pattern:.2f}."
            data = {
                "mapping": pattern.model_dump(mode="json"),
                "ref_frame": ref_frame,
                "t_exp": None if t_exp is None else f"{t_exp.to_value(u.s)!r} s",
                "desired_sens": f"{float(desired_sens)!r} mJy",
            }
            return data, message, "dimmed"
