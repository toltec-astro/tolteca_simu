API reference
=============

Observation planning
--------------------

.. automodapi:: tolteca_simu.planning
   :skip: MappingPreset, MappingPresets, ObservationDescription, PresetParam

.. autofunction:: tolteca_simu.planning.presets.get_default_presets_path

.. automodapi:: tolteca_simu.mapping
   :skip: DoubleLissajousPattern, LissajousPattern, RastajousPattern, RasterPattern

See :doc:`models` for observation descriptions, mapping patterns and presets.

.. automodapi:: tolteca_simu.sky

.. automodapi:: tolteca_simu.lmt

.. autodata:: tolteca_simu.lmt.LmtAtmModelName
   :no-value:

.. automodapi:: tolteca_simu.lmtot

Sky sources
-----------

.. automodapi:: tolteca_simu.sources

TolTEC
------

.. automodapi:: tolteca_simu.toltec

.. autodata:: tolteca_simu.toltec.info.ToltecArrayName
   :no-value:

.. autodata:: tolteca_simu.toltec.info.TOLTEC_ARRAYS
   :no-value:

.. autodata:: tolteca_simu.toltec.info.TOLTEC_PLATE_SCALE

.. automodapi:: tolteca_simu.toltec.sensitivity

.. autodata:: tolteca_simu.toltec.sensitivity.POLARIZED_NOISE_FACTOR

.. automodapi:: tolteca_simu.toltec.time_cost

.. automodapi:: tolteca_simu.toltec.planning

.. automodapi:: tolteca_simu.toltec.exports

Calibration data
----------------

.. automodapi:: tolteca_simu.cal_data

Configuration and applications
------------------------------

See :doc:`models` for the ``simu`` configuration fields.

.. automodapi:: tolteca_simu.core

.. automodapi:: tolteca_simu.web.toltec_obs_planner

Command line
------------

.. typer:: tolteca_simu.cli.app
   :prog: tolteca_simu
   :width: 90
   :show-nested:
