"""TolTEC sensitivity view."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
from dash_component_template import Template
from dash_iconify import DashIconify

from .controls import CONTROL_SIZE
from .instrument import band_label

if TYPE_CHECKING:
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

__all__ = ["ToltecResultsPanel", "make_sensitivity_tabs"]

_TOTAL_TIME_LABEL = "Project Total Time (incl. Overhead)"


def _fmt(value: object) -> str:
    if isinstance(value, u.Quantity):
        return f"{value.value:.3g} {value.unit:unicode}"
    return str(value)


def _row(label: str, help_text: str, value: object, *, highlight: bool) -> dmc.TableTr:
    # As v1: the row label, then a help icon explaining the quantity on hover.
    return dmc.TableTr(
        [
            dmc.TableTd(
                dmc.Group(
                    [
                        label,
                        dmc.Tooltip(
                            DashIconify(
                                icon="tabler:help-circle",
                                width=15,
                                color="var(--mantine-color-dimmed)",
                            ),
                            label=help_text,
                            multiline=True,
                            w=300,
                            withArrow=True,
                        ),
                    ],
                    gap=6,
                    wrap="nowrap",
                )
            ),
            dmc.TableTd(_fmt(value)),
        ],
        # As v1: the project total time, which proposals refer to.
        **({"bg": "cyan.4"} if highlight else {}),
    )


def make_sensitivity_tabs(
    result: ToltecPlanningResult, time_cost: TimeCost
) -> dmc.Tabs:
    """Tabulate the sensitivity of each array and the project time.

    Parameters
    ----------
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    time_cost : tolteca_simu.toltec.time_cost.TimeCost
        The project time.

    Returns
    -------
    dash_mantine_components.Tabs
        One table per array, the computed array selected, with v1's rows.
        Each row label has a help icon that explains the quantity on hover;
        the project total time, which proposals refer to, is highlighted.
    """
    emission = "Polarized Emission" if result.polarized else "Total Intensity"
    stokes = "Polarized (Q/U)" if result.polarized else "Total Intensity (I)"
    per_night = time_cost.science_time_per_night
    panels = []
    for name, s in result.summaries.items():
        # The labels and help texts of v1 (toltec.py, _make_sens_tab_content).
        rows = [
            (
                "Array Name",
                "The TolTEC array name, e.g., a1100 for the 1.1mm array.",
                name,
            ),
            (
                "Mean Alt.",
                "The mean altitude of the mapping pattern.",
                s.alt_mean.to(u.deg),
            ),
            (
                "# of Detectors (Enabled / Total)",
                (
                    "Number of detectors configured for science data vs total. "
                    "These numbers are likely to change following fall "
                    "commissioning."
                ),
                (
                    f"{s.n_dets} / {s.n_dets_designed} "
                    f"({s.n_dets / s.n_dets_designed:.0%})"
                ),
            ),
            (
                f"Detector Sens. ({emission})",
                f"Estimated detector sensitivity for {emission.lower()}.",
                s.detector_sensitivity,
            ),
            (
                f"Mapping Speed ({emission})",
                f"Estimated mapping speed for {emission.lower()}.",
                f"{s.mapping_speed.value:.1f} {s.mapping_speed.unit:s}",
            ),
            (
                "Map Area",
                "Effective area of the mapping pattern.",
                result.depth.map_area,
            ),
            (
                "Exp. Time per Pass",
                "The time needed to complete one pass of the mapping pattern.",
                result.t_exp,
            ),
            (
                "Effective On-target Time per Pass",
                (
                    'The effective time on target. This equals to "Exp. Time" '
                    "except for raster maps where the turnaround time is "
                    "excluded."
                ),
                result.t_exp_eff,
            ),
            (
                "Stokes Params of Depth Values",
                (
                    "Indicated whether the depth values reported in this table "
                    "are for total intensity or polarimetry."
                ),
                stokes,
            ),
            (
                "Median RMS Sens. per Pass",
                "Estimated median of the RMS sensitivity for a single pass",
                s.depth_rms,
            ),
            (
                "Number of Passes",
                (
                    "The number of passes to execute the mapping pattern for to "
                    "reach the desired coadded map RMS."
                ),
                result.n_passes,
            ),
            (
                "Coadded Map RMS Sens.",
                (
                    "The estimated map RMS sensitivity after coadding "
                    '"Number of Passes" individual exposures.'
                ),
                s.depth_rms_coadd,
            ),
            (
                "Project Total Science Time",
                "The total time to finish all the observations",
                time_cost.science_time,
            ),
            (
                "Science Time Overhead",
                (
                    "The time that is considered overhead within the "
                    '"Project Science Time".'
                ),
                time_cost.science_overhead,
            ),
            (
                "Assumed Number of Obs. Nights",
                (
                    "Number of nights the project needs to finish, assuming "
                    f"{per_night.value:g}{per_night.unit} of up-time per night."
                ),
                time_cost.n_nights,
            ),
            (
                _TOTAL_TIME_LABEL,
                (
                    "The time to finish the project, including all overheads. "
                    "Refer to this number for proposal submission."
                ),
                time_cost.total_time,
            ),
            (
                "Project Overhead",
                (
                    "The time that is considered overhead within the "
                    '"Project Total Time".'
                ),
                time_cost.overhead_time,
            ),
            (
                "Project Overhead %",
                "The project overhead percentage.",
                f"{time_cost.overhead_fraction:.1%}",
            ),
        ]
        panels.append(
            dmc.TabsPanel(
                dmc.Table(
                    dmc.TableTbody(
                        [
                            _row(*row, highlight=row[0] == _TOTAL_TIME_LABEL)
                            for row in rows
                        ]
                    ),
                    striped=True,
                    highlightOnHover=True,
                    withTableBorder=True,
                    withColumnBorders=True,
                    fz=CONTROL_SIZE,
                ),
                value=name,
            )
        )
    return dmc.Tabs(
        [
            dmc.TabsList(
                [dmc.TabsTab(band_label(name), value=name) for name in result.summaries]
            ),
            *panels,
        ],
        value=result.array_name,
    )


class ToltecResultsPanel(Template):
    """Sensitivity tables, empty until the planner page fills `sensitivity`."""

    def __init__(self) -> None:
        super().__init__()
        self.sensitivity = self.child[dmc.Box]()
