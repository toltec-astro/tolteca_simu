"""Form controls with the v1 planner's visual cues, built from Mantine inputs.

As in v1, an input shows its name as a grey prefix and its unit as a grey
suffix, with the value in the middle. A checked input shows its feedback below
it: green, with a green border and a check mark, when valid; Mantine's error
style when invalid. Choices are groups of pills with a grey label. The styles are
in ``assets/planner.css``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dash_component_template import LazyComponent

__all__ = [
    "INPUT_SIZE",
    "feedback",
    "field",
    "hover_card",
    "labeled_choice",
    "section_width",
    "with_tooltip",
]

INPUT_SIZE = "xs"
"""Size of the planner's inputs: compact, as v1's small form controls."""

# Width of a character and the padding of a section label at INPUT_SIZE.
_CHAR_WIDTH = 6.5
_SECTION_PADDING = 24


def section_width(labels: Iterable[str]) -> int:
    """Return the section width, in pixels, that fits the longest label.

    Inputs of one card share it, so that their values line up.

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


def _section(text: str) -> dmc.Text:
    return dmc.Text(text, size=INPUT_SIZE, c="dimmed", style={"whiteSpace": "nowrap"})


def field(  # noqa: PLR0913
    parent: LazyComponent,
    component: type,
    label: str | None = None,
    *,
    label_width: int | None = None,
    unit: str | None = None,
    checked: bool = False,
    **kwargs: object,
) -> LazyComponent:
    """Add an input with a prefix name and a suffix unit.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the input.
    component : type
        The Mantine input class, such as `dash_mantine_components.TextInput`.
    label : str, optional
        Name shown in grey before the value.
    label_width : int, optional
        Width of the name, from `section_width`; defaults to fit ``label``.
    unit : str, optional
        Unit shown in grey after the value.
    checked : bool
        Whether the input shows feedback from a check: its callback sets
        ``error``, ``description`` and ``mod`` from `feedback`. A checked
        input without a unit shows the check mark of a valid value.
    **kwargs
        Other properties of the input.

    Returns
    -------
    dash_component_template.LazyComponent
        The input.
    """
    props: dict[str, Any] = {"size": INPUT_SIZE}
    if label is not None:
        props["leftSection"] = _section(label)
        props["leftSectionWidth"] = label_width or section_width([label])
        # Names of one card line up on the left, as v1's prefixes.
        props["leftSectionProps"] = {
            "style": {"justifyContent": "flex-start", "paddingInlineStart": 8}
        }
    if unit is not None:
        props["rightSection"] = _section(unit)
        props["rightSectionWidth"] = section_width([unit])
    if checked:
        props["className"] = "toltec-field"
        props["inputWrapperOrder"] = ["label", "input", "description", "error"]
        props["classNames"] = {"description": "toltec-feedback"}
        if unit is None:
            props["rightSection"] = dmc.Text(
                "✓", size=INPUT_SIZE, fw=700, className="toltec-check"
            )
    return parent.child[component](**(props | kwargs))


def feedback(message: str | None, *, valid: bool) -> tuple[Any, str | None, dict]:
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
        Values for the input's ``error``, ``description`` and ``mod``.
    """
    if valid:
        return None, message or None, {"valid": True}
    # An empty message still marks the input invalid.
    return message or True, None, {}


def labeled_choice(
    parent: LazyComponent,
    label: str,
    options: list[dict[str, str]],
    value: str,
    *,
    label_width: int | None = None,
) -> tuple[LazyComponent, dict[str, LazyComponent]]:
    """Add a group of pills, one of which is chosen, with a grey label before it.

    The pills wrap onto more lines when the row is too narrow.

    Parameters
    ----------
    parent : dash_component_template.LazyComponent
        Where to add the group.
    label : str
        Name shown in grey before the choices.
    options : list of dict
        The ``label`` and ``value`` of each choice.
    value : str
        The value chosen at first.
    label_width : int, optional
        Width of the name, as for the inputs of the same card.

    Returns
    -------
    group : dash_component_template.LazyComponent
        The `dash_mantine_components.ChipGroup`, whose ``value`` is the choice.
    chips : dict
        The `dash_mantine_components.Chip` of each value.
    """
    row = parent.child[dmc.Group](gap="xs", wrap="nowrap", align="flex-start")
    row.child[dmc.Text](
        label,
        size=INPUT_SIZE,
        c="dimmed",
        w=label_width,
        pl=8,
        pt=4,
        style={"flexShrink": 0},
    )
    group = row.child[dmc.ChipGroup](value=value, multiple=False, deselectable=False)
    pills = group.child[dmc.Group](gap=4, flex=1)
    chips = {
        option["value"]: pills.child[dmc.Chip](
            option["label"], value=option["value"], size=INPUT_SIZE
        )
        for option in options
    }
    return group, chips


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
    return parent.child[dmc.Tooltip](
        label=" ".join(text.split()),
        multiline=True,
        w=320,
        withArrow=True,
        position="top-start",
        openDelay=300,
        boxWrapperProps={"w": "100%"},
    )
