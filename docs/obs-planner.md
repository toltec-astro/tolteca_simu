# Run the observation planner

The TolTEC observation planner is a web application in which observers describe
an observation and see its visibility, trajectory, coverage, sensitivity and
project time. It runs on Dash's development server for local use, or under
gunicorn behind a reverse proxy in production.

| Need                                                  | Do                                                                                 |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Run a planner on your computer                        | `tolteca_simu obs_planner run` with a [configuration file](#configure-the-planner) |
| Check the settings a planner would use                | `tolteca_simu obs_planner show_config`                                             |
| Serve the planner to observers                        | [`tolteca_simu obs_planner serve`](#serve-the-planner) behind a reverse proxy      |
| Draw the sky and coverage views with a Firefly server | Set [`viewer`](#choose-the-viewer)                                                 |
| Offer your own mapping presets                        | Set [`presets_path`](#offer-your-own-presets)                                      |
| Plan an observation in the page                       | [Use the planner](#use-the-planner)                                                |

## Configure the planner

The planner reads its settings from the `simu.obs_planner` section of YAML
configuration files. Only `cal_data_path`, the root of the TolTEC calibration
data store, is required; TolTEC deployments provide the store.

```{literalinclude} examples/simu.yaml
:language: yaml
```

```{testcode}
:hide:
:skipif: skip_without_cal_data

from tollan.utils.yaml import yaml_load
from tolteca_simu.config import SimuConfig

settings = yaml_load(docs_path / "examples" / "simu.yaml")
settings["simu"]["obs_planner"]["cal_data_path"] = str(cal_data_path)
config = SimuConfig.model_validate(settings["simu"]).obs_planner
print(config.subtitle, config.target_alt_min, config.server.port, config.viewer.kind)
```

```{testoutput}
:hide:
:skipif: skip_without_cal_data

Large Program 2026 30.0 deg 8054 aladin_lite
```

Unset settings keep their defaults, which match the production planner: the
packaged presets, the LMT surface RMS, the TolTEC array property table, and the
detector noise factors. See {py:class}`~tolteca_simu.config.ObsPlannerConfig`
for every setting.

Pass one or more files with `--config_paths`; later files take precedence.
Dotted options override single settings. Print the resolved settings to check
them:

```console
tolteca_simu obs_planner show_config --config_paths simu.yaml
tolteca_simu obs_planner show_config --config_paths simu.yaml --simu.obs_planner.subtitle "test"
```

## Run the planner locally

```console
tolteca_simu obs_planner run --config_paths simu.yaml
```

Open <http://127.0.0.1:8054> in a browser. `--host`, `--port` and `--debug`
override `server.host`, `server.port` and `server.debug`; `--debug` enables
Dash's development tools.

## Serve the planner

```console
tolteca_simu obs_planner serve --config_paths simu.yaml
```

`serve` runs the planner under gunicorn with `server.workers` worker processes
and a `server.timeout` in seconds. Behind a reverse proxy that forwards a path
such as `/toltec_obs_planner/` unchanged, set `server.url_base_pathname` to that
path.

In a TolTECA deployment location, the `tolteca_simu` run profile provides the
same commands with the location's configuration:

```console
just run tolteca_simu obs_planner
just run tolteca_simu obs_planner_serve
just run tolteca_simu show_config
```

## Choose the viewer

The sky view and the coverage view are drawn by Aladin Lite in the page by
default; nothing else needs to run. To draw them with a Firefly server instead,
give its base URL as browsers reach it:

```yaml
simu:
  obs_planner:
    viewer:
      kind: firefly
      url: /firefly/
```

A deployment location's `just run tolteca_simu firefly` starts a Firefly server.

## Offer your own presets

The mapping presets offered in the page come from `presets_path`, by default the
presets shipped with the package. To offer your own, write a presets file as
described in [Mapping patterns and presets](mapping.md#write-a-presets-file) and
name it:

```yaml
simu:
  obs_planner:
    presets_path: /path/to/my_presets.yaml
```

## Use the planner

The left column holds the observation; the right column shows the results.

1. In the **Plan** tab, enter the **Target** as a coordinate or a name, the
   **Obs Date** and the **Obs Start Time (UT)**. The check below each field
   shows the resolved coordinate, the target's up-time, and its position at the
   start.
2. Under **Site**, choose the **Atm. Quantile** of the conditions.
3. Under **Instrument: TolTEC**, choose the **Stokes Params**, the **TolTEC
   band** whose depth sets the number of passes, and the **Coverage Unit** of
   the coverage map.
4. Under **Mapping**, choose a preset, enter the **Desired Map RMS**, adjust the
   pattern parameters within their ranges, and choose the **Mapping Reference
   Frame**.
5. Press **Execute**.

The sky view then shows the trajectory, the detectors, the field of view and the
coverage outline over the sky survey. The trajectory plots, the coverage view
and the **TolTEC sensitivity** tables follow below.

Download the results with the buttons above the trajectory plots:

| Download                    | Contents                                                                  |
| --------------------------- | ------------------------------------------------------------------------- |
| LMT OT script               | The observation as a script for the LMT observing tool.                   |
| Coverage map (FITS)         | The coverage of the chosen band, in the chosen coverage unit.             |
| Results for proposal (ECSV) | Sensitivity and project time per array, with the observation description. |

To reproduce earlier results, open the **Verify** tab, upload a results ECSV
file under **Upload result to verify**, and press **Execute**.
