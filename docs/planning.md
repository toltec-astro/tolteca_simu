# Plan an observation in Python

The planner's results are available from Python: describe an observation, then
compute its visibility, trajectory, coverage and sensitivity, and project time,
and write the files the planner offers for download.

| Step                          | Use                                                                                                                                                                         |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Describe the observation      | {py:class}`~tolteca_simu.planning.ObservationDescription`                                                                                                                   |
| Target elevation over the day | {py:func}`~tolteca_simu.planning.get_target_visibility`, {py:func}`~tolteca_simu.planning.get_target_uptime`                                                                |
| Trajectory                    | {py:func}`~tolteca_simu.planning.get_trajectory`                                                                                                                            |
| Coverage and sensitivity      | {py:class}`~tolteca_simu.toltec.planning.ToltecPlanner`                                                                                                                     |
| Project time                  | {py:func}`~tolteca_simu.toltec.time_cost.get_time_cost`                                                                                                                     |
| Files                         | {py:func}`~tolteca_simu.lmtot.make_lmtot_script`, {py:func}`~tolteca_simu.toltec.exports.make_results_table`, {py:func}`~tolteca_simu.toltec.exports.make_coverage_hdulist` |

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

## Compute coverage and sensitivity

Render the trajectory, then plan it with the TolTEC planner. The planner reads
the calibration tables when it first needs them and keeps them for later
observations. The defaults of
{py:class}`~tolteca_simu.config.ToltecPlannerConfig` and
{py:class}`~tolteca_simu.config.LmtPlannerConfig` are the production settings:

```{testcode}
:skipif: skip_without_cal_data

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.config import LmtPlannerConfig, ToltecPlannerConfig
from tolteca_simu.planning import get_trajectory
from tolteca_simu.toltec.planning import ToltecPlanner

trajectory = get_trajectory(
    description.mapping,
    description.target,
    description.t0,
    t_exp=description.get_t_exp(),
    ref_frame=description.ref_frame,
    observer=observer,
)
toltec_config = ToltecPlannerConfig()
planner = ToltecPlanner(
    CalDataStore(cal_data_path),
    apt_path=toltec_config.apt,
    tel_surface_rms=LmtPlannerConfig().tel_surface_rms,
    det_noise_factors=toltec_config.det_noise_factors,
)
result = planner.plan(description, trajectory, observer)
print(f"{result.n_passes} pass of {result.t_exp}")
for name, summary in result.summaries.items():
    print(name, f"NEFD {summary.nefd:.3f}, depth {summary.depth_rms_coadd:.3f}")
```

```{testoutput}
:skipif: skip_without_cal_data

1 pass of 10.0 min
a1100 NEFD 4.926 mJy / Hz(1/2), depth 0.510 mJy
a1400 NEFD 2.999 mJy / Hz(1/2), depth 0.310 mJy
a2000 NEFD 1.584 mJy / Hz(1/2), depth 0.164 mJy
```

The result also holds the detector footprint on the sky, the field-of-view
outline, the coverage map and the map depth of the selected array. See
{py:class}`~tolteca_simu.toltec.planning.ToltecPlanningResult`.

## Estimate the project time

```{testcode}
:skipif: skip_without_cal_data

from tolteca_simu.toltec.time_cost import get_time_cost

time_cost = get_time_cost(result.n_passes, result.t_exp, result.t_exp_eff)
print(f"{time_cost.total_time:.2f} in {time_cost.n_nights} night")
```

```{testoutput}
:skipif: skip_without_cal_data

0.27 h in 1 night
```

The project time adds pointing and other overheads to the science time.

## Write the files

These are the files the planner offers for download:

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
from tolteca_simu.lmtot import make_lmtot_script
from tolteca_simu.toltec.exports import (
    make_coverage_hdulist,
    make_results_table,
    write_results_ecsv,
)

created_at = datetime.now(UTC)
Path("obs.lmtot").write_text(
    make_lmtot_script(description, author="Jane Observer", created_at=created_at)
)
table = make_results_table(
    description, result, time_cost, toltec_config.apt, created_at
)
Path("results.ecsv").write_text(write_results_ecsv(table))
make_coverage_hdulist(result, "mJy/beam").writeto("coverage.fits")
print(table["array_name"].tolist())
```

```{testoutput}
:skipif: skip_without_cal_data

['a1100', 'a1400', 'a2000']
```

```{testcleanup}
:skipif: skip_without_cal_data

os.chdir(previous_cwd)
output_dir.cleanup()
```

| File            | Contents                                                                      |
| --------------- | ----------------------------------------------------------------------------- |
| `obs.lmtot`     | The observation as a script for the LMT observing tool.                       |
| `results.ecsv`  | Sensitivity and project time per array, with the description in its metadata. |
| `coverage.fits` | Coverage images of the selected array, in `"mJy/beam"` or `"s/pixel"`.        |

A results file reproduces its observation:
{py:func}`~tolteca_simu.toltec.exports.read_results_metadata` returns the
description it records, which plans to the same results.
