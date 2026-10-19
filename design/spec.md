# TolTECA simulation specification

Status: draft for review. The user answered the first round of open decisions on
2026-10-16; the remaining items are listed in [Open decisions](#open-decisions)
and [Deferred](#deferred). A statement elsewhere does not settle an open
decision.

## Purpose and scope

- `tolteca_simu` predicts what an LMT observation will record and deliver,
  before or alongside the real observation.
- Observers use it to plan observations: target visibility, telescope
  trajectory, sky coverage, sensitivity and time cost, through Python, the
  command line, or the observation planner web application.
- The first deliverable is the observation planner and the planning API behind
  it. Synthetic observations and signal injection are later scope; their
  sections record intent only.
- TolTECA defines the observation description and its results. Backends compute
  signals for that description; several backends may serve the same description.
- Telescope operation, scheduling, proposal handling and data reduction are
  outside this scope. Reduction consumes simulated data through the same
  interfaces as real data.

## Concepts

| Term                      | Meaning                                                                                                           |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Observation description   | Site, target, start time, mapping pattern, instrument configuration, and conditions of one observation.           |
| Mapping pattern           | Telescope motion as offsets in time from a reference point.                                                       |
| Trajectory                | A mapping pattern rendered around a target, from a start time, in a reference frame.                              |
| Reference frame           | Frame in which pattern offsets are interpreted, e.g. horizon or equatorial.                                       |
| Instrument specialization | The parts of planning one instrument supplies: detector layout, sensitivity model, presets, and its result views. |
| Array property table      | Per-detector instrument properties: array, network, position, orientation, and response parameters.               |
| Calibration artifact      | Versioned static input data, such as an array property table, passbands, or atmosphere model tables.              |
| Conditions                | Atmosphere and telescope state that set the detected background, such as an atmosphere model and the surface RMS. |
| Noise scaling             | Tunable factors that adjust predicted detector noise empirically, on top of the power-loading model.              |
| Preset                    | A named mapping pattern with default parameter values and permitted ranges.                                       |
| Planning result           | Visibility, trajectory, coverage, sensitivity, and time cost derived from an observation description.             |
| Backend                   | A component that computes signals for an observation description.                                                 |
| Job key (`job_key`)       | The stem that identifies one simulation run and its outputs.                                                      |

## Observation description

- An observation description fully determines its planning results and simulated
  signals. The same description yields the same results through Python, the
  command line, and the web application.
- Physical quantities carry units. Inputs are validated against their physical
  type before use.
- A description is serializable and reloadable. A saved description reproduces
  its results.

### Sites

- A site supplies the observer location and local time conventions used for
  visibility and coordinate transformations.
- The LMT is the supported site. Site facts come from TolTECA's LMT conventions;
  `tolteca_simu` does not redefine them.

### Targets and time

- A target is a named source or a sky coordinate in a stated frame. Name
  resolution is an input convenience; the resolved coordinate is what a
  description records.
- The start time is an absolute time. Visibility and trajectories are evaluated
  relative to it.
- A target below the site's minimum usable elevation during the observation is
  reported to the user, not silently accepted.

### Mapping patterns

- Mapping patterns describe how the telescope covers a field. Pattern families
  are parameterized offsets; trajectories are their rendering on the sky.

| Pattern family                                        | Kind                        |
| ----------------------------------------------------- | --------------------------- |
| Raster                                                | Raster-like                 |
| Lissajous                                             | Lissajous                   |
| Double Lissajous                                      | Lissajous                   |
| Rastajous                                             | Raster-like                 |
| Recorded trajectory (replay of an LMT telescope file) | Determined by the recording |

- A pattern defines its own duration. A raster-like pattern cannot be observed
  for longer than its duration; Lissajous-like patterns may repeat.
- Pattern offsets are evaluated at arbitrary times. Evaluation is deterministic
  and independent of sampling rate; sampling is chosen by the consumer.
- Rendering a pattern around a target applies the reference frame at the
  evaluated times, including the time dependence of horizon coordinates.
- A recorded trajectory reads LMT telescope files through TolTECA's telescope
  data access. It preserves the recorded target, times, and hold state.

### Instruments

- An instrument defines how detectors view the sky and respond to it.
- Planning is instrument-agnostic. Each instrument provides a specialization
  through one interface: its detector layout, sensitivity model, presets, and
  any instrument-specific result views. Adding an instrument adds a
  specialization and changes no shared planning code.
- TolTEC is the first specialization. Its detectors are described by an array
  property table, the same entity that reduction uses.
- Detector positions project from the instrument focal plane to the sky along a
  trajectory, including the parallactic rotation for horizon-referenced
  observations.
- Array facts such as band, beam size, and passband have one owner in TolTECA;
  `tolteca_simu` consumes them.

### Calibration artifacts

- The array property table, passbands, and static atmosphere model tables are
  calibration artifacts. They belong to a TolTECA calibration-data component
  that does not yet exist; earlier work is in `toltec-astro/toltec_calib`.
- Until that component exists, a temporary calibration data store beside
  `tolteca_simu` in the development location holds the artifacts the planner
  needs. Configuration names the store and the artifact versions used; code does
  not embed artifact paths or bundle artifact data.
- Planning results report the calibration artifacts they used.

### Conditions and sensitivity model

- The sensitivity model predicts the detected background, noise, and mapping
  speed for each array under stated conditions.
- Atmosphere conditions are selected from named models for the site, such as
  quartile conditions. A time-domain atmosphere realization is a backend
  capability, not a planning input.
- Telescope surface RMS is an explicit condition.
- Noise scaling is a tunable empirical adjustment on top of the power-loading
  model, not a derived quantity. Detector noise factors are configured per
  atmosphere model and array. v1 `main` adds an optional target mapping speed
  per array that derives a further global factor; without a target, the factor
  is one.
- Sensitivity results report the conditions and noise scaling they assume.

### Sources

- Sources describe sky brightness for synthetic observations and injection: a
  FITS image, or a point-source catalog with per-array fluxes.
- Planning results do not require sources.

## Planning

- Planning answers whether, when, and how efficiently an observation can achieve
  its goal, without simulating detector timestreams.

| Planning result  | Meaning                                                                           |
| ---------------- | --------------------------------------------------------------------------------- |
| Visibility       | Target elevation over the observing day, with the observation interval marked.    |
| Trajectory       | Telescope and detector tracks of the observation in the chosen frame.             |
| Coverage         | Detector sampling density on the sky per array, accumulated along the trajectory. |
| Sensitivity      | Mapping speed and expected map depth per array under the stated conditions.       |
| Time cost        | Observing time including overheads, for the requested depth or area.              |
| Observing script | The observation expressed for the LMT observing tool.                             |

- Planning results derive from the observation description alone. They are
  computed by the planning API, which the web application and the command line
  call; neither reimplements a calculation.
- Coverage and sensitivity use the array property table and sensitivity model of
  the selected instrument specialization.
- Presets bound user choices. A preset's permitted ranges are configuration, not
  code.
- Planning results agree with the production observation planner (v1 branch
  `obs_planner` at `639b8a1`) for the same inputs, calibration artifacts, and
  noise scaling, within stated tolerances.

## Observation planner application

- The observation planner is a web application for observers to build an
  observation description interactively and inspect its planning results.
- It is provided as the module `tolteca_simu.web.toltec_obs_planner` and is the
  first deliverable of this package.
- The application is a client of the planning API. Interactive state is the
  observation description; results are recomputed from it, not stored
  separately.
- The application composes shared planning views with the views of the selected
  instrument specialization.
- The site, instrument, title, presets, calibration artifacts, conditions, and
  noise scaling are deployment configuration, loaded through TolTECA's
  configuration system. The application does not read environment variables
  directly.
- A user can export the current observation description and its observing
  script, and reload a description to restore the same results.
- Results update interactively as the observer edits the description.
- A sky view shows the planning results over a sky survey: the coverage map, the
  trajectory, the coverage outline, and the instrument's detectors. It is drawn
  by Aladin Lite through `dash_aladin_lite`, a general-purpose Dash component
  package outside TolTECA. A coverage plot gives the map values.
- The application does not produce synthetic acquisitions.

### Deployment

- The application serves on a local port and is published through a reverse
  proxy, under a configurable URL prefix.
- Production runs the application under gunicorn. Development and debugging run
  Dash's own server directly.
- Both modes load the same configuration through the `tolteca_simu` command
  line, following the `tolteca_web` pattern.

## Synthetic observations (later scope)

- Synthetic observations produce data that TolTECA readers, the KIDs pipeline,
  and Citlali consume as if recorded, for pipeline validation and forecasting.
- A synthetic observation evaluates sources, conditions, and detector response
  along the trajectory, and records them as acquisitions with the telescope,
  KIDs, and half-wave plate interfaces of a real observation.
- Simulated acquisitions are identified as simulated: master `simu`.
- A simulation run is identified by its job key, the stem of its outputs.
- Evaluation may be split in time for memory or parallel execution. Splitting
  does not change the result.
- Random realizations, such as the atmosphere, are reproducible from recorded
  seeds.
- The time-domain atmosphere comes from the TOAST backend. The KIDs detector
  response converts optical power to recorded readout signals.

## Signal injection (later scope)

- Signal injection adds simulated source signals to real acquisitions, to
  measure how reduction recovers known sources.
- Injection follows the real acquisition's recorded trajectory, detector
  properties, and detector model. The original acquisition is never modified;
  injected data is a new, separately identified acquisition.

## Configuration and entry points

- One configuration key, `simu`, holds the simulation configuration; one handler
  builds the planning and simulation objects from it. Configuration composes
  from files and command-line overrides in TolTECA's usual way.
- The configuration schema is designed for v3, not copied from v1. Names are
  snake_case words (`job_key`, not v1 `jobkey`); a v1 name survives only when it
  is already clear.
- The command line `tolteca_simu` and the Python API run the same operations.
- Scientific computations are callable without the configuration system, from
  explicit inputs with units.

## Integrated workflows

| Workflow                                        | Handoff                                                                                                                          |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Plan an observation                             | Observation description → planning API → planning results → web application or command line.                                     |
| Validate reduction with a synthetic observation | Observation description and sources → backend evaluation → simulated acquisitions → input discovery → KIDs pipeline and Citlali. |
| Measure source recovery                         | Real acquisition and sources → injection → injected acquisition → reduction → comparison with the injected sources.              |

## Open decisions

1. **Side-by-side result display.** CARTA, a full web application, can serve as
   a display backend beside the planner: the planner publishes result files and
   links to them ("open in CARTA"). Whether and how to provide it waits for a
   CARTA deployment.
2. **Preservation and serving of calibration artifacts.** The temporary store is
   a stopgap. The lmtdv0 Dataverse that served the static atmosphere tables is
   unavailable.

## Deferred

- Synthetic acquisition layout, writers, and the KIDs forward model.
- How job keys map to TolTECA data-product identifiers.
- Parts of v1 outside the planner slice: `simu0`, the SEQUOIA simulator, and the
  timestream projection.
