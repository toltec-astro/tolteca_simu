"""Calibration artifacts read from the temporary calibration data store.

The store (``tolteca_cal_data``) holds versioned static inputs: the LMT
atmosphere model tables, TolTEC array property tables, and passbands. This
module owns the store's layout; callers name the store root and, for the
array property table, the file in use.
"""

from functools import cache
from pathlib import Path

import numpy as np
from astropy.table import QTable

__all__ = ["CalDataStore"]


@cache
def _read_table(path: Path) -> QTable:
    return QTable.read(path, format="ascii.ecsv")


@cache
def _read_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        return dict(data)


class CalDataStore:
    """Access to the calibration data store.

    Files are read once per process and shared; callers must not modify the
    returned tables.

    Parameters
    ----------
    root : pathlib.Path
        Root directory of the store.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """Root directory of the store."""
        return self._root

    def get_lmt_atm_table(self, name: str) -> dict[str, np.ndarray]:
        """Return an LMT am atmosphere model table.

        Parameters
        ----------
        name : str
            Model name, such as ``"am_q25"``.

        Returns
        -------
        dict of numpy.ndarray
            ``atmFreq`` (GHz), ``el`` (deg), ``atmTRJ`` (K) and ``atmTtx``.
        """
        return _read_npz(self._root / "lmt" / "atm_am" / f"{name}.npz")

    def get_toltec_passband(self, array_name: str) -> QTable:
        """Return the passband of a TolTEC array.

        Parameters
        ----------
        array_name : str
            Array name.

        Returns
        -------
        astropy.table.QTable
            Columns ``f``, ``wl`` and ``throughput``.
        """
        return _read_table(
            self._root / "toltec" / "passband" / f"{array_name}_passband.ecsv"
        )

    def get_toltec_apt(self, path: str) -> QTable:
        """Return a TolTEC array property table.

        Parameters
        ----------
        path : str
            File path relative to the store root.

        Returns
        -------
        astropy.table.QTable
            The table, with detector offsets ``x_t`` and ``y_t``.
        """
        return _read_table(self._root / path)

    def get_toltec_apt_designed(self, array_name: str) -> QTable:
        """Return the designed array property table of a TolTEC array.

        Parameters
        ----------
        array_name : str
            Array name.

        Returns
        -------
        astropy.table.QTable
            The designed detectors, with ``edge_indices`` in the metadata.
        """
        return _read_table(
            self._root / "toltec" / "apt_designed" / f"{array_name}_prop.ecsv"
        )
