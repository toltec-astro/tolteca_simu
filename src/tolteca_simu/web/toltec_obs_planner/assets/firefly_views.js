// Sky and coverage views of the TolTEC observation planner, drawn by Firefly.
//
// The page loads firefly_loader.js from the Firefly server. Each view is a
// Firefly viewer with one plot. As in v1, the sky view is one HiPS plot that
// follows the target; each planning result replaces its region layers and sets
// its field of view, keeping the user's survey and display settings. The
// result's coverage FITS file (gzip compressed, as the page keeps it for its
// download) is uploaded and shown in the coverage view. Both views are drawn
// at the same time.

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

// The viewers, the plots, the sky center, and the region layers drawn.
const drawn = {
  viewers: {},
  count: 0,
  sky: null,
  skyReady: null,
  skyCenter: null,
  skyKey: null,
  coverage: null,
  layers: [],
};

// Create a Firefly viewer in its element, unless the element holds it; a new
// element (the page re-rendered) gets a new viewer, and the view's plot is
// drawn again.
const ensureViewer = (firefly, viewerId, view) => {
  const element = document.getElementById(viewerId);
  if (drawn.viewers[view] === viewerId && element.childElementCount > 0) {
    return;
  }
  if (drawn[view]) {
    removePlot(firefly, drawn[view]);
    drawn[view] = null;
  }
  if (view === "sky") {
    drawn.skyReady = null;
    drawn.skyKey = null;
  }
  // The new viewer draws the view again.
  const { NewPlotMode, IMAGE } = firefly.util.image;
  const newPlots = NewPlotMode.create_replace.key;
  firefly.action.dispatchAddViewer(viewerId, newPlots, IMAGE);
  firefly.util.renderDOM(element, firefly.ui.MultiImageViewer, {
    viewerId,
    canReceiveNewPlots: newPlots,
    Toolbar: firefly.ui.MultiViewStandardToolbar,
  });
  drawn.viewers[view] = viewerId;
};

const plotRequest = (firefly, params) =>
  firefly.util.image.WebPlotRequest.makeFromObj({
    ...params,
    GroupLocked: false,
  });

const removeLayers = (firefly, plotId) => {
  for (const [layerId, layerPlotId] of drawn.layers) {
    if (layerPlotId === plotId) {
      firefly.action.dispatchDeleteRegionLayer(layerId, plotId);
    }
  }
  drawn.layers = drawn.layers.filter(
    ([, layerPlotId]) => layerPlotId !== plotId,
  );
};

const removePlot = (firefly, plotId) => {
  removeLayers(firefly, plotId);
  firefly.action.dispatchDeletePlotView({ plotId });
};

const addLayer = (firefly, plotId, layer) => {
  const layerId = `${layer.id}-${plotId}`;
  firefly.action.dispatchCreateRegionLayer(
    layerId,
    layer.title,
    null,
    layer.regions,
    plotId,
  );
  drawn.layers.push([layerId, plotId]);
  if (!layer.visible) {
    firefly.action.dispatchChangeVisibility({
      id: layerId,
      visible: false,
      plotId,
      useGroup: false,
    });
  }
};

// Show a field of view of fovDeg across the width of the plot, as Aladin
// Lite does.
const setFov = (firefly, plotId, fovDeg) => {
  const pv = firefly.util.image
    .visRoot()
    .plotViewAry.find((p) => p.plotId === plotId);
  const plot = pv.plots[0];
  firefly.action.dispatchZoom({
    plotId,
    userZoomType: "LEVEL",
    level: (pv.viewDim.width * plot.projection.pixelScaleDeg) / fovDeg,
    actionScope: "SINGLE",
  });
};

const worldPt = (firefly, radec) =>
  firefly.util.image.makeWorldPt(radec[0], radec[1]);

// The sky plot, created at the target on first use; later calls recenter it.
const centerSky = async (firefly, settings, viewerId, radec) => {
  if (!drawn.skyReady) {
    const plotId = `toltec-sky-${++drawn.count}`;
    drawn.sky = plotId;
    drawn.skyCenter = radec;
    firefly.action.dispatchPlotHiPS({
      plotId,
      viewerId,
      wpRequest: plotRequest(firefly, {
        Type: "HiPS",
        plotId,
        hipsRootUrl: settings.hips,
        WorldPt: `${radec[0]};${radec[1]};EQ_J2000`,
        Title: "Sky view",
        PredefinedOverlayIds: HIPS_OVERLAYS,
      }),
    });
    drawn.skyReady = waitForPlot(firefly, plotId).then(() => {
      setFov(firefly, plotId, settings.fov_default);
      return plotId;
    });
    return drawn.skyReady;
  }
  const plotId = await drawn.skyReady;
  if (JSON.stringify(radec) !== JSON.stringify(drawn.skyCenter)) {
    drawn.skyCenter = radec;
    firefly.action.dispatchRecenter({
      plotId,
      centerPt: worldPt(firefly, radec),
    });
  }
  return plotId;
};

const drawSky = async (firefly, views, settings, viewerId, radec) => {
  const plotId = await centerSky(firefly, settings, viewerId, radec);
  removeLayers(firefly, plotId);
  setFov(firefly, plotId, views.size_deg);
  for (const layer of views.sky_layers) {
    addLayer(firefly, plotId, layer);
  }
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
  for (const layer of views.coverage_layers) {
    addLayer(firefly, plotId, layer);
  }
};

const fireflyApi = (fireflyUrl) => {
  const timeout = new Promise((_, reject) =>
    setTimeout(
      () => reject(new Error(`Firefly is not available at ${fireflyUrl}`)),
      FIREFLY_LOAD_TIMEOUT_MS,
    ),
  );
  return Promise.race([window.toltecObsPlannerFirefly, timeout]);
};

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.toltec_obs_planner = Object.assign(
  window.dash_clientside.toltec_obs_planner || {},
  {
    center_firefly_sky: function (radec, settings, statusId, skyElementId) {
      if (!radec) {
        return window.dash_clientside.no_update;
      }
      const report = (text) =>
        window.dash_clientside.set_props(statusId, { children: text });
      fireflyApi(settings.url)
        .then((firefly) => {
          const viewerId = elementId(skyElementId);
          ensureViewer(firefly, viewerId, "sky");
          return centerSky(firefly, settings, viewerId, radec);
        })
        .catch((error) => report(error.message));
      return radec;
    },
    render_firefly_views: function (
      views,
      downloads,
      settings,
      radec,
      statusId,
      skyElementId,
      coverageElementId,
    ) {
      if (!views || !downloads || !radec) {
        return "Press Execute to plan the observation.";
      }
      const fireflyUrl = settings.url;
      const report = (text) =>
        window.dash_clientside.set_props(statusId, { children: text });
      // The upload needs only the Firefly server, not its loaded API.
      const { filename, content_gzip } = downloads.coverage;
      const upload = window.toltecObsPlanner
        .base64ToBlob(content_gzip, "application/gzip")
        .then((blob) => uploadFile(fireflyUrl, blob, `${filename}.gz`));
      // Its failure is reported when the coverage view awaits it.
      upload.catch(() => {});
      fireflyApi(fireflyUrl)
        .then(async (firefly) => {
          const skyViewerId = elementId(skyElementId);
          const coverageViewerId = elementId(coverageElementId);
          ensureViewer(firefly, skyViewerId, "sky");
          ensureViewer(firefly, coverageViewerId, "coverage");
          // The sky layers are kept when only the coverage changes, such as
          // when switching its unit.
          const skyKey = JSON.stringify([views.size_deg, views.sky_layers]);
          const drawing = [];
          if (skyKey !== drawn.skyKey) {
            drawn.skyKey = skyKey;
            drawing.push(drawSky(firefly, views, settings, skyViewerId, radec));
          }
          drawing.push(drawCoverage(firefly, views, upload, coverageViewerId));
          await Promise.all(drawing);
          report(
            "Use each view's toolbar for color, stretch and layers; " +
              "detectors are a layer to switch on.",
          );
        })
        .catch((error) => report(error.message));
      return "Drawing the views…";
    },
  },
);
