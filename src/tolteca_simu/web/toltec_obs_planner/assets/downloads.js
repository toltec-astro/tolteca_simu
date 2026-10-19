// Downloads of the TolTEC observation planner, saved from the page's
// downloads store without a server request.

window.toltecObsPlanner = window.toltecObsPlanner || {};

// Blob of base64-encoded bytes, decoded by the browser.
window.toltecObsPlanner.base64ToBlob = async (content, type) =>
  (await fetch(`data:${type};base64,${content}`)).blob();

const blobToBase64 = (blob) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.toltec_obs_planner = Object.assign(
  window.dash_clientside.toltec_obs_planner || {},
  {
    // Save the coverage FITS file: the store keeps it gzip compressed.
    save_coverage: async function (_nClicks, downloads) {
      if (!downloads) {
        return window.dash_clientside.no_update;
      }
      const { filename, content_gzip } = downloads.coverage;
      const compressed = await window.toltecObsPlanner.base64ToBlob(
        content_gzip,
        "application/gzip",
      );
      const fits = await new Response(
        compressed.stream().pipeThrough(new DecompressionStream("gzip")),
      ).blob();
      return {
        content: await blobToBase64(fits),
        filename,
        base64: true,
        type: "application/fits",
      };
    },
  },
);
