# Export diagnostics

Every Shogun invocation saves its full console output next to its generated HSL
script, with the extension `.shogun.log`. Repeated lines are condensed only in
the console. A subsequent run of the same script replaces its log.

To trace aligned prop visibility checks, enable diagnostics before starting the
exporter in PowerShell:

```powershell
$env:VICON_EXPORTER_DIAGNOSTICS = "1"
uv run .\main.py
```

Select the failing take and the aligned prop export. If its exports already exist,
enable overwrite to execute the filter again. Diagnostics print the prop and
marker names before querying trajectories, followed by the trajectory boundary
count. The last `DIAG` messages before an error identify the operation being
processed; they do not by themselves prove that marker data is corrupt.

For individual props, the log is
`aligned_exports/scripts/aligned_export_props.shogun.log` inside the take.
Combined props use `aligned_scene_extras.shogun.log` in the same directory.

Disable detailed diagnostics afterwards:

```powershell
Remove-Item Env:VICON_EXPORTER_DIAGNOSTICS
```

This switch controls exporter-generated prop tracing, not Vicon's internal logging
level. Full Shogun console logs remain enabled.
