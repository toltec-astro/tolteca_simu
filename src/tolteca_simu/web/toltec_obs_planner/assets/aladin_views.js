// Sky and coverage views of the TolTEC observation planner, drawn by Aladin
// Lite (dash_aladin_lite).
//
// The sky view takes its layers from the views store. The coverage view shows
// the result's coverage FITS file, which the page keeps gzip compressed for its
// download: it is decompressed here and given to Aladin Lite as a blob URL.

// The blob URL of the coverage image shown now.
let coverageUrl = null;

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.toltec_obs_planner = Object.assign(
  window.dash_clientside.toltec_obs_planner || {},
  {
    render_aladin_views: async function (views, downloads) {
      const noUpdate = window.dash_clientside.no_update;
      if (!views || !downloads) {
        return [
          ...Array(6).fill(noUpdate),
          "Press Execute to plan the observation.",
        ];
      }
      const { filename, content_gzip } = downloads.coverage;
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
        colormap: "viridis",
        base: true,
      };
      const { sky, coverage } = views;
      return [
        sky.target,
        sky.fov,
        sky.layers,
        coverage.target,
        coverage.fov,
        [image, ...coverage.layers],
        `Use each view's layer control for layers and, on ${filename}, ` +
          "the colormap, stretch and cuts; detectors are a layer to switch on.",
      ];
    },
  },
);
