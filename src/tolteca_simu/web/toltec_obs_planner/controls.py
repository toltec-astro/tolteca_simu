"""Form controls of the planner: Mantine components with v1's cues.

As in v1, a card has a title band; an input shows its name before the value
and its unit after it, as segments attached to the input; a checked input
shows a green border, a check mark and a green message when valid, and a red
border, an alert mark and a red message when invalid; a choice of one option
fills the chosen option. ``assets/planner.css`` styles the segments and the
valid and invalid marks for the classes and modifiers set here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dash.development.base_component import Component
    from dash_component_template import LazyComponent, Template

__all__ = [
    "CONTROL_SIZE",
    "feedback",
    "field",
    "field_props",
    "hover_card",
    "labeled_choice",
    "section_width",
    "titled_card",
    "tooltip",
    "with_tooltip",
]

CONTROL_SIZE = "sm"
"""Size of the planner's inputs and buttons: 14px text, as v1's small form
controls."""

# Width of a character and the padding of a name or unit at CONTROL_SIZE.
_CHAR_WIDTH = 7.4
_SECTION_PADDING = 22
# Class of the name and unit segments (assets/planner.css).
_ADDON_CLASS = "planner-addon"


def section_width(labels: Iterable[str]) -> int:
    """Return the width, in pixels, that fits each label.

    An input's name or unit fits its own label. The labels of the choices of
    one card share one width, so that their options line up.

    Parameters
    ----------
    labels : iterable of str
        The labels.

    Returns
    -------
    int
        Width in pixels.
    """
    return int(_SECTION_PADDING + _CHAR_WIDTH * max(len(text) for text in labels))


def titled_card(
    parent: Template | LazyComponent, title: str
) -> tuple[LazyComponent, LazyComponent]:
    """Add a bordered card with a title band, as v1's card header.

    Parameters
    ----------
    parent : dash_component_template.Template or dash_component_template.LazyComponent
        Where to add the card.
    title : str
        Title shown in the band.

    Returns
    -------
    header : dash_component_template.LazyComponent
        A `dash_mantine_components.Group` in the title band, holding the
        title.
    body : dash_component_template.LazyComponent
        A `dash_mantine_components.Stack` below the title, for the content.
    """
    card = parent.child[dmc.Card](withBorder=True, padding="sm")
    section = card.child[dmc.CardSection](
        withBorder=True,
        inheritPadding=True,
        py="xs",
        bg="var(--mantine-color-default-hover)",
    )
    header = section.child[dmc.Group](gap="xs")
    header.child[dmc.Text](title, fw=500)
    body = card.child[dmc.Stack](gap="xs", pt="sm")
    return header, body


def _section(text: str) -> dmc.Text:
    return dmc.Text(text, size=CONTROL_SIZE)


def field_props(
    label: str | None = None, *, unit: str | None = None, checked: bool = False
) -> dict[str, Any]:
    """Return the properties of an input with a name, a unit and feedback.

    Parameters
    ----------
    label : str, optional
        Name shown before the value.
    unit : str, optional
        Unit shown after the value.
    checked : bool
        Whether the input shows feedback from a check below it: its callback
        sets ``error``, ``description`` and ``mod`` from `feedback`.

    Returns
    -------
    dict
        Properties for a Mantine input, such as
        `dash_mantine_components.NumberInput`.
    """
    props: dict[str, Any] = {"size": CONTROL_SIZE}
    if label is not None:
        props["leftSection"] = _section(label)
        props["leftSectionWidth"] = section_width([label])
    if unit is not None:
        props["rightSection"] = _section(unit)
        props["rightSectionWidth"] = section_width([unit])
    if label is not None or unit is not None:
        props["classNames"] = {"section": _ADDON_CLASS}
    if checked:
        props["inputWrapperOrder"] = ["label", "input", "description", "error"]
    return props


def field(
    parent: LazyComponent,
    component: type,
    label: str | None = None,
    *,
    unit: str | None = None,
    checked: bool = False,
    **kwargs: object,
) -> LazyComponent:
    """Add an input with its name before the value and its unit after it.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the input.
    component : type
        The Mantine input class, such as `dash_mantine_components.TextInput`.
    label : str, optional
        Name shown before the value.
    unit : str, optional
        Unit shown after the value.
    checked : bool
        Whether the input shows feedback from a check below it, as for
        `field_props`.
    **kwargs
        Other properties of the input.

    Returns
    -------
    dash_component_template.LazyComponent
        The input.
    """
    props = field_props(label, unit=unit, checked=checked)
    return parent.child[component](**(props | kwargs))


def feedback(message: str | None, *, valid: bool) -> tuple[Any, Any, dict]:
    """Return the ``error``, ``description`` and ``mod`` of a checked input.

    Parameters
    ----------
    message : str or None
        Feedback shown below the input.
    valid : bool
        Whether the value is valid.

    Returns
    -------
    tuple
        Values for the input's ``error``, ``description`` and ``mod``. A valid
        input is marked ``data-valid``, which shows its check mark and green
        border and message; an invalid one has Mantine's error state, also
        without a message.
    """
    if valid:
        return None, message or None, {"valid": True}
    return message or True, None, {}


def labeled_choice(  # noqa: PLR0913
    parent: LazyComponent,
    label: str,
    options: list[dict[str, Any]],
    value: str,
    *,
    label_width: int | None = None,
    below: bool = False,
) -> LazyComponent:
    """Add a choice of one option, with its label before it.

    As v1, the chosen option is filled and a click changes it at once.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the choice.
    label : str
        Name shown before the options.
    options : list of dict
        The ``label`` and ``value`` of each option, and ``disabled`` for an
        option that cannot be chosen.
    value : str
        The value chosen at first.
    label_width : int, optional
        Width of the name, from `section_width`, as for the other choices of
        the same card.
    below : bool
        Whether the options go on their own line under the label, filling it,
        for options too long to follow the label, as v1 wraps them.

    Returns
    -------
    dash_component_template.LazyComponent
        The `dash_mantine_components.SegmentedControl`, whose ``value`` is
        the choice and whose ``data`` holds the options.
    """
    row = (
        parent.child[dmc.Stack](gap=4)
        if below
        else parent.child[dmc.Group](gap="xs", wrap="nowrap")
    )
    row.child[dmc.Text](
        f"{label}:",
        size=CONTROL_SIZE,
        w=None if below else label_width,
        flex="none",
    )
    return row.child[dmc.SegmentedControl](
        data=options,
        value=value,
        size=CONTROL_SIZE,
        color="blue",
        transitionDuration=0,
        fullWidth=below,
    )


def hover_card(parent: LazyComponent) -> tuple[LazyComponent, LazyComponent]:
    """Add a card of notes shown while the pointer is over its target.

    As v1's popovers, the card opens to the right of its target, or above it
    when there is no room, so that it does not cover a dropdown below.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the card.

    Returns
    -------
    target : dash_component_template.LazyComponent
        The full-width target, to add one component to.
    notes : dash_component_template.LazyComponent
        A `dash_mantine_components.Stack` in the card, for the notes.
    """
    card = parent.child[dmc.HoverCard](
        width=360,
        shadow="md",
        withArrow=True,
        position="right-start",
        middlewares={"flip": {"fallbackPlacements": ["top-start"]}, "shift": True},
    )
    target = card.child[dmc.HoverCardTarget](boxWrapperProps={"w": "100%"})
    notes = card.child[dmc.HoverCardDropdown]().child[dmc.Stack](gap="xs")
    return target, notes


def _tooltip_props(text: str) -> dict[str, Any]:
    return {
        "label": " ".join(text.split()),
        "multiline": True,
        "w": 320,
        "withArrow": True,
        "position": "top-start",
        "boxWrapperProps": {"w": "100%"},
    }


def with_tooltip(parent: LazyComponent, text: str) -> LazyComponent:
    """Add a tooltip that explains the component added to it.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the tooltip.
    text : str
        The explanation.

    Returns
    -------
    dash_component_template.LazyComponent
        The tooltip, to add one component to.
    """
    return parent.child[dmc.Tooltip](**_tooltip_props(text))


def tooltip(component: Component, text: str) -> dmc.Tooltip:
    """Return a component with a tooltip that explains it.

    Parameters
    ----------
    component : dash.development.base_component.Component
        The component, made in a callback.
    text : str
        The explanation.

    Returns
    -------
    dash_mantine_components.Tooltip
        The tooltip around the component.
    """
    return dmc.Tooltip(component, **_tooltip_props(text))
