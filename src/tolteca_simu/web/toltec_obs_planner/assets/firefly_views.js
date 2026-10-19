// Sky and coverage views of the TolTEC observation planner, drawn by Firefly.
//
// The page loads firefly_loader.js from the Firefly server. Both views are
// plots in one Firefly viewer, in its grid layout; its toolbar switches
// between the grid and one plot at a time. For each planning result, this
// callback shows the HiPS survey with the trajectory, outline and detector
// regions, and uploads the result's coverage FITS file (gzip compressed, as
// the page keeps it for its download) to show it as the coverage view. Both
// plots are drawn at the same time.

// Firefly calls onFireflyLoaded once its API is ready.
window.toltecObsPlannerFirefly =
  window.toltecObsPlannerFirefly ||
  new Promise((resolve) => {
    if (window.firefly && window.firefly.showImage) {
      resolve(window.firefly);
      return;
    }
    window.onFireflyLoaded = (firefly) => resolve(firefly || window.firefly);
  });

const FIREFLY_LOAD_TIMEOUT_MS = 30000;

// Element id of a Dash component id (a string, or a dict with sorted keys).
const elementId = (id) =>
  typeof id === "string"
    ? id
    : JSON.stringify(
        Object.fromEntries(
          Object.keys(id)
            .sort()
            .map((k) => [k, id[k]]),
        ),
      );

const waitForPlot = async (firefly, plotId) => {
  for (let i = 0; i < 300; i++) {
    if (firefly.util.image.getPrimePlot(plotId)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Firefly did not create plot ${plotId}`);
};

// Upload a file to the Firefly server; return the key that names it there.
const uploadFile = async (fireflyUrl, blob, filename) => {
  const form = new FormData();
  form.append("fileAnalysis", "false");
  form.append("file", blob, filename);
  const response = await fetch(`${fireflyUrl}CmdSrv/sync?cmd=upload`, {
    method: "POST",
    body: form,
  });
  const [status, message, cacheKey] = (await response.text()).split("::");
  if (!response.ok || status !== "200") {
    throw new Error(`upload failed: ${message || response.status}`);
  }
  return cacheKey;
};

// Each region layer belongs to the plot it was created for. Firefly would
// otherwise share it: a new plot takes over existing region layers of the
// types in its PredefinedOverlayIds (defaults below, without regions), and a
// new region layer goes to every plot of an overlay-locked group, so the plots
// are created unlocked (GroupLocked).
const IMAGE_OVERLAYS = [
  "ACTIVE_TARGET_TYPE",
  "POINT_SELECTION_TYPE",
  "NORTH_UP_COMPASS_TYPE",
  "WEB_GRID_TYPE",
  "OVERLAY_MARKER_TYPE",
  "OVERLAY_FOOTPRINT_TYPE",
].join(";");
const HIPS_OVERLAYS = [
  "ACTIVE_TARGET_TYPE",
  "POINT_SELECTION_TYPE",
  "NORTH_UP_COMPASS_TYPE",
  "OVERLAY_MARKER_TYPE",
  "OVERLAY_FOOTPRINT_TYPE",
  "EXTRACT_HIPS_FILE_TOOL_TYPE",
  "MOC_PLOT_TYPE",
].join(";");

// The viewer, and the plots and region layers drawn for the current result.
const drawn = {
  viewer: null,
  count: 0,
  sky: null,
  skyKey: null,
  coverage: null,
  layers: [],
};

// Create the Firefly viewer in its element, unless the element holds it; a
// new element (the page re-rendered) gets a new viewer and new plots.
const ensureViewer = (firefly, viewerId) => {
  const element = document.getElementById(viewerId);
  if (drawn.viewer === viewerId && element.childElementCount > 0) {
    return;
  }
  for (const plotId of [drawn.sky, drawn.coverage]) {
    if (plotId) {
      removePlot(firefly, plotId);
    }
  }
  Object.assign(drawn, { sky: null, skyKey: null, coverage: null });
  const { NewPlotMode, IMAGE } = firefly.util.image;
  const newPlots = NewPlotMode.create_replace.key;
  firefly.action.dispatchAddViewer(viewerId, newPlots, IMAGE);
  firefly.util.renderDOM(element, firefly.ui.MultiImageViewer, {
    viewerId,
    canReceiveNewPlots: newPlots,
    Toolbar: firefly.ui.MultiViewStandardToolbar,
  });
  firefly.action.dispatchChangeViewerLayout(viewerId, "grid");
  drawn.viewer = viewerId;
};

const plotRequest = (firefly, params) =>
  firefly.util.image.WebPlotRequest.makeFromObj({
    ...params,
    GroupLocked: false,
  });

const removePlot = (firefly, plotId) => {
  for (const [layerId, layerPlotId] of drawn.layers) {
    if (layerPlotId === plotId) {
      firefly.action.dispatchDeleteRegionLayer(layerId, plotId);
    }
  }
  drawn.layers = drawn.layers.filter(
    ([, layerPlotId]) => layerPlotId !== plotId,
  );
  firefly.action.dispatchDeletePlotView({ plotId });
};

const addRegions = (firefly, plotId, name, title, regions, visible = true) => {
  const layerId = `${name}-${plotId}`;
  firefly.action.dispatchCreateRegionLayer(
    layerId,
    title,
    null,
    regions,
    plotId,
  );
  drawn.layers.push([layerId, plotId]);
  if (!visible) {
    firefly.action.dispatchChangeVisibility({
      id: layerId,
      visible: false,
      plotId,
      useGroup: false,
    });
  }
};

const drawSky = async (firefly, views, viewerId) => {
  // A fresh plot id for each result, so that layers never attach to a plot
  // that is being replaced.
  const plotId = `toltec-sky-${++drawn.count}`;
  if (drawn.sky) {
    removePlot(firefly, drawn.sky);
  }
  drawn.sky = plotId;
  firefly.action.dispatchPlotHiPS({
    plotId,
    viewerId,
    wpRequest: plotRequest(firefly, {
      Type: "HiPS",
      plotId,
      hipsRootUrl: views.hips,
      WorldPt: views.world_pt,
      SizeInDeg: views.size_deg,
      Title: views.sky_title,
      PredefinedOverlayIds: HIPS_OVERLAYS,
    }),
  });
  await waitForPlot(firefly, plotId);
  const { trajectory, outline, detectors } = views.regions;
  addRegions(firefly, plotId, "trajectory", "Trajectory", trajectory);
  addRegions(firefly, plotId, "outline", "Coverage outline", outline);
  addRegions(firefly, plotId, "detectors", "Detectors", detectors, false);
};

const drawCoverage = async (firefly, views, upload, viewerId) => {
  const cacheKey = await upload;
  const plotId = `toltec-coverage-${++drawn.count}`;
  if (drawn.coverage) {
    removePlot(firefly, drawn.coverage);
  }
  drawn.coverage = plotId;
  firefly.action.dispatchPlotImage({
    plotId,
    viewerId,
    wpRequest: plotRequest(firefly, {
      plotId,
      File: cacheKey,
      Title: views.coverage_title,
      PredefinedOverlayIds: IMAGE_OVERLAYS,
    }),
  });
  await waitForPlot(firefly, plotId);
  addRegions(
    firefly,
    plotId,
    "outline",
    "Coverage outline",
    views.regions.outline,
  );
};

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.toltec_obs_planner = Object.assign(
  window.dash_clientside.toltec_obs_planner || {},
  {
    render_firefly_views: function (
      views,
      downloads,
      fireflyUrl,
      statusId,
      viewerElementId,
    ) {
      if (!views || !downloads) {
        return "Complete the observation description.";
      }
      const report = (text) =>
        window.dash_clientside.set_props(statusId, { children: text });
      // The upload needs only the Firefly server, not its loaded API.
      const { filename, content_gzip } = downloads.coverage;
      const upload = window.toltecObsPlanner
        .base64ToBlob(content_gzip, "application/gzip")
        .then((blob) => uploadFile(fireflyUrl, blob, `${filename}.gz`));
      // Its failure is reported when the coverage view awaits it.
      upload.catch(() => {});
      const timeout = new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error(`Firefly is not available at ${fireflyUrl}`)),
          FIREFLY_LOAD_TIMEOUT_MS,
        ),
      );
      Promise.race([window.toltecObsPlannerFirefly, timeout])
        .then(async (firefly) => {
          const viewerId = elementId(viewerElementId);
          ensureViewer(firefly, viewerId);
          // The sky view is kept when only the coverage changes, such as
          // when switching its unit.
          const skyKey = JSON.stringify([
            views.world_pt,
            views.size_deg,
            views.regions,
          ]);
          const drawing = [];
          if (skyKey !== drawn.skyKey) {
            drawn.skyKey = skyKey;
            drawing.push(drawSky(firefly, views, viewerId));
          }
          drawing.push(drawCoverage(firefly, views, upload, viewerId));
          await Promise.all(drawing);
          // The grid follows the order in which Firefly creates the plots;
          // keep the sky view first.
          firefly.action.dispatchReplaceViewerItems(
            viewerId,
            [drawn.sky, drawn.coverage],
            firefly.util.image.IMAGE,
          );
          report(
            "Use the toolbar for color, stretch and layers of the selected " +
              "view, and for the grid or single layout; detectors are a " +
              "layer to switch on.",
          );
        })
        .catch((error) => report(error.message));
      return "Drawing the views…";
    },
  },
);
