"""Mapping pattern of the observation description, chosen from presets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import astropy.units as u
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
from tolteca_simu.planning.description import FluxDensityQuantityField

from .controls import feedback, field, labeled_choice, section_width, with_tooltip

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.mapping import MappingPattern
    from tolteca_simu.planning import MappingPreset, MappingPresets, PresetParam

__all__ = ["MappingPanel", "make_mapping_data"]

_t_exp_adapter = TypeAdapter(TimeQuantityField | None)
_desired_sens_adapter = TypeAdapter(FluxDensityQuantityField)


def make_mapping_data(
    pattern: MappingPattern,
    ref_frame: str,
    t_exp: u.Quantity | None,
    desired_sens: u.Quantity,
) -> dict[str, Any]:
    """Return the mapping part of an observation description, as JSON.

    Parameters
    ----------
    pattern : tolteca_simu.mapping.MappingPattern
        The mapping pattern.
    ref_frame : {"altaz", "icrs"}
        Frame of the pattern offsets.
    t_exp : astropy.units.Quantity or None
        Exposure time; None observes the pattern once.
    desired_sens : astropy.units.Quantity
        Desired coadded map depth.

    Returns
    -------
    dict
        ``mapping``, ``ref_frame``, ``t_exp`` and ``desired_sens``, serialized
        by their field types.
    """
    return {
        "mapping": pattern.model_dump(mode="json"),
        "ref_frame": ref_frame,
        "t_exp": _t_exp_adapter.dump_python(t_exp, mode="json"),
        "desired_sens": _desired_sens_adapter.dump_python(desired_sens, mode="json"),
    }


_PARAM_ID_TYPE = "mapping-preset-param"
_REF_FRAMES = [
    {"label": "Az/Alt", "value": "altaz"},
    {"label": "RA/Dec", "value": "icrs"},
]
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
        card = self.child[dmc.Card](withBorder=True, padding="sm")
        stack = card.child[dmc.Stack](gap="xs")
        stack.child[dmc.Title]("Mapping", order=5)
        self._desired_sens = field(
            with_tooltip(stack, _DESIRED_SENS_TOOLTIP),
            dmc.NumberInput,
            _DESIRED_SENS_LABEL,
            checked=True,
            value=_DESIRED_SENS_DEFAULT,
            min=0,
            placeholder="1.0",
            hideControls=True,
        )
        data, value = self._make_preset_options({"polarized": False})
        preset_card = stack.child[dmc.HoverCard](
            width=360, shadow="md", withArrow=True, position="bottom-start"
        )
        self._preset_select = field(
            preset_card.child[dmc.HoverCardTarget](boxWrapperProps={"w": "100%"}),
            dmc.Select,
            checked=True,
            data=data,
            value=value,
            placeholder="Choose a mapping pattern template to edit ...",
            allowDeselect=False,
        )
        self._preset_text = preset_card.child[dmc.HoverCardDropdown]().child[dmc.Stack](
            gap="xs"
        )
        param_width = section_width(
            [name for p in presets.presets for name in p.params]
        )
        self._forms = []
        for preset in presets.presets:
            form = stack.child[dmc.Stack](gap="xs")
            for name, param in preset.params.items():
                # A hidden parameter takes no room, so it has no tooltip.
                parent = (
                    with_tooltip(form, _param_tooltip(preset, name, param))
                    if param.visible
                    else form
                )
                param_input = field(
                    parent,
                    dmc.NumberInput,
                    name,
                    label_width=param_width,
                    unit=None if param.unit is None else str(param.unit),
                    id={"type": _PARAM_ID_TYPE, "preset": preset.key, "param": name},
                    value=param.value,
                    min=param.min,
                    max=param.max,
                    placeholder=_param_placeholder(param),
                    hideControls=True,
                    disabled=not param.editable,
                    display=None if param.visible else "none",
                )
            self._forms.append(form)
        # Any parameter input supplies the pattern-matching id of them all.
        self._param_input = param_input
        self._ref_frame, ref_frame_chips = labeled_choice(
            stack, _REF_FRAME_LABEL, _REF_FRAMES, "altaz"
        )
        self._altaz_chip = ref_frame_chips["altaz"]
        # Where the page adds its Execute button.
        self.footer = stack.child[dmc.Stack](gap="xs")
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
                const keys = {json.dumps(keys)};
                const texts = {json.dumps(texts)};
                const text = (children) => ({{
                    namespace: "dash_mantine_components", type: "Text",
                    props: {{children, size: "xs"}},
                }});
                return [texts[key].filter(t => t).map(text)].concat(keys.map(
                    k => (k === key ? {{}} : {{display: "none"}})));
            }}
            """,
            Output(self._preset_text(), "children"),
            [Output(form(), "style") for form in self._forms],
            Input(self._preset_select(), "value"),
        )
        params = self._param_input({"preset": ALL, "param": ALL})

        app.callback(
            Output(self._preset_select(), "data"),
            Output(self._preset_select(), "value"),
            Output(self._altaz_chip(), "disabled"),
            Output(self._ref_frame(), "value"),
            Input(self._instrument(), "data"),
            State(self._preset_select(), "value"),
            State(self._ref_frame(), "value"),
        )(self._apply_conditions)

        preset_select = self._preset_select()
        desired_sens_input = self._desired_sens()

        app.callback(
            Output(self.mapping(), "data"),
            Output(preset_select, "error"),
            Output(preset_select, "description"),
            Output(preset_select, "mod"),
            Output(desired_sens_input, "error"),
            Output(desired_sens_input, "description"),
            Output(desired_sens_input, "mod"),
            Input(preset_select, "value"),
            Input(params, "value"),
            Input(self._ref_frame(), "value"),
            Input(desired_sens_input, "value"),
            State(params, "id"),
        )(self._make_mapping)

    def _make_mapping(
        self,
        key: str,
        values: list,
        ref_frame: str,
        desired_sens: float | str | None,
        ids: list[dict[str, str]],
    ) -> tuple:
        sens_feedback = _desired_sens_feedback(desired_sens)
        preset = self._presets.get(key)
        selected = {
            i["param"]: v
            for i, v in zip(ids, values, strict=True)
            if i["preset"] == key
        }
        pattern = t_exp = None
        if any(v is None or v == "" for v in selected.values()):
            message = "Invalid mapping settings: enter every parameter."
        else:
            try:
                pattern, t_exp = preset.make_mapping(selected)
            except (ValueError, ValidationError) as error:
                message = f"Invalid mapping settings: {error}"
        if pattern is None:
            return None, *feedback(message, valid=False), *sens_feedback
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
            return None, *feedback(message, valid=False), *sens_feedback
        else:
            message = f"Time to finish the pattern: {t_pattern:.2f}."
        preset_feedback = feedback(message, valid=True)
        if desired_sens is None or sens_feedback[0] is not None:
            return None, *preset_feedback, *sens_feedback
        data = make_mapping_data(
            pattern, ref_frame, t_exp, float(desired_sens) << u.mJy
        )
        return data, *preset_feedback, *sens_feedback

    def _apply_conditions(
        self, instrument: dict[str, Any] | None, key: str, ref_frame: str
    ) -> tuple:
        # The instrument settings are published by a clientside callback;
        # until then there are no conditions to apply.
        if instrument is None:
            raise PreventUpdate
        conditions = {k: v for k, v in instrument.items() if isinstance(v, bool)}
        data, first_enabled = self._make_preset_options(conditions)
        if not _is_enabled(self._presets.get(key), conditions):
            key = first_enabled
        # Polarimetry maps in RA/Dec only.
        polarized = bool(conditions.get("polarized", False))
        if polarized:
            ref_frame = "icrs"
        return data, key, polarized, ref_frame
