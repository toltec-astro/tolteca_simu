// Sidereal time for the site information of the TolTEC observation planner,
// computed as v1 did (tolteca obs_planner assets/astro_utils.js).

window.toltecObsPlanner = window.toltecObsPlanner || {};

// Julian date of a Date.
const julianDate = (date) => date.getTime() / 86400000.0 + 2440587.5;

// Greenwich sidereal time, in hours.
const greenwichSiderealTime = (date) => {
  const jd = julianDate(date);
  const jd0 = Math.floor(jd - 0.5) + 0.5;
  const t = (jd0 - 2451545.0) / 36525.0;
  let t0 = (6.697374558 + 2400.051336 * t + 0.000025862 * t * t) % 24;
  if (t0 < 0) {
    t0 += 24;
  }
  const ut =
    ((date.getUTCMilliseconds() / 1000 + date.getUTCSeconds()) / 60 +
      date.getUTCMinutes()) /
      60 +
    date.getUTCHours();
  let gst = (t0 + ut * 1.002737909) % 24;
  if (gst < 0) {
    gst += 24;
  }
  return gst;
};

// Local sidereal time, in hours, at an east longitude in degrees.
window.toltecObsPlanner.getLST = (date, lon) => {
  let d = (greenwichSiderealTime(date) + lon / 15.0) / 24.0;
  d -= Math.floor(d);
  return 24.0 * d;
};
