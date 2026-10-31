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
telescope recorded a hold are marked in `turnaround`. Evaluate sources along the
trajectory with its `coords_icrs`.
