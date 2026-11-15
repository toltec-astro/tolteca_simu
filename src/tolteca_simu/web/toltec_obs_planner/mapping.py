"""Mapping pattern of the observation description, chosen from presets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, dcc
from dash.exceptions import PreventUpdate
from dash_component_template import Template
from pydantic import TypeAdapter, ValidationError
from tollan.config.types import TimeQuantityField

from tolteca_simu.mapping import (
    DoubleLissajousPattern,
    LissajousPattern,
    RastajousPattern,
    RasterPattern,
)

from .controls import (
    feedback,
    field,
    field_props,
    hover_card,
    labeled_choice,
    titled_card,
    tooltip,
    with_tooltip,
)

if TYPE_CHECKING:
    import astropy.units as u
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.mapping import MappingPattern
    from tolteca_simu.planning import MappingPreset, MappingPresets, PresetParam

__all__ = ["MappingPanel", "make_preset_data"]

_t_exp_adapter = TypeAdapter(TimeQuantityField | None)


def make_preset_data(
    pattern: MappingPattern, t_exp: u.Quantity | None
) -> dict[str, Any]:
    """Return the mapping pattern and exposure time of a preset, as JSON.

    Parameters
    ----------
    pattern : tolteca_simu.mapping.MappingPattern
        The mapping pattern.
    t_exp : astropy.units.Quantity or None
        Exposure time; None observes the pattern once.

    Returns
    -------
    dict
        ``mapping`` and ``t_exp``, serialized by their field types. The page
        adds ``ref_frame`` and ``desired_sens`` to make the mapping part of
        the observation description.
    """
    return {
        "mapping": pattern.model_dump(mode="json"),
        "t_exp": _t_exp_adapter.dump_python(t_exp, mode="json"),
    }


_PARAM_ID_TYPE = "mapping-preset-param"

_DESIRED_SENS_DEFAULT = 1.0  # mJy/beam
_DESIRED_SENS_LABEL = "Desired Map RMS (mJy/beam)"
_REF_FRAME_LABEL = "Mapping Reference Frame"
# v1 obs_planner: the explanation of the desired map RMS.
_DESIRED_SENS_TOOLTIP = """
The desired map RMS. This determines the number of passes the mapping pattern
defined below being executed. Fractional numbers will be rounded up, and the
reporting table will list the actual map RMS with the given passes and the
overhead involved in carrying out the calculation. Therefore it is advertised to
have integer number of passes, which can be achieved by either changing the
mapping pattern time (per-pass execution time, via tweaking the t_exp
(lissajous-like) or length/space/speed (raster)), or this value directly after
getting the initial execution output for the per-pass map RMS.
"""
_PATTERN_FIELDS = {
    cls.model_fields["type"].default: cls.model_fields
    for cls in (
        RasterPattern,
        LissajousPattern,
        DoubleLissajousPattern,
        RastajousPattern,
    )
}


def _ref_frame_options(*, polarized: bool) -> list[dict[str, Any]]:
    # Polarimetry maps in RA/Dec only.
    return [
        {"label": "AZ/Alt", "value": "altaz", "disabled": polarized},
        {"label": "RA/Dec", "value": "icrs", "disabled": False},
    ]


def _is_enabled(preset: MappingPreset, conditions: dict[str, Any]) -> bool:
    return all(conditions.get(k) == v for k, v in preset.conditions.items())


def _param_placeholder(param: PresetParam) -> str:
    vmin = "-∞" if param.min is None else f"{param.min:g}"
    vmax = "+∞" if param.max is None else f"{param.max:g}"
    return f"{param.value:g} [{vmin}, {vmax}]"


def _param_tooltip(preset: MappingPreset, name: str, param: PresetParam) -> str:
    # As v1: the preset's help text, or the pattern's description of the field.
    pattern_field = _PATTERN_FIELDS[preset.pattern].get(name)
    text = param.description or (pattern_field and pattern_field.description) or ""
    default = _param_placeholder(param)
    if param.unit is not None:
        default = f"{default} {param.unit}"
    return f"{text} Preset default: {default}".strip()


def _desired_sens_feedback(desired_sens: float | str | None) -> tuple:
    if desired_sens is None or desired_sens == "":
        return feedback("Desired map RMS is required", valid=False)
    if float(desired_sens) <= 0:
        return feedback("Desired map RMS must be positive.", valid=False)
    return feedback(None, valid=True)


class MappingPanel(Template):
    """Desired depth, preset choice, preset parameters, and the reference frame.

    As in v1, no preset is chosen at first; choosing one shows its
    parameters. The panel publishes the mapping part of the observation
    description in its `mapping` store: ``mapping`` and ``t_exp``, serialized
    by their field types, and ``ref_frame`` and ``desired_sens``, as entered.
    The store holds None until a preset with valid parameters and a valid
    desired depth are entered; the `preset_select` shows an error until a
    preset with valid parameters is chosen. Presets whose conditions the instrument
    settings do not meet are disabled; when the settings change which presets
    are enabled, the choice is cleared.

    Parameters
    ----------
    presets : tolteca_simu.planning.MappingPresets
        The presets to offer.
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
        _, stack = titled_card(self, "Mapping")
        self._desired_sens = field(
            with_tooltip(stack, _DESIRED_SENS_TOOLTIP),
            dmc.NumberInput,
            _DESIRED_SENS_LABEL,
            checked=True,
            value=_DESIRED_SENS_DEFAULT,
            min=0,
            placeholder="1.0",
            hideControls=True,
            clampBehavior="none",
            debounce=True,
        )
        preset_target, self._preset_text = hover_card(stack)
        self.preset_select = field(
            preset_target,
            dmc.Select,
            checked=True,
            data=self._make_preset_options({"polarized": False}),
            value=None,
            placeholder="Choose a mapping pattern template to edit ...",
            allowDeselect=False,
        )
        # The parameters of the chosen preset, made on selection.
        self._form = stack.child[dmc.Stack](gap="xs")
        self._ref_frame = labeled_choice(
            stack, _REF_FRAME_LABEL, _ref_frame_options(polarized=False), "altaz"
        )
        # Where the page adds its Execute button.
        self.footer = stack.child[dmc.Stack](gap="xs")
        self._preset_data = stack.child[dcc.Store](data=None)
        self.mapping = stack.child[dcc.Store](data=None)

    def _make_preset_options(self, conditions: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "value": p.key,
                "label": p.label,
                "disabled": not _is_enabled(p, conditions),
            }
            for p in self._presets.presets
        ]

    def setup_callbacks(self, app: Dash) -> None:
        """Show the chosen preset and publish its mapping.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        # As v1's preset popover: the description, or the pattern type, and
        # the long description.
        texts = {
            p.key: [
                p.description or f"mapping type: {p.pattern}",
                p.description_long or "",
            ]
            for p in self._presets.presets
        }
        app.clientside_callback(
            f"""
            function(key) {{
                const texts = {json.dumps(texts)};
                if (!key) {{
                    return window.dash_clientside.no_update;
                }}
                return texts[key].filter(t => t).map(children => ({{
                    namespace: "dash_mantine_components", type: "Text",
                    props: {{children, size: "sm"}},
                }}));
            }}
            """,
            Output(self._preset_text(), "children"),
            Input(self.preset_select(), "value"),
        )
        form_id = self._form().id
        app.callback(
            Output(self._form(), "children"),
            Input(self.preset_select(), "value"),
        )(lambda key: self._make_form(form_id, key))
        app.callback(
            Output(self.preset_select(), "data"),
            Output(self.preset_select(), "value"),
            Output(self._ref_frame(), "data"),
            Output(self._ref_frame(), "value"),
            Input(self._instrument(), "data"),
            State(self.preset_select(), "data"),
            State(self._ref_frame(), "data"),
        )(self._apply_conditions)
        params = {"type": _PARAM_ID_TYPE, "form": form_id}
        preset_select = self.preset_select()
        app.callback(
            Output(self._preset_data(), "data"),
            Output(preset_select, "error"),
            Output(preset_select, "description"),
            Output(preset_select, "mod"),
            # Dash does not call this when all parameter inputs are removed,
            # so the choice itself is an input too.
            Input(preset_select, "value"),
            Input(params | {"preset": ALL, "param": ALL}, "value"),
            State(params | {"preset": ALL, "param": ALL}, "id"),
        )(self._make_preset_data)
        desired_sens_input = self._desired_sens()
        app.callback(
            Output(desired_sens_input, "error"),
            Output(desired_sens_input, "description"),
            Output(desired_sens_input, "mod"),
            Input(desired_sens_input, "value"),
        )(_desired_sens_feedback)
        # As v1: the mapping part is assembled in the browser.
        app.clientside_callback(
            """
            function(desiredSens, desiredSensError, refFrame, presetData) {
                if (!presetData || desiredSensError) {
                    return null;
                }
                return Object.assign({}, presetData, {
                    ref_frame: refFrame,
                    desired_sens: desiredSens + " mJy",
                });
            }
            """,
            Output(self.mapping(), "data"),
            Input(desired_sens_input, "value"),
            Input(desired_sens_input, "error"),
            Input(self._ref_frame(), "value"),
            Input(self._preset_data(), "data"),
        )

    def _make_form(self, form_id: str, key: str | None) -> list[Any] | None:
        # As v1: the parameter inputs of the chosen preset, each with its
        # tooltip.
        if not key:
            return None
        preset = self._presets.get(key)
        inputs = []
        for name, param in preset.params.items():
            param_input = dmc.NumberInput(
                id={
                    "type": _PARAM_ID_TYPE,
                    "form": form_id,
                    "preset": preset.key,
                    "param": name,
                },
                value=param.value,
                min=param.min,
                max=param.max,
                placeholder=_param_placeholder(param),
                hideControls=True,
                clampBehavior="none",
                disabled=not param.editable,
                display=None if param.visible else "none",
                **field_props(
                    name, unit=None if param.unit is None else str(param.unit)
                ),
            )
            # A hidden parameter takes no room, so it has no tooltip.
            inputs.append(
                tooltip(param_input, _param_tooltip(preset, name, param))
                if param.visible
                else param_input
            )
        return inputs

    def _make_preset_data(
        self, key: str | None, values: list, ids: list[dict[str, str]]
    ) -> tuple:
        if not key:
            return None, *feedback("Invalid mapping settings.", valid=False)
        selected = {
            i["param"]: v
            for i, v in zip(ids, values, strict=True)
            if i["preset"] == key
        }
        # The inputs of a newly chosen preset are made after the choice.
        if not selected:
            raise PreventUpdate
        if any(v is None or v == "" for v in selected.values()):
            return None, *feedback("Invalid mapping settings.", valid=False)
        preset = self._presets.get(key)
        try:
            pattern, t_exp = preset.make_mapping(selected)
        except (ValueError, ValidationError) as error:
            message = f"Invalid mapping settings: {error}"
            return None, *feedback(message, valid=False)
        t_pattern = pattern.t_pattern
        if t_exp is not None:
            message = (
                f"Total exposure time: {t_exp}. "
                f"Time to finish one pass: {t_pattern:.2f}."
            )
        elif t_pattern > self._t_exp_max:
            message = (
                f"The pattern takes {t_pattern:.2f} to finish, which exceeds "
                f"the required maximum value of {self._t_exp_max}."
            )
            return None, *feedback(message, valid=False)
        else:
            message = f"Time to finish the pattern: {t_pattern:.2f}."
        return make_preset_data(pattern, t_exp), *feedback(message, valid=True)

    def _apply_conditions(
        self,
        instrument: dict[str, Any] | None,
        preset_options: list[dict[str, Any]],
        ref_frame_options: list[dict[str, Any]],
    ) -> tuple:
        # As v1: options that do not change are left alone; changed preset
        # options clear the choice, and changed reference frames choose the
        # first enabled one.
        if instrument is None:
            raise PreventUpdate
        conditions = {k: v for k, v in instrument.items() if isinstance(v, bool)}
        presets: Any = self._make_preset_options(conditions)
        preset: Any = None
        if presets == preset_options:
            presets = preset = dash.no_update
        ref_frames: Any = _ref_frame_options(
            polarized=bool(conditions.get("polarized", False))
        )
        ref_frame: Any = next(o["value"] for o in ref_frames if not o["disabled"])
        if ref_frames == ref_frame_options:
            ref_frames = ref_frame = dash.no_update
        return presets, preset, ref_frames, ref_frame
