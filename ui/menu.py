# gui_menu.py

from pathlib import Path
from tkinter import Button, Checkbutton, IntVar, Label, Radiobutton, Tk, filedialog

from configuration.settings import METAHUMAN_VICON_TARGET_FBX


class UserSelection:
    def __init__(self):
        self.folder: Path | None = None
        self.run_export: bool = False
        self.include_tracking_props: bool = False
        self.run_mannequin_retarget: bool = False
        self.run_mannequin_adjusted_retarget: bool = False
        self.run_geeno_retarget: bool = False
        self.run_aligned_export: bool = False
        self.run_aligned_metahuman: bool = False
        self.run_aligned_metahuman_vicon: bool = False
        self.run_metahuman_vicon: bool = False
        self.metahuman_vicon_target_fbx: Path = METAHUMAN_VICON_TARGET_FBX
        self.run_aligned_geeno: bool = False
        self.overwrite: bool = False
        self.run_convert_bvh: bool = False
        self.run_rename_face_videos: bool = False


def open_menu():
    selection = UserSelection()

    root = Tk()
    root.title("Vicon Exporter")

    Label(root, text="Select operations to run:", font=("Arial", 12, "bold")).pack(
        pady=10
    )

    export_var = IntVar()
    tracking_props_var = IntVar()
    mannequin_var = IntVar()
    mannequin_adjusted_var = IntVar()
    geeno_var = IntVar()
    aligned_var = IntVar()
    aligned_metahuman_var = IntVar()
    aligned_metahuman_vicon_var = IntVar()
    metahuman_vicon_var = IntVar()
    aligned_geeno_var = IntVar()
    overwrite_var = IntVar(value=0)
    convert_var = IntVar()
    rename_var = IntVar()

    Label(root, text="Export", font=("Arial", 10, "bold")).pack(anchor="w", pady=(6, 0))
    Checkbutton(root, text="Run Classic Export", variable=export_var).pack(anchor="w")
    Checkbutton(
        root,
        text="Include eye tracker + calibration free markers",
        variable=tracking_props_var,
    ).pack(anchor="w")

    Label(root, text="Aligned workflow", font=("Arial", 10, "bold")).pack(
        anchor="w", pady=(10, 0)
    )
    Checkbutton(
        root,
        text="Standard aligned export (C3D, FBX, BVH, MCP)",
        variable=aligned_var,
    ).pack(anchor="w")
    Checkbutton(
        root,
        text="Aligned MetaHuman retarget (existing VSR)",
        variable=aligned_metahuman_var,
    ).pack(anchor="w")
    Checkbutton(
        root,
        text="Aligned MetaHuman retarget (Vicon automatic setup)",
        variable=aligned_metahuman_vicon_var,
    ).pack(anchor="w")
    Checkbutton(root, text="Aligned Geeno retarget", variable=aligned_geeno_var).pack(
        anchor="w"
    )

    Label(
        root, text="Vicon automatic MetaHuman setup", font=("Arial", 10, "bold")
    ).pack(anchor="w", pady=(10, 0))
    Checkbutton(
        root,
        text="Full-take MetaHuman retarget (Vicon automatic setup)",
        variable=metahuman_vicon_var,
    ).pack(anchor="w")
    target_label = Label(
        root, text=f"UE5 target FBX: {selection.metahuman_vicon_target_fbx}"
    )
    target_label.pack(anchor="w")

    def choose_target():
        target = filedialog.askopenfilename(
            title="Select UE5 Mannequin or MetaHuman target",
            filetypes=[("FBX skeleton", "*.fbx")],
        )
        if target:
            selection.metahuman_vicon_target_fbx = Path(target)
            target_label.config(text=f"UE5 target FBX: {target}")

    Button(root, text="Choose UE5 Target FBX", command=choose_target).pack(anchor="w")

    Label(root, text="Existing exports", font=("Arial", 10, "bold")).pack(
        anchor="w", pady=(10, 0)
    )
    Radiobutton(
        root,
        text="Keep existing exports (skip existing output groups)",
        variable=overwrite_var,
        value=0,
    ).pack(anchor="w")
    Radiobutton(
        root, text="Overwrite selected exports", variable=overwrite_var, value=1
    ).pack(anchor="w")

    Label(root, text="Legacy standalone retargets", font=("Arial", 10, "bold")).pack(
        anchor="w", pady=(10, 0)
    )
    Checkbutton(root, text="Run Mannequin Retarget", variable=mannequin_var).pack(
        anchor="w"
    )
    Checkbutton(
        root,
        text="Run MetaHuman Adjusted Retarget (legacy tutorial)",
        variable=mannequin_adjusted_var,
    ).pack(anchor="w")
    Checkbutton(root, text="Run Geeno Retarget", variable=geeno_var).pack(anchor="w")

    Label(root, text="Utilities", font=("Arial", 10, "bold")).pack(
        anchor="w", pady=(10, 0)
    )
    Checkbutton(root, text="Convert BVH Rotations", variable=convert_var).pack(
        anchor="w"
    )
    Checkbutton(root, text="Run Renaming", variable=rename_var).pack(anchor="w")

    def choose_folder():
        folder = filedialog.askdirectory(title="Select take folder")
        if folder:
            selection.folder = Path(folder)
            folder_label.config(text=f"Selected: {folder}")

    Button(root, text="Choose Take Folder", command=choose_folder).pack(pady=10)
    folder_label = Label(root, text="No folder selected")
    folder_label.pack()

    def confirm():
        selection.run_export = bool(export_var.get())
        selection.include_tracking_props = bool(tracking_props_var.get())
        selection.run_mannequin_retarget = bool(mannequin_var.get())
        selection.run_mannequin_adjusted_retarget = bool(mannequin_adjusted_var.get())
        selection.run_geeno_retarget = bool(geeno_var.get())
        selection.run_aligned_export = bool(aligned_var.get())
        selection.run_aligned_metahuman = bool(aligned_metahuman_var.get())
        selection.run_aligned_metahuman_vicon = bool(aligned_metahuman_vicon_var.get())
        selection.run_metahuman_vicon = bool(metahuman_vicon_var.get())
        selection.run_aligned_geeno = bool(aligned_geeno_var.get())
        selection.overwrite = bool(overwrite_var.get())
        selection.run_convert_bvh = bool(convert_var.get())
        selection.run_rename_face_videos = bool(rename_var.get())
        root.destroy()

    Button(root, text="Run", command=confirm, bg="#4CAF50", fg="white").pack(pady=20)

    root.mainloop()
    return selection
