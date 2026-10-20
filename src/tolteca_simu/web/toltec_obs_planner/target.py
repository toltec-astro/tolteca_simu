"""Target and start time of the observation description."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
from astropy.coordinates import SkyCoord
from astropy.time import Time
from dash import Input, Output, State, dcc
from dash_component_template import Template
from pydantic import ValidationError

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_target_uptime, parse_target

from .controls import feedback, field, section_width, with_tooltip

if TYPE_CHECKING:
    from astroplan import Observer
    from dash import Dash

__all__ = ["TargetPanel", "check_date", "check_start_time"]

_DATE_LABEL = "Obs Date"
_TIME_LABEL = "Obs Start Time (UT)"
# The formats of the date and start time inputs, as in v1.
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_PATTERN = re.compile(r"\d{2}:\d{2}:\d{2}")


def _parse_start(date: str | None, time: str | None = "00:00:00") -> Time | None:
    # The UT start time, or None unless both inputs have their format.
    if not date or not time:
        return None
    if not (_DATE_PATTERN.fullmatch(date) and _TIME_PATTERN.fullmatch(time)):
        return None
    try:
        return Time(f"{date} {time}", scale="utc")
    except ValueError:
        return None


def check_date(
    target: SkyCoord, date: Time, observer: Observer, alt_min: u.Quantity
) -> tuple[str, bool]:
    """Report whether a target is observable on a UT day.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target.
    date : astropy.time.Time
        Start of the UT day.
    observer : astroplan.Observer
        The observing site.
    alt_min : astropy.units.Quantity
        Lowest usable elevation.

    Returns
    -------
    message : str
        The up-time and transit, or why the date does not work.
    valid : bool
        Whether the target is observable that day.
    """
    uptime = get_target_uptime(target, date, observer, alt_min)
    if uptime is None:
        return "Target is not up at night. Pick another date.", False
    transit = uptime.transit_time.datetime.strftime("UT %H:%M:%S")
    return f"Total up-time: {uptime.uptime:.1f}. Highest at {transit}.", True


def check_start_time(
    target: SkyCoord, t0: Time, observer: Observer, alt_min: u.Quantity
) -> tuple[str, bool]:
    """Report the target position at the start time.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target.
    t0 : astropy.time.Time
        The start time.
    observer : astroplan.Observer
        The observing site.
    alt_min : astropy.units.Quantity
        Lowest usable elevation.

    Returns
    -------
    message : str
        The target azimuth and altitude, or why the time does not work.
    valid : bool
        Whether the start time is at night with the target high enough.
    """
    if not observer.is_night(t0):
        sunrise = observer.sun_rise_time(t0, which="previous").iso
        sunset = observer.sun_set_time(t0, which="next").iso
        return (
            f"The time entered is not at night. Sunrise: {sunrise}. Sunset: {sunset}",
            False,
        )
    altaz = target.transform_to(observer.altaz(time=t0))
    position = f"Az = {altaz.az.degree:.4f}d Alt = {altaz.alt.degree:.4f}d"
    if altaz.alt < alt_min:
        message = (
            f"Target at {position} is too low (< {alt_min}) to observe. "
            "Pick another time."
        )
        return message, False
    return f"Target {position}.", True


class TargetPanel(Template):
    """Inputs for the target and the observation start time, with their checks.

    The panel publishes the resolved target in its `resolved` store (``name``,
    ``ra_deg`` and ``dec_deg``, or None), and the target part of the
    observation description, serialized as JSON, in its `target` store:
    ``target_name``, ``target`` and ``t0``. The `target` store holds None while
    an input is invalid. The date and time checks inform; they do not make the
    description invalid.

    Parameters
    ----------
    target_alt_min : astropy.units.Quantity
        Lowest usable elevation, for the date and time checks.
    """

    def __init__(self, target_alt_min: u.Quantity) -> None:
        super().__init__()
        self._target_alt_min = target_alt_min
        card = self.child[dmc.Card](withBorder=True, padding="sm")
        stack = card.child[dmc.Stack](gap="xs")
        stack.child[dmc.Title]("Target", order=5)
        width = section_width([_DATE_LABEL, _TIME_LABEL])
        self._target_input = field(
            with_tooltip(
                stack,
                "Enter source name or coordinates. Names are sent to a name "
                "lookup server for resolving the coordinates. Coordinates "
                'should be like "17.7d -2.1d" or "10h09m08s +20d19m18s".',
            ),
            dmc.TextInput,
            checked=True,
            placeholder="M1, NGC 1277, 17.7d -2.1d, 10h09m08s +20d19m18s",
            value="M1",
            debounce=True,
        )
        self._date_input = field(
            with_tooltip(
                stack,
                "The date of observation. The visibility report is done by "
                f"checking if the target elevation is > {target_alt_min} during "
                "the night time.",
            ),
            dmc.TextInput,
            _DATE_LABEL,
            label_width=width,
            checked=True,
            placeholder="yyyy-mm-dd",
            value=None,
            debounce=True,
        )
        self._time_input = field(
            with_tooltip(
                stack,
                "The time of observation. The target has to be at elevation > "
                f"{target_alt_min} during the night.",
            ),
            dmc.TextInput,
            _TIME_LABEL,
            label_width=width,
            checked=True,
            placeholder="HH:MM:SS",
            value="06:00:00",
            debounce=True,
        )
        # Where the page adds the altitude plot and the site information.
        self.footer = stack.child[dmc.Stack](gap="xs")
        self.resolved = stack.child[dcc.Store](data=None)
        self.target = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Resolve and check the target, and publish it with the start time.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            """
            function(_id, value) {
                return value || new Date().toISOString().slice(0, 10);
            }
            """,
            Output(self._date_input(), "value"),
            Input(self._date_input(), "id"),
            State(self._date_input(), "value"),
        )
        target_input = self._target_input()
        date_input = self._date_input()
        time_input = self._time_input()
        app.callback(
            Output(self.resolved(), "data"),
            Output(target_input, "error"),
            Output(target_input, "description"),
            Output(target_input, "mod"),
            Input(target_input, "value"),
        )(self._resolve_target)
        app.callback(
            Output(date_input, "error"),
            Output(date_input, "description"),
            Output(date_input, "mod"),
            Input(date_input, "value"),
            Input(self.resolved(), "data"),
        )(self._check_date)
        app.callback(
            Output(time_input, "error"),
            Output(time_input, "description"),
            Output(time_input, "mod"),
            Input(time_input, "value"),
            Input(date_input, "value"),
            Input(self.resolved(), "data"),
        )(self._check_time)
        app.callback(
            Output(self.target(), "data"),
            Input(self.resolved(), "data"),
            Input(date_input, "value"),
            Input(time_input, "value"),
        )(self._make_target)

    @staticmethod
    def _resolve_target(text: str | None) -> tuple:
        if not text:
            return None, *feedback(
                "Enter the name or coordinate of target.", valid=False
            )
        try:
            coord = parse_target(text)
        except ValidationError as error:
            message = f"Unable to resolve target: {error.errors()[0]['msg']}"
            return None, *feedback(message, valid=False)
        ra, dec = coord.ra.degree, coord.dec.degree
        resolved = {"name": text, "ra_deg": ra, "dec_deg": dec}
        message = f"Target coordinate resolved: {ra}d {dec}d (J2000)."
        return resolved, *feedback(message, valid=True)

    def _check_date(self, date: str | None, resolved: dict | None) -> tuple:
        if resolved is None:
            return feedback(None, valid=False)
        day = _parse_start(date)
        if day is None:
            return feedback("Invalid Date. Use yyyy-mm-dd.", valid=False)
        message, valid = check_date(
            _coord(resolved), day, get_lmt_observer(), self._target_alt_min
        )
        return feedback(message, valid=valid)

    def _check_time(
        self, time: str | None, date: str | None, resolved: dict | None
    ) -> tuple:
        if resolved is None or _parse_start(date) is None:
            return feedback(None, valid=False)
        t0 = _parse_start(date, time)
        if t0 is None:
            return feedback("Invalid time. Use HH:MM:SS.", valid=False)
        message, valid = check_start_time(
            _coord(resolved), t0, get_lmt_observer(), self._target_alt_min
        )
        return feedback(message, valid=valid)

    @staticmethod
    def _make_target(
        resolved: dict | None, date: str | None, time: str | None
    ) -> dict[str, str] | None:
        t0 = _parse_start(date, time)
        if resolved is None or t0 is None:
            return None
        return {
            "target_name": resolved["name"],
            "target": f"{resolved['ra_deg']:.17g}d {resolved['dec_deg']:.17g}d",
            "t0": t0.isot,
        }


def _coord(resolved: dict) -> SkyCoord:
    return SkyCoord(resolved["ra_deg"] << u.deg, resolved["dec_deg"] << u.deg)
