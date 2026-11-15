// Sky and coverage views of the TolTEC observation planner, drawn by Aladin
// Lite (dash_aladin_lite).
//
// The sky view takes its field of view and layers from the views of the
// result store; its center follows the target separately, as in v1. The
// coverage view shows the result's coverage FITS file, which the page keeps
// gzip compressed for its download: it is decompressed here and given to
// Aladin Lite as a blob URL.

// The blob URL of the coverage image shown now.
let coverageUrl = null;

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.toltec_obs_planner = Object.assign(
  window.dash_clientside.toltec_obs_planner || {},
  {
    render_aladin_views: async function (result) {
      const noUpdate = window.dash_clientside.no_update;
      if (!result) {
        return [...Array(5).fill(noUpdate), ""];
      }
      const { views, downloads } = result;
      const { content_gzip } = downloads.coverage;
      const compressed = await window.toltecObsPlanner.base64ToBlob(
        content_gzip,
        "application/gzip",
      );
      const fits = await new Response(
        compressed.stream().pipeThrough(new DecompressionStream("gzip")),
      ).blob();
      // Aladin Lite has fetched the previous image by now.
      if (coverageUrl) {
        URL.revokeObjectURL(coverageUrl);
      }
      coverageUrl = URL.createObjectURL(fits);
      const image = {
        type: "image",
        id: "coverage",
        name: views.coverage_title,
        url: coverageUrl,
        // As v1's JS9 view.
        colormap: "grayscale",
        base: true,
      };
      const { sky, coverage } = views;
      return [
        sky.fov,
        sky.layers,
        coverage.target,
        coverage.fov,
        [image, ...coverage.layers],
        // The legend under the sky view names the overlays.
        "",
      ];
    },
  },
);
