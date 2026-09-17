![logo](images/logo.png)

# Vicon Exporter

A small Python tool for processing Vicon Shogun takes (`.mcp`) with Shogun Post CL. It generates HSL scripts, runs Shogun, and writes predictable mocap exports for the local pipeline.

Important: this code requires Vicon Shogun Post with `ShogunPostCL.exe`. Set the executable path in `configuration/settings.py`.

## Features

- Runs Shogun Post CL with live streaming output.
- Generates HSL scripts for each take.
- Exports actor `.fbx`, `.bvh`, `.c3d`, and `.mcp` files.
- Runs mannequin, legacy MetaHuman-adjusted, Vicon automatic MetaHuman, and Geeno retarget exports.
- Can read aLigner `*.export.yaml` files and export an aligned frame range without overwriting the classic output.
- Finds take folders recursively from a selected root folder.

## Install

Use uv from the repository root:

```powershell
uv sync
```

Then run:

```powershell
uv run main.py
```

If you do not use uv, install the dependencies from `pyproject.toml` into a Python environment and run:

```powershell
python main.py
```

## Main Outputs

The classic exporter writes to:

```text
take/
  exported/
    markers_world.c3d
    clapperboard.c3d
    eye_tracker_1.c3d
    eye_tracker_2.c3d
    calibration_markers.c3d  # only for takes inside a calibration folder
    actors/
      <actor>_.c3d
      <actor>_.fbx
      <actor>_.bvh
      <actor>_.mcp
```

The eye tracker and calibration free-marker exports are enabled with the
`Include eye tracker + calibration free markers` menu option. If an exported
take is missing only one eye tracker file, rerunning the export with this option
generates just the missing extra file.

BVH export is still attempted by default. If Shogun rejects a classical
no-fingers character with the known `multiple zero dof end bones` BVH error, the
exporter first retries with a static-hand BVH fallback that enables hand/finger
rotation DOFs before saving BVH. If Shogun still rejects the skeleton, it retries
without only the BVH save step, leaving C3D, FBX, and MCP exports intact.
Production 10-finger characters should keep producing BVH as before.

The aLigner-compatible exporter writes to a separate folder:

```text
take/
  aligned_exports/
    actors/
      <actor>_aligned.c3d
      <actor>_aligned.fbx
      <actor>_aligned.bvh
      <actor>_aligned.mcp
    retargeted/
      metahuman/
        <actor>_metahuman_aligned.fbx
      geeno/
        <actor>_geeno_aligned.fbx
    reports/
      aligned_export_summary.yaml
    scripts/
      aligned_export_all_actors.hsl
      aligned_retarget_metahuman.hsl
      aligned_retarget_geeno.hsl
```

Choose **Keep existing exports** (the default) or **Overwrite selected exports**
in the menu. Keep skips an aligned output group if its directory already contains
files: standard actors, MetaHuman, and Geeno are separate groups. It does not fill
partial groups; choose Overwrite to regenerate them. Standalone retargets also
skip existing exports for their selected target in Keep mode. Classic export
keeps its existing skip behavior and can still add missing tracking props.
Overwrite reruns selected exports without deleting the classic export folder or
unrelated retargets. The aligned workflow writes only to `aligned_exports/`;
the `exported/` and aLigner metadata folders are left untouched by that workflow.

## aLigner Workflow

After the classic export and an aLigner run, each take should contain:

```text
take/
  exported/
  aligner._data/
    <take>.export.yaml
    <take>.state.yaml
```

Use the menu option:

```text
Standard aligned export (C3D, FBX, BVH, MCP)
Aligned MetaHuman retarget
Aligned Geeno retarget
```

That pass reads the aLigner `*.export.yaml`, finds the MOCAP actor entries under `exported/actors`, and uses the exported local start/end frame values to generate HSL with:

```hsl
playRange <start_frame> <end_frame>;
```

Select any combination. Standard export produces cropped actor files without
retargeting. MetaHuman and Geeno each retarget the take MCP over the aligned frame
range, so either can run independently of standard aligned export.

## Data Tree Normalization

Use `utils/normalize_data_tree.py` when an exported data folder needs safer,
more uniform names. The script is dry-run first: it writes a CSV/JSON plan and
an undo PowerShell script, checks for name collisions, and only renames files or
folders when `--apply` is passed.

The default rules are intentionally conservative:

- `DD-MM-YYYY` becomes `YYYY-MM-DD`.
- If a folder has both a date and a session label, the date moves first.
- `mocap` is removed from names.
- repeated underscores are collapsed to one underscore.
- `take1`, `take 1`, and `take_1` become `001`.
- official IDs such as `S021`, `S001-S003`, and `I04` are preserved.
- YAML file names are included by default, but non-YAML file names are left alone.

First produce and review the plan:

```powershell
uv run python utils/normalize_data_tree.py "D:\path\to\data"
```

If the plan looks correct, apply only the path renames:

```powershell
uv run python utils/normalize_data_tree.py "D:\path\to\data" --apply
```

To also update exact old names and relative paths inside `.yaml`/`.yml` files,
add `--rewrite-yaml`. YAML files are copied to `*.before-normalize.bak` before
their contents are changed.

```powershell
uv run python utils/normalize_data_tree.py "D:\path\to\data" --apply --rewrite-yaml
```

Only use `--include-files` after reviewing a dry-run plan carefully. It extends
the same naming rules to non-YAML file names, which can break external tools if
those files are referenced by generated metadata.

## Retarget Types

There are two mannequin-style retarget modes:

- `mannequin`: uses `models/basic_mannequin.vsr` with `hsl/retarget_general_template.hsl`. This is the simpler path. It selects each Shogun character, loads the VSR, retargets, selects the retargeting hierarchy, and exports FBX.
- `mannequin adjusted`: uses `models/adjusted_mannequin.vsr` with `hsl/retarget_mannequin_template_adjusted_for_metahuman.hsl`. It retargets once, moves forearm `Rz` twist from the forearm to the hand on both arms, runs `solve`, then retargets again. This is intended for the MetaHuman-adjusted setup, but because it touches the solve skeleton it is more fragile in Shogun.

Geeno retargeting uses `models/geeno.vsr` with the general retarget template.

Vicon's [automated MetaHuman setup documentation](https://vicon-help.atlassian.net/wiki/spaces/ShogunPost121/pages/1253738008/Automate+retargeting+to+MetaHuman)
describes preparing a retarget setup using `SetupRetargetToUE5Mannequin.hsl`.
It requires one solved standard Shogun VSS subject and a UE5 MetaHuman or
Mannequin FBX with the `Character/Retargeting/[Locator]/root/pelvis` hierarchy
(Mannequin from UE 5.0.3 or later). Prepare and validate that setup in Shogun
before saving the VSR used for the existing batch exporters. The separate
Vicon automatic exporter below imports the FBX and creates a fresh setup itself.

## Vicon Automatic MetaHuman Export

The existing tutorial-based adjusted exporter and existing aligned VSR exporter
remain available. The new **Full-take MetaHuman retarget (Vicon automatic setup)**
and **Aligned MetaHuman retarget (Vicon automatic setup)** options follow the
supplied-script method in the Shogun Post 1.21 documentation:

1. Run Classic Export to produce one solved actor MCP per subject.
2. Use **Choose UE5 Target FBX** to select a MetaHuman or UE5.0.3+ Mannequin FBX.
   The default is `models/retarget_original_mannequin.fbx`; verify that your chosen
   FBX meets the documented hierarchy and scale requirements before batch use.
3. Select the new full-take and/or aligned Vicon option. Aligned export also
   requires the aLigner export YAML and its referenced actor MCPs.
4. Choose Keep or Overwrite and run.

Each actor is loaded in a separate Shogun CL process. Actor MCP selected saves
can still contain multiple subjects, so the generated HSL first isolates the
subject matching the actor filename prefix (for example `Jam` matches `James`).
Ambiguous or missing matches abort instead of exporting another actor. Other
subjects are removed only from the in-memory scene; source MCPs are not modified.
When an actor MCP is unavailable, the exporter can use `processed.mcp` or the
original take MCP and isolate the same actor. Actor names can be discovered from
the existing standard BVH, C3D, or FBX files.

Aligned YAML source paths are resolved against the selected take's
`exported/actors/` directory, allowing exports to move between PCs, drive letters,
and operating systems without editing the YAML.

The generated HSL imports
the target into the current subject's Retargeting setup, registers the installed
`Scripts/Retargeting` directory, calls `SetupRetargetToUE5Mannequin`, retargets,
and saves only the target hierarchy to FBX. The installed main script handles
the DOFs, poses, MetaHuman extra bones, and finger setup. The legacy tutorial's
forearm/hand DOF edits and additional solve pass are not added to this workflow.
Aligned output uses each actor's own start/end frames from aLigner.

New outputs are isolated from the existing exporters:

```text
take/exported/retargeted/metahuman_vicon/<actor>_metahuman_vicon.fbx
take/aligned_exports/retargeted/metahuman_vicon/<actor>_metahuman_vicon_aligned.fbx
```

Standalone saved-VSR retargets now also have separate output folders:

```text
take/exported/retargeted/metahuman_legacy/  # adjusted, older tutorial method
take/exported/retargeted/metahuman_vsr/     # basic mannequin VSR method
take/exported/retargeted/metahuman_vicon/   # new official automatic setup method
take/exported/retargeted/geeno/
```

Existing exports in `exported/actors/` are left in place. Rerun a selected
retarget to populate its new directory. Aligned outputs keep the existing
`aligned_exports/retargeted/metahuman/` and `geeno/` folders alongside the new
`metahuman_vicon/` folder.

Generated scripts are saved in `exported/scripts/` or `aligned_exports/scripts/`.
For these new exports, Keep skips individual existing actor FBXs, so missing
actors can still be exported. Overwrite replaces an actor's FBX only after a new
FBX is produced successfully.

`METAHUMAN_VICON_TARGET_FBX` sets the default target in
`configuration/settings.py`. `METAHUMAN_VICON_SCRIPTS_DIR = None` locates Vicon's
scripts beside the resolved Shogun executable; set it explicitly for a custom
installation. Use the scripts supplied with your current Shogun version,
including their helper scripts. The exporter does not automatically rescale the
FBX: prepare an appropriately scaled target and validate motion on one take
in Shogun before exporting a batch. Actual Shogun/animation validation is still
required; the automated tests cover HSL generation and batch behavior.

The aligned `metahuman` output intentionally uses the basic mannequin retarget path because it is less invasive and has been the more reliable Shogun CL path. The adjusted MetaHuman template is still available from the separate menu option, but it touches the solve skeleton and may fail with Shogun script errors around `setProperty -onMod`.

## Generated HSL Files

The app writes aligned workflow HSL files into the aligned export folder so they can be inspected and run manually:

```text
take/
  aligned_exports/
    scripts/
      aligned_export_all_actors.hsl
      aligned_retarget_metahuman.hsl
      aligned_retarget_geeno.hsl
```

Shogun Post CL does not always surface detailed script context, so these generated files are the best place to inspect exact line numbers after an error.

## Project Layout

```text
vicon_exporter/
  bvh/
  configuration/
  exporter/
  hsl/
  models/
  ui/
  utils/
  wrapper/
  main.py
  pyproject.toml
  uv.lock
```
