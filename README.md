# tolteca_simu

[![GitHub Discussion][github-discussions-badge]][github-discussions-link]

<!-- SPHINX-START -->

`tolteca_simu` plans TolTEC observations at the LMT: target visibility, the
telescope trajectory, sky coverage, sensitivity and project time. Use it from
Python, from the `tolteca_simu` command line, or through the TolTEC observation
planner web application.

## Installation

`tolteca_simu` needs Python 3.13 or later. Install it from GitHub:

```console
pip install "tolteca_simu @ git+https://github.com/toltec-astro/tolteca_simu.git"
```

The `toast` extra adds the TOAST atmosphere backend, which the planner does not
need. TOAST provides wheels for macOS arm64 and Linux x86_64:

```console
pip install "tolteca_simu[toast] @ git+https://github.com/toltec-astro/tolteca_simu.git"
```

## Quick start

The planner reads detector, passband and atmosphere tables from a TolTEC
calibration data store, which TolTEC deployments provide. Name its root in a
configuration file, `simu.yaml`:

```yaml
simu:
  obs_planner:
    cal_data_path: /path/to/tolteca_cal_data
```

Start the planner, then open <http://127.0.0.1:8054> in a browser:

```console
tolteca_simu obs_planner run --config_paths simu.yaml
```

## Guides

| Task                                                              | Guide                                               |
| ----------------------------------------------------------------- | --------------------------------------------------- |
| Configure, run and serve the planner; use its page and downloads. | [Run the observation planner](docs/obs-planner.md)  |
| Define mapping patterns and trajectories; write preset files.     | [Mapping patterns and presets](docs/mapping.md)     |
| Compute planning results in Python and export their files.        | [Plan an observation in Python](docs/planning.md)   |
| Describe sky sources; replay a recorded telescope trajectory.     | [Sky sources and telescope replay](docs/sources.md) |

<!-- prettier-ignore-start -->
[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/toltec-astro/tolteca_simu/discussions

<!-- prettier-ignore-end -->
