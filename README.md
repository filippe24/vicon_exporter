![logo](images/logo.png)

a lightweight, terminal-based, python tool for processing Vicon Shogun takes (`.mcp`) and export them in a predefined manner. 

**important: this code requires an installation of Shogun Post with Shogun Post CL.** The path to ShogunPostCL can be set inside `configuration/settings.py`.

functionalities:
- it runs ShogunPostCL with **live streaming output**.
- it generates `.hsl` (vicon shogun proprietary script language) files for each take.
- it exports `.fbx`, `.bvh`, `.c3d` files from `.mcp`.
- it provides live feedback and automatic folders detections.
This tool is ideal for motion capture pipelines where multiple takes must be processed quickly and consistently.

The intended output can be edited from the base `hsl` template and `shogun_runner.py`.

### install and use.
first install dependencies using `requirements.txt` or using `uv` using `uv sync`.
be sure that `Vicon's Shogun Post` (we have used version 1.18) is installed. identify the path to `ShogunPostCL.exe` and set it on `confogiration/settings.py`.

---

to run the code use the command `uv run main.py` or `python main.py`.
First you will be prompted to select a folder. The code automatically identify all the folder containing `.mcp` files recursively (it assume one .mcp per folder) and it start exporting automatically.


### folder structure.

```
exporter/
 ├── configuration/
 │     └── settings.py
 ├── exporter/
 │     ├── export_pipeline.py
 │     └── ...
 ├── wrapper/
 │     └── shogun_runner.py
 ├── main.py
 ├── requirements.txt
 └── pyproject.toml
```

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![uv](https://img.shields.io/badge/uv-powered-orange.svg)
![Platform](https://img.shields.io/badge/platform-windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

      vicon exporter
      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
      ▓▓▓▓▓▓▓▓▓▓▓▓
      ▓▓▓ ▓▓▓▓▓▓▓▓▓▓
      ▓█▓▓▓▓▓