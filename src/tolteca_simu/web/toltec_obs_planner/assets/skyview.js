// Sky view of the TolTEC observation planner, drawn with Aladin Lite v3.
//
// The planner fills a store with the layers of each planning result; this
// clientside callback draws them in the viewer, which it creates on first use
// in the given container.
window.dash_clientside = Object.assign({}, window.dash_clientside, {
  toltec_obs_planner: {
    render_sky: function (layers, containerId) {
      const container = document.getElementById(containerId);
      if (!container) {
        return window.dash_clientside.no_update;
      }
      if (typeof A === "undefined") {
        return "Aladin Lite could not be loaded; the sky view is unavailable.";
      }
      if (!layers) {
        return "Complete the observation description.";
      }
      A.init.then(() => {
        let aladin = container._aladin;
        if (!aladin) {
          aladin = A.aladin(container, {
            survey: "P/DSS2/color",
            cooFrame: "icrs",
            showLayersControl: true,
            showCooGridControl: true,
            showSimbadPointerControl: true,
            showFullscreenControl: true,
          });
          container._aladin = aladin;
        }
        aladin.removeOverlays();
        aladin.gotoRaDec(layers.target[0], layers.target[1]);
        aladin.setFoV(layers.fov);
        aladin.setOverlayImageLayer(
          A.image(layers.image.url, {
            name: layers.image.name,
            colormap: "viridis",
            opacity: 0.7,
          }),
          "coverage",
        );
        const trajectory = A.graphicOverlay({
          name: "Trajectory",
          color: "red",
          lineWidth: 1,
        });
        aladin.addOverlay(trajectory);
        trajectory.add(A.polyline(layers.trajectory));
        const outline = A.graphicOverlay({
          name: "Coverage outline",
          color: "#66cccc",
          lineWidth: 2,
        });
        aladin.addOverlay(outline);
        if (layers.outline.length > 2) {
          outline.add(A.polygon(layers.outline));
        }
        const detectors = A.graphicOverlay({
          name: layers.detectors.name,
          color: "#4dabf7",
          lineWidth: 1,
        });
        aladin.addOverlay(detectors);
        for (const [ra, dec] of layers.detectors.coords) {
          detectors.add(A.circle(ra, dec, layers.detectors.radius));
        }
        // Many detectors clutter the view; they are a layer to switch on.
        detectors.hide();
      });
      return (
        `${layers.image.name} (${layers.image.unit}), trajectory, ` +
        "coverage outline, and detectors; use the layer control to switch them."
      );
    },
  },
});
