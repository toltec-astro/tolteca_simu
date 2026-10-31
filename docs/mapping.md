# Mapping patterns and presets

A mapping pattern describes the telescope motion as offsets in time from a
reference point. Rendered around a target from a start time, it becomes the
trajectory of an observation. Presets name the patterns a planner offers, with
default values and permitted ranges.

| Need                                 | Use                                                                                                                                                                                                               |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Describe a pattern                   | {py:class}`~tolteca_simu.mapping.RasterPattern`, {py:class}`~tolteca_simu.mapping.LissajousPattern`, {py:class}`~tolteca_simu.mapping.DoubleLissajousPattern`, {py:class}`~tolteca_simu.mapping.RastajousPattern` |
| Evaluate offsets at times you choose | `offsets(t)`, `turnaround_mask(t)`                                                                                                                                                                                |
| Place a pattern on the sky           | {py:func}`~tolteca_simu.planning.get_trajectory`                                                                                                                                                                  |
| Offer patterns with ranges           | A presets file read by {py:class}`~tolteca_simu.planning.MappingPresets`                                                                                                                                          |

## Describe a pattern

Pattern parameters are quantities. Give them as quantities or as strings with
units; each is checked against its physical type.

```{testcode}
import astropy.units as u
import numpy as np
from tolteca_simu.mapping import LissajousPattern, RasterPattern

raster = RasterPattern(
    length="10 arcmin", space="1 arcmin", n_scans=5, rot="0 deg",
    speed="30 arcsec/s", t_turnaround="5 s",
)
lissajous = LissajousPattern(
    x_length="4 arcmin", y_length="4 arcmin", x_omega="9.2 rad/s",
    y_omega="8 rad/s", delta="45 deg", rot="0 deg",
)
print(f"{raster.t_pattern:.1f}, {lissajous.t_pattern:.1f}")
```

```{testoutput}
120.0 s, 38.9 s
```

`t_pattern` is the time to execute the pattern once. A raster-like pattern ends
there; a Lissajous-like pattern may repeat for a longer exposure. The class
attribute `pattern_kind` tells them apart.

Evaluate a pattern at any times; the result does not depend on how you sample
it. `turnaround_mask` marks the raster turnarounds, which are off scan:

```{testcode}
t = np.array([0, 10, 20, 22.5]) << u.s
dlon, dlat = raster.offsets(t)
print(dlon.to(u.arcmin))
print(dlat.to(u.arcmin))
print(raster.turnaround_mask(t))
```

```{testoutput}
[-5.   0.   5.   5.5] arcmin
[-2.  -2.  -2.  -1.5] arcmin
[False False  True  True]
```

## Place a pattern on the sky

{py:func}`~tolteca_simu.planning.get_trajectory` renders a pattern around a
target from a start time. With `ref_frame="altaz"` the offsets are in azimuth
and elevation; with `"icrs"` they are in right ascension and declination.

```{testcode}
from astropy.time import Time
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_trajectory, parse_target

target = parse_target("09h55m52.4s +69d40m47s")
trajectory = get_trajectory(
    raster,
    target,
    Time("2026-01-15 06:00:00"),
    t_exp=raster.t_pattern,
    ref_frame="altaz",
    observer=get_lmt_observer(),
)
alt = trajectory.coords_altaz.alt
print(trajectory.t.size, f"{alt.min():.2f}", f"{alt.max():.2f}")
```

```{testoutput}
1201 33.32 deg 33.52 deg
```

{py:func}`~tolteca_simu.planning.parse_target` also accepts a source name such
as `"M82"`, which it resolves through an online name service. The
{py:class}`~tolteca_simu.planning.Trajectory` holds the times, the offsets, the
boresight in the reference frame, ICRS and horizon coordinates, and the
turnaround flags.

## Use presets

The planner offers the presets in its presets file. Read the presets shipped
with the package, choose one, and make its pattern from parameter values:

```{testcode}
from tolteca_simu.planning import MappingPresets
from tolteca_simu.planning.presets import get_default_presets_path

presets = MappingPresets.from_yaml(get_default_presets_path())
preset = presets.get("toltec_blank_field_raster")
values = {name: param.value for name, param in preset.params.items()}
pattern, t_exp = preset.make_mapping(values)
print(type(pattern).__name__, f"{pattern.t_pattern:.0f}", t_exp)
```

```{testoutput}
RasterPattern 1764 s None
```

Values are in each parameter's unit. A value outside its range raises
`ValueError`:

```{testcode}
try:
    preset.make_mapping({**values, "speed": 8.0})
except ValueError as error:
    print(error)
```

```{testoutput}
speed=8.0 is outside [0.0, 5.0]
```

## Write a presets file

A presets file lists presets under `presets`, in the order the planner shows
them:

```{literalinclude} examples/my_presets.yaml
:language: yaml
```

| Key                               | Meaning                                                                                                                                                                                                                     |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `key`                             | Unique identifier.                                                                                                                                                                                                          |
| `label`                           | Name shown to observers.                                                                                                                                                                                                    |
| `conditions`                      | Instrument settings the preset requires. With `polarized: false`, the planner offers the preset for total intensity only.                                                                                                   |
| `description`, `description_long` | Short and long help text.                                                                                                                                                                                                   |
| `pattern`                         | `raster`, `lissajous`, `double_lissajous` or `rastajous`.                                                                                                                                                                   |
| `params`                          | Each pattern parameter with its `value` and `unit` (none for a count), the permitted range `min` and `max`, whether the observer may change it (`editable`), whether the planner shows it (`visible`), and a `description`. |

Two parameters are optional. `t_exp` is the exposure time; without it, the
pattern is observed once, and the planner rejects a pattern that takes longer
than its `t_exp_max` setting. `speed_lissajous` sets the average speed of a
Lissajous figure by scaling the pattern's frequencies; in a double Lissajous or
Rastajous pattern, it is the speed of the major figure.

Reading the file checks every preset, including that its default values make a
pattern:

```{testsetup} my_presets
import os

previous_cwd = Path.cwd()
os.chdir(docs_path / "examples")
```

```{testcode} my_presets
from pathlib import Path
from tolteca_simu.planning import MappingPresets

presets = MappingPresets.from_yaml(Path("my_presets.yaml"))
preset = presets.get("compact_lissajous")
pattern, t_exp = preset.make_mapping(
    {name: param.value for name, param in preset.params.items()}
)
print(type(pattern).__name__, t_exp)
```

```{testoutput} my_presets
LissajousPattern 5.0 min
```

```{testcleanup} my_presets
os.chdir(previous_cwd)
```

Point the planner at your file with
[`presets_path`](obs-planner.md#offer-your-own-presets).
