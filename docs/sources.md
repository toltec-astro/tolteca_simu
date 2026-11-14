# Sky sources and telescope replay

Sources give the sky surface brightness that detectors see, per array, as a
point-source catalog or as FITS images. A recorded LMT telescope file gives the
trajectory of a real observation, at any sampling times.

| Need                                        | Use                                                  |
| ------------------------------------------- | ---------------------------------------------------- |
| Point sources with fluxes per array         | {py:class}`~tolteca_simu.sources.PointSourceCatalog` |
| Images of the sky, one per array            | {py:class}`~tolteca_simu.sources.ImageSource`        |
| Surface brightness along detector positions | `ImageSource.evaluate(label, ra, dec)`               |
| The trajectory of a recorded observation    | {py:func}`~tolteca_simu.planning.get_tel_trajectory` |

## Point-source catalogs

A catalog is a table with source positions and one flux column per array. Read a
file with {py:meth}`~tolteca_simu.sources.PointSourceCatalog.read`, or use a
table you have:

```{testcode}
import astropy.units as u
import numpy as np
from astropy.table import Table
from tolteca_simu.sources import PointSourceCatalog

table = Table({
    "source_name": ["src_a", "src_b"],
    "ra": [150.10, 150.12] * u.deg,
    "dec": [2.20, 2.21] * u.deg,
    "flux_a1100": [10.0, 4.0] * u.mJy,
    "flux_a2000": [3.0, 1.0] * u.mJy,
})
catalog = PointSourceCatalog.from_table(
    table, flux_columns={"a1100": "flux_a1100", "a2000": "flux_a2000"}
)
print(catalog.names, catalog.fluxes["a1100"])
```

```{testoutput}
['src_a' 'src_b'] [10.  4.] mJy
```

Columns without units are read as degrees for positions and mJy for fluxes.
Without a `source_name` column, sources are named `src0`, `src1`, and so on.

Render the catalog as images with one Gaussian beam per source. Each beam
integrates to the source flux:

```{testcode}
from tolteca_simu.toltec import TOLTEC_ARRAYS

fwhms = {name: array.a_fwhm for name, array in TOLTEC_ARRAYS.items()}
source = catalog.make_image_source(fwhms)
image = source.images["a1100"]
pixel_area = (0.5 * u.arcsec) ** 2
print(image.data.shape, f"{(image.data.sum() * image.unit * pixel_area).to(u.mJy):.2f}")
```

```{testoutput}
(326, 326) 14.00 mJy
```

The images share one grid of 0.5 arcsec pixels, centered on the sources, that
spans their extent plus ten of the largest FWHM.

## Evaluate sources

`evaluate` takes one label per row of positions, such as each detector's array,
and returns the surface brightness at each position, in MJy/sr. Positions
outside an image, and rows whose label has no image, are zero:

```{testcode}
label = ["a1100", "a1100", "a2000", "a1400"]
ra = [[150.10], [150.30], [150.10], [150.10]] << u.deg
dec = [[2.20], [2.20], [2.20], [2.20]] << u.deg
print(source.evaluate(label, ra, dec).round(3))
```

```{testoutput}
[[15.018]
 [ 0.   ]
 [ 1.363]
 [ 0.   ]] MJy / sr
```

Each position takes the value of its nearest pixel.

## FITS images

Open images from a FITS file by naming the extension for each array. The file
stays open, memory-mapped, until the `with` block ends; evaluate within it:

```{testsetup} fits
import os
import tempfile
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

previous_cwd = Path.cwd()
example_dir = tempfile.TemporaryDirectory()
os.chdir(example_dir.name)
wcs = WCS(naxis=2)
wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
wcs.wcs.crval = [150.1, 2.2]
wcs.wcs.crpix = [50.5, 50.5]
wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
header = wcs.to_header()
header["BUNIT"] = "MJy/sr"
fits.HDUList(
    [fits.PrimaryHDU(), fits.ImageHDU(np.ones((100, 100)), header, name="A1100_I")]
).writeto("sky.fits")
```

```{testcode} fits
import astropy.units as u
import numpy as np
from tolteca_simu.sources import ImageSource

with ImageSource.open("sky.fits", extensions={"a1100": "A1100_I"}) as source:
    ra = [[150.1], [150.1]] << u.deg
    dec = [[2.2], [2.2]] << u.deg
    print(source.evaluate(["a1100", "a2000"], ra, dec))
```

```{testoutput} fits
[[1.]
 [0.]] MJy / sr
```

```{testcleanup} fits
os.chdir(previous_cwd)
example_dir.cleanup()
```

Each extension needs a celestial WCS and its unit in `SIGUNIT` or `BUNIT`; an
extension without a unit raises `ValueError`.

## Replay a recorded trajectory

{py:func}`~tolteca_simu.planning.get_tel_trajectory` returns the boresight
trajectory recorded in an LMT telescope file, interpolated to the times you
give, such as the sampling times of the detectors. Reading the file requires
`tolteca_datamodels`, part of TolTECA; install TolTECA alongside `tolteca_simu`.
The example reads a telescope file from the observation tree at `data_lmt_path`:

```{testcode}
:skipif: skip_without_data_lmt

from tolteca_datamodels.lmt import open_lmt_tel
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_tel_trajectory

observer = get_lmt_observer()
path = data_lmt_path / "tel" / "tel_toltec_2025-10-31_145609_00_0002.nc"
with open_lmt_tel(path) as dataset:
    tel = dataset.load().lmt_tel
    recorded = get_tel_trajectory(tel, observer=observer)
    t = np.arange(0, recorded.t[-1].to_value(u.s), 1 / 122.0703125) << u.s
    trajectory = get_tel_trajectory(tel, observer=observer, t=t)
print(recorded.t.size, f"{recorded.t[-1]:.2f}", recorded.time[0].isot)
print(trajectory.t.size, trajectory.turnaround.sum())
```

```{testoutput}
:skipif: skip_without_data_lmt

3427 68.51 s 2025-10-31T09:28:06.880
8363 0
```

Without `t`, the trajectory has the file's own samples. Times are seconds from
the first sample; times outside the file raise `ValueError`. Samples where the
telescope recorded a hold are marked in `turnaround`.

## Detectors along a trajectory

{py:func}`~tolteca_simu.toltec.get_detector_positions` places detectors along a
planned or replayed boresight trajectory. It takes each detector's offset in the
TolTEC frame, the `x_t` and `y_t` columns of an array property table, and
returns horizon and ICRS positions with one row per detector and one column per
time. The example places all detectors of the production array property table
along the first 2 s of the replayed scan, then evaluates a source at the
detector positions, with each detector's array name as its label:

```{testcode}
:skipif: skip_without_data_lmt or skip_without_cal_data

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.config import ToltecPlannerConfig
from tolteca_simu.toltec import TOLTEC_ARRAYS, get_detector_positions

apt = CalDataStore(cal_data_path).get_toltec_apt(ToltecPlannerConfig().apt)
t = np.arange(0, 2, 1 / 122.0703125) << u.s
trajectory = get_tel_trajectory(tel, observer=observer, t=t)
positions = get_detector_positions(apt["x_t"], apt["y_t"], trajectory)

array_names = {array.index: name for name, array in TOLTEC_ARRAYS.items()}
labels = [array_names[index] for index in apt["array"]]
catalog = PointSourceCatalog.from_table(
    Table({"ra": [72.34708] * u.deg, "dec": [63.53594] * u.deg, "flux_a1100": [50.0] * u.mJy}),
    flux_columns={"a1100": "flux_a1100"},
)
source = catalog.make_image_source({"a1100": TOLTEC_ARRAYS["a1100"].a_fwhm})
signal = source.evaluate(labels, positions.coords_icrs.ra, positions.coords_icrs.dec)
print(signal.shape, f"{signal.max():.1f}")
```

```{testoutput}
:skipif: skip_without_data_lmt or skip_without_cal_data

(3553, 245) 45.6 MJy / sr
```

The detectors turn with the boresight elevation, as the TolTEC field of view
does on the sky.

Positions at each time depend on that time only, so you can evaluate a long
observation in time chunks and join the results. Memory grows with the number of
positions in a chunk, about 0.13 kB per detector and sample.

## Detector signals

{py:func}`~tolteca_simu.toltec.get_detector_loading` returns the optical power
on each detector along its positions: the source seen through the atmosphere,
and the atmosphere and instrument background at the detector's altitude, from
the loading model of each array. It also returns the standard deviation of the
white power noise per sample, and
{py:func}`~tolteca_simu.toltec.realize_power_noise` draws that noise from a
seed. The example continues with the positions and signal above, under the
median LMT atmosphere, with the planner's loading models:

```{testcode}
:skipif: skip_without_data_lmt or skip_without_cal_data

from tollan.config import RuntimeContext
from tolteca_simu.core import Simu
from tolteca_simu.toltec import get_detector_loading, realize_power_noise

simu = Simu(RuntimeContext({"simu": {"obs_planner": {"cal_data_path": cal_data_path}}}))
loading_models = simu.make_toltec_planner().get_loading_models("am_q50")
f_smp = 122.0703125 * u.Hz
loading = get_detector_loading(
    labels, positions.coords_altaz.alt, signal, loading_models, f_smp
)
noise = realize_power_noise(
    loading.power_noise, seed=1, detector_keys=apt["uid"], sample_start=0
)
power = loading.power + noise
a1100 = np.asarray(labels) == "a1100"
print(f"{loading.power[a1100].mean():.2f}", f"{loading.power_noise[a1100].mean().to(u.aW):.0f}")
```

```{testoutput}
:skipif: skip_without_data_lmt or skip_without_cal_data

15.68 pW 2087 aW
```

The noise of each sample depends only on the seed, the detector key and the
sample index within the run, so a run evaluated in time chunks, each with its
own `sample_start`, gives the same noise as a whole run.

{py:func}`~tolteca_simu.toltec.get_kids_signals` turns the power into the KIDs
detuning `x`, loss `r` and readout signal, through a KIDs model table of
TolTECA's physical model families, such as a model fit writes for a tune. The
table has one row per detector, in detector order. `power_ref` is each
detector's power when the model was measured; here the tune is at the first
sample. The detuning follows the power with the detector's responsivity, and
TolTECA's timestream solver recovers `x` and `r` from the signal with the same
table:

```{testcode}
:hide:
:skipif: skip_without_data_lmt or skip_without_cal_data

_f = np.asarray(apt["tone_freq"], float)
_n = len(_f)
model_params = Table({
    "chan": np.arange(_n), "f_in": _f, "f_g": _f, "fr": _f,
    "r": np.full(_n, 2.5e-5), "c_re": np.full(_n, 2e-5), "c_im": np.zeros(_n),
    "H0_re": np.full(_n, 1e4), "H0_im": np.zeros(_n),
    "H1_re": np.zeros(_n), "H1_im": np.zeros(_n),
})
for _c in ("f_in", "f_g", "fr"):
    model_params[_c].unit = u.Hz
for _c in ("H1_re", "H1_im"):
    model_params[_c].unit = "1 / Hz"
model_params.meta["model_schema"] = {
    "name": "KidsSweepWithAffineGain",
    "version": 1,
    "parameters": [
        {"name": _c, "unit": {"fr": "Hz", "f_g": "Hz", "H1_re": "1 / Hz", "H1_im": "1 / Hz"}.get(_c, "")}
        for _c in ("f_g", "fr", "r", "c_re", "c_im", "H0_re", "H0_im", "H1_re", "H1_im")
    ],
}
```

```{testcode}
:skipif: skip_without_data_lmt or skip_without_cal_data

from tolteca_kidsproc.timestream import TimestreamSolver
from tolteca_simu.toltec import get_kids_signals

responsivity = [TOLTEC_ARRAYS[name].responsivity.value for name in labels] / u.pW
signals = get_kids_signals(power, loading.power[:, 0], responsivity, model_params)
r, x, flags = TimestreamSolver(model_params, model_params["chan"])(
    signals.iq.real.T, signals.iq.imag.T
)
print(signals.iq.shape, np.allclose(x.T, signals.x, rtol=0, atol=1e-12))
```

```{testoutput}
:skipif: skip_without_data_lmt or skip_without_cal_data

(3553, 245) True
```

The responsivities of {py:data}`~tolteca_simu.toltec.info.TOLTEC_ARRAYS` are
typical values per array, until detector calibrations provide them per detector.
`get_kids_signals` requires TolTECA's `tolteca_kidsproc`.
