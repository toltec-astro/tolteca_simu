"""Downloads of planning results, and reloading a saved result."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_component_template import Template

__all__ = ["ExportsPanel"]


class ExportsPanel(Template):
    """Download buttons and a results upload; wired by the planner page."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Exports", order=5)
        group = stack.child[dmc.Group](gap="xs")
        self.lmtot_button = group.child[dmc.Button](
            "LMT OT script", size="xs", variant="light"
        )
        self.results_button = group.child[dmc.Button](
            "Results for proposal (ECSV)", size="xs", color="green"
        )
        self.coverage_button = group.child[dmc.Button](
            "Coverage map (FITS)", size="xs", variant="light"
        )
        self.lmtot_download = stack.child[dcc.Download]()
        self.results_download = stack.child[dcc.Download]()
        self.coverage_download = stack.child[dcc.Download]()
        self.upload = stack.child[dcc.Upload](
            html.Div("Drop a results ECSV file here, or click to select one."),
            max_size=1_000_000,
            style={
                "border": "1px dashed var(--mantine-color-gray-5)",
                "borderRadius": "4px",
                "padding": "12px",
                "textAlign": "center",
                "fontSize": "12px",
            },
        )
        self.status = stack.child[dmc.Text](size="xs", c="dimmed")
