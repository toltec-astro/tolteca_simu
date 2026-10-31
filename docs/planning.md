# Plan an observation in Python

The planner's results are available from Python: describe an observation, check
its visibility, plan it, and write the files the planner offers for download.

| Step                                               | Use                                                                                                          |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Describe the observation                           | {py:class}`~tolteca_simu.planning.ObservationDescription`                                                    |
| Target elevation over the day                      | {py:func}`~tolteca_simu.planning.get_target_visibility`, {py:func}`~tolteca_simu.planning.get_target_uptime` |
| Trajectory, coverage and sensitivity, project time | {py:func}`~tolteca_simu.toltec.planning.plan_observation`                                                    |
| Files                                              | {py:func}`~tolteca_simu.toltec.exports.make_export_files`                                                    |

Coverage and sensitivity read the TolTEC calibration data store; the examples
below name its root `cal_data_path`.

## Describe the observation

An observation description holds everything the results depend on: the target
and start time, the mapping pattern and its reference frame, the exposure time,
the atmosphere quantile, the TolTEC settings, and the desired map depth. Make
the pattern from a [preset](mapping.md#use-presets):

```{testcode}
import astropy.units as u
from astropy.time import Time
from tolteca_simu.planning import MappingPresets, ObservationDescription, parse_target
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.settings import ToltecSettings

presets = MappingPresets.from_yaml(get_default_presets_path())
preset = presets.get("toltec_blank_field_lissajous")
pattern, t_exp = preset.make_mapping(
    {name: param.value for name, param in preset.params.items()}
)
description = ObservationDescription(
    target_name="09h55m52.4s +69d40m47s",
    target=parse_target("09h55m52.4s +69d40m47s"),
    t0=Time("2026-01-15 06:00:00"),
    mapping=pattern,
    ref_frame="altaz",
    t_exp=t_exp,
    atm_model_name="am_q25",
    instrument=ToltecSettings(polarized=False, array_name="a1100"),
    desired_sens=1 << u.mJy,
)
```

`atm_model_name` selects the 25 %, 50 % or 75 % quantile of the LMT atmosphere
conditions. `array_name` selects the TolTEC band whose map depth sets the number
of passes.

## Check visibility

```{testcode}
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_target_uptime, get_target_visibility

observer = get_lmt_observer()
uptime = get_target_uptime(
    description.target, Time("2026-01-15"), observer, alt_min=20 << u.deg
)
print(f"{uptime.uptime.to(u.h):.1f}, transit at {uptime.transit_time.iso[11:16]} UT")
visibility = get_target_visibility(description.target, description.t0, observer)
print(f"highest at {visibility.alt.max():.1f}")
```

```{testoutput}
10.0 h, transit at 08:48 UT
highest at 39.4 deg
```

`get_target_uptime` counts the night-time of the UT day starting at its date
argument with the target at or above `alt_min`, and returns None when there is
none. `get_target_visibility` gives the altitude over the UT day with the sunset
and sunrise times, for plotting.

## Plan the observation

{py:func}`~tolteca_simu.toltec.planning.plan_observation` computes what the
planner computes on Execute: the trajectory, the coverage and sensitivity, and
the project time. It needs a TolTEC planner, which
{py:meth}`~tolteca_simu.core.Simu.make_toltec_planner` builds from the same
`simu.obs_planner` settings as the planner; unset settings keep their production
defaults:

```{testcode}
:skipif: skip_without_cal_data

from tollan.config import RuntimeContext
from tolteca_simu.core import Simu
from tolteca_simu.toltec.planning import plan_observation

simu = Simu(RuntimeContext({"simu": {"obs_planner": {"cal_data_path": cal_data_path}}}))
planner = simu.make_toltec_planner()
plan = plan_observation(description, planner)
result = plan.result
print(f"{result.n_passes} pass of {result.t_exp}")
for name, summary in result.summaries.items():
    print(name, f"NEFD {summary.nefd:.3f}, depth {summary.depth_rms_coadd:.3f}")
print(f"{plan.time_cost.total_time:.2f} in {plan.time_cost.n_nights} night")
```

```{testoutput}
:skipif: skip_without_cal_data

1 pass of 10.0 min
a1100 NEFD 4.926 mJy / Hz(1/2), depth 0.510 mJy
a1400 NEFD 2.999 mJy / Hz(1/2), depth 0.310 mJy
a2000 NEFD 1.584 mJy / Hz(1/2), depth 0.164 mJy
0.27 h in 1 night
```

Pass `config_sources=Path("simu.yaml")` to `RuntimeContext` to use a
configuration file. The planner reads the calibration tables when it first needs
them and keeps them; reuse it for further observations.

The {py:class}`~tolteca_simu.toltec.planning.ObservationPlan` holds the
description, the {py:class}`~tolteca_simu.planning.Trajectory`, the
{py:class}`~tolteca_simu.toltec.planning.ToltecPlanningResult` (detector
footprint, field-of-view outline, coverage map, map depth and per-array
sensitivity) and the {py:class}`~tolteca_simu.toltec.time_cost.TimeCost`, which
adds pointing and other overheads to the science time.

`plan_observation` renders the trajectory with
{py:func}`~tolteca_simu.planning.get_trajectory`, plans it with
{py:meth}`~tolteca_simu.toltec.planning.ToltecPlanner.plan`, and estimates the
project time with {py:func}`~tolteca_simu.toltec.time_cost.get_time_cost`. Call
those directly to change one step, such as the trajectory's sampling.

## Write the files

{py:func}`~tolteca_simu.toltec.exports.make_export_files` returns the files the
planner offers for download, by kind, each as a file name and its content:

```{testsetup}
:skipif: skip_without_cal_data

import os
import tempfile

previous_cwd = Path.cwd()
output_dir = tempfile.TemporaryDirectory()
os.chdir(output_dir.name)
```

```{testcode}
:skipif: skip_without_cal_data

from datetime import UTC, datetime
from pathlib import Path
from tolteca_simu.toltec.exports import make_export_files

files = make_export_files(
    plan,
    apt_path=simu.config.obs_planner.toltec.apt,
    coverage_unit="depth",
    created_at=datetime.now(UTC),
)
for filename, content in files.values():
    if isinstance(content, bytes):
        Path(filename).write_bytes(content)
    else:
        Path(filename).write_text(content)
    print(filename)
```

```{testoutput}
:skipif: skip_without_cal_data

target_09h55m52.4s-+69d40m47s.lmtot
toltec_obs_planner_results.ecsv
obsplanner_toltec_a1100_cov.fits
```

```{testcleanup}
:skipif: skip_without_cal_data

os.chdir(previous_cwd)
output_dir.cleanup()
```

| Kind       | Contents                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| `lmtot`    | The observation as a script for the LMT observing tool.                                                               |
| `results`  | Sensitivity and project time per array, with the description in its metadata.                                         |
| `coverage` | Coverage images of the selected array: map depth in mJy/beam (`coverage_unit="depth"`) or time in s/pixel (`"time"`). |

A results file reproduces its observation:
{py:func}`~tolteca_simu.toltec.exports.read_results_metadata` returns the
description it records, which plans to the same results. To plan from the
command line, see
[Plan from the command line](obs-planner.md#plan-from-the-command-line).
