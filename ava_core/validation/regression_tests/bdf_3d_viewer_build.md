# bdf_3d_viewer_build Regression Procedure

Run the AVA engineering tool tests that exercise `bdf_3d_viewer_build`.

Required cases:

- `synthetic_plate_bdf`: build a viewer from a small CQUAD4 BDF and confirm `index.html`, `viewer_config.json`, and `data/geometry.json` exist.
- `diagnostic_bdf`: build a viewer from a BDF with duplicate and floating nodes and confirm diagnostic counts remain in geometry JSON.
- `missing_bdf_case`: request a missing BDF path and confirm the tool fails without exposing raw model text.
