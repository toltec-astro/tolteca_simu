# Test data

Inputs copied from real v1 simulation runs, unchanged unless noted:

| File                          | Origin                                                                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `point_source_flux_cat0.ecsv` | `work_toltec/test_point_source_flux/three_sources/cat0.ecsv`                                                                                                                                      |
| `aztec_sources_pope.asc`      | `work_toltec/test_simu_redu/aztec_sources_pope.asc`                                                                                                                                               |
| `oph1400_cutout.fits`         | `work_toltec/test_toast_atm/refdata/Oph1400Toltec.fits`: 120 × 120 pixel cutouts of `A1100_I`, `A1400_I` and `A2000_I` around the 1.1 mm peak, with their WCS, `SIGUNIT`, `STOKES` and `WAVELNTH` |

The `v1_*_reference.json` files hold values recorded with v1 tolteca; each names
its host, environment, commit and recording script.
