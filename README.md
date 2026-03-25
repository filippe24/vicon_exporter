             vicon exporter
          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
               ▓▓▓▓▓▓▓▓▓▓▓▓
             ▓▓▓ ▓▓▓▓▓▓▓▓▓▓
                     ▓▓▓▓▓▓
### vicon exporter.
a lightweight, terminal-based, python tool for processing Vicon Shogun takes (`.mcp`) and export them in a predefined manner. 

**important: this code requires an installation of Shogun Post with Shogun Post CL.** The path is hardcoded inside

functionalities:
- it runs ShogunPostCL with **live streaming output**.
- it generates `.hsl` (vicon shogun proprietary script language) files for each take.
- it exports `.fbx`, `.bvh`, `.c3d` files from `.mcp`.
- it provides live feedback and automatic folders detections.
This tool is ideal for motion capture pipelines where multiple takes must be processed quickly and consistently.

The intended output can be edited from the base `hsl` template and `shogun_runner.py`.

### install and use.
first install dependencies using `requirements.txt` or using `uv` using `uv sync`.
Then to run the code use the command `uv run main.py` or `python main.py`.
First you will be prompted to select a folder





---




### folder structure.
it supports flexible folder layouts:
```
exporter/
 ├── main.py
 ├── exporter/
 │     ├── export_pipeline.py
 │     └── ...
 ├── wrapper/
 │     └── shogun_runner.py
 ├── README.md
 └── pyproject.toml
```