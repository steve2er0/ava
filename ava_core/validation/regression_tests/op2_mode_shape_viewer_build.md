# op2_mode_shape_viewer_build Regression Procedure

Run the AVA engineering tool tests that exercise `op2_mode_shape_viewer_build`.

Required cases:

- `synthetic_modal_cache_case`: build a viewer from a small BDF and two-mode OP2-derived JSON export, then confirm `data/modes/manifest.json` and each mode shape file exist.
- `mismatched_mode_node_case`: include at least one modal node absent from the BDF and confirm workspace generation still succeeds.
- `missing_op2_case`: request a missing OP2/modal export path and confirm the tool fails without exposing raw result data.
