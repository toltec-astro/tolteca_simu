Models and configuration fields
===============================

These references are generated from Pydantic models. See :doc:`modules` for the
functions and classes that use them.

Observation description
-----------------------

.. autopydantic_model:: tolteca_simu.planning.ObservationDescription
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.toltec.settings.ToltecSettings
   :class-doc-from: class

Mapping patterns
----------------

.. autodata:: tolteca_simu.mapping.MappingPattern
   :no-value:

.. autopydantic_model:: tolteca_simu.mapping.RasterPattern
   :class-doc-from: class
   :members:
   :inherited-members: FrozenBaseModel

.. autopydantic_model:: tolteca_simu.mapping.LissajousPattern
   :class-doc-from: class
   :members:
   :inherited-members: FrozenBaseModel

.. autopydantic_model:: tolteca_simu.mapping.DoubleLissajousPattern
   :class-doc-from: class
   :members:
   :inherited-members: FrozenBaseModel

.. autopydantic_model:: tolteca_simu.mapping.RastajousPattern
   :class-doc-from: class
   :members:
   :inherited-members: FrozenBaseModel

Mapping presets
---------------

.. autopydantic_model:: tolteca_simu.planning.PresetParam
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.planning.MappingPreset
   :class-doc-from: class
   :members:

.. autopydantic_model:: tolteca_simu.planning.MappingPresets
   :class-doc-from: class
   :members:

Simulation settings
-------------------

.. autopydantic_model:: tolteca_simu.config.SimuConfig
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.config.ObsPlannerConfig
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.config.ObsPlannerServerConfig
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.config.LmtPlannerConfig
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.config.ToltecPlannerConfig
   :class-doc-from: class

.. autodata:: tolteca_simu.config.ViewerConfig
   :no-value:

.. autopydantic_model:: tolteca_simu.config.AladinLiteViewerConfig
   :class-doc-from: class

.. autopydantic_model:: tolteca_simu.config.FireflyViewerConfig
   :class-doc-from: class
