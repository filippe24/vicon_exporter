from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk

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
        self.run_aligned_props: bool = False
        self.run_aligned_combined_props: bool = False
        self.run_aligned_calibration_markers: bool = False
        self.prop_crop_policy: str = "first"
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
    root.minsize(820, 760)
    style = ttk.Style(root)
    style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
    style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Hint.TLabel", foreground="#555555")

    body = ttk.Frame(root, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Vicon Exporter", style="Title.TLabel").pack(anchor="w")
    ttk.Label(
        body, text="Choose your takes, select outputs, then run.", style="Hint.TLabel"
    ).pack(anchor="w", pady=(2, 12))

    folder_text = StringVar(
        value="Choose a take folder or a parent folder to process a batch"
    )
    source = ttk.LabelFrame(body, text="1. Take folder", padding=10)
    source.pack(fill="x", pady=(0, 12))

    def choose_folder():
        folder = filedialog.askdirectory(
            title="Select take folder or batch parent folder"
        )
        if folder:
            selection.folder = Path(folder)
            folder_text.set(folder)

    ttk.Button(source, text="Choose folder…", command=choose_folder).pack(
        side="right", padx=(10, 0)
    )
    ttk.Entry(source, textvariable=folder_text, state="readonly").pack(
        fill="x", expand=True
    )

    operation_names = (
        "run_export",
        "include_tracking_props",
        "run_mannequin_retarget",
        "run_mannequin_adjusted_retarget",
        "run_geeno_retarget",
        "run_aligned_export",
        "run_aligned_props",
        "run_aligned_combined_props",
        "run_aligned_calibration_markers",
        "run_aligned_metahuman",
        "run_aligned_metahuman_vicon",
        "run_metahuman_vicon",
        "run_aligned_geeno",
        "run_convert_bvh",
        "run_rename_face_videos",
    )
    variables = {name: BooleanVar(root, value=False) for name in operation_names}
    overwrite = BooleanVar(root, value=False)
    summary = StringVar()

    ttk.Label(body, text="2. Outputs and operations", style="Section.TLabel").pack(
        anchor="w", pady=(0, 6)
    )
    tabs = ttk.Notebook(body)
    tabs.pack(fill="both", expand=True)
    exports = ttk.Frame(tabs, padding=12)
    legacy = ttk.Frame(tabs, padding=12)
    utilities = ttk.Frame(tabs, padding=12)
    tabs.add(exports, text="Exports")
    tabs.add(legacy, text="Legacy methods")
    tabs.add(utilities, text="Utilities")

    def hint(parent, text, width=355):
        ttk.Label(
            parent, text=text, style="Hint.TLabel", wraplength=width, justify="left"
        ).pack(anchor="w", fill="x", pady=(2, 5))

    def check(parent, text, key, command=None):
        widget = ttk.Checkbutton(
            parent, text=text, variable=variables[key], command=command
        )
        widget.pack(anchor="w", pady=4)
        return widget

    columns = ttk.Frame(exports)
    columns.pack(fill="x")
    columns.columnconfigure(0, weight=1, uniform="workflows")
    columns.columnconfigure(1, weight=1, uniform="workflows")
    full = ttk.LabelFrame(columns, text="Full take", padding=10)
    full.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    aligned = ttk.LabelFrame(columns, text="Aligned take", padding=10)
    aligned.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    hint(
        full,
        "Export the full frame range. Standard export prepares actor files.",
    )

    def change_standard():
        if not variables["run_export"].get():
            variables["include_tracking_props"].set(False)

    def change_extras():
        if variables["include_tracking_props"].get():
            variables["run_export"].set(True)

    check(full, "Standard actor export", "run_export", change_standard)
    hint(full, "C3D, FBX, BVH and MCP → exported/actors/")
    extras = ttk.Frame(full, padding=(16, 0, 0, 0))
    extras.pack(fill="x")
    check(
        extras,
        "Include eye trackers + calibration markers",
        "include_tracking_props",
        change_extras,
    )
    hint(
        extras,
        "Selects Standard export. Keep adds missing extras. Free markers: calibration folders only.",
        320,
    )
    check(full, "MetaHuman · Vicon automatic setup", "run_metahuman_vicon")
    hint(full, "Uses the UE5 target FBX selected below.")
    check(full, "Geeno retarget", "run_geeno_retarget")

    hint(
        aligned,
        "Use the frame ranges saved by aLigner. Requires an export YAML in .aligner (older locations also supported).",
    )
    check(aligned, "Standard actor export", "run_aligned_export")
    hint(aligned, "C3D, FBX, BVH and MCP → aligned_exports/actors/")
    check(aligned, "Visible props · C3D", "run_aligned_props")
    hint(aligned, "Props with marker data in the crop → aligned_exports/props/")
    check(aligned, "All visible props in one C3D", "run_aligned_combined_props")
    check(
        aligned,
        "Unlabeled markers · calibration only",
        "run_aligned_calibration_markers",
    )
    hint(
        aligned,
        "Independent outputs; markers run only under folders containing ‘calibration’.",
    )
    prop_crop = StringVar(root, value="First C3D")
    ttk.Label(aligned, text="Prop crop range").pack(anchor="w")
    ttk.Combobox(
        aligned,
        textvariable=prop_crop,
        state="readonly",
        values=("First C3D", "Earliest start / latest end"),
    ).pack(anchor="w", fill="x")
    check(aligned, "MetaHuman · Vicon automatic setup", "run_aligned_metahuman_vicon")
    check(aligned, "Geeno retarget", "run_aligned_geeno")
    hint(
        aligned,
        "Choose either retarget independently, or combine with Standard export. Outputs → aligned_exports/retargeted/",
    )

    target = ttk.LabelFrame(
        exports, text="UE5 target · shared by both Vicon MetaHuman exports", padding=10
    )
    target.pack(fill="x", pady=(12, 0))
    target_text = StringVar(value=str(selection.metahuman_vicon_target_fbx))

    def choose_target():
        filename = filedialog.askopenfilename(
            title="Select UE5 Mannequin or MetaHuman FBX",
            filetypes=[("FBX skeleton", "*.fbx")],
        )
        if filename:
            selection.metahuman_vicon_target_fbx = Path(filename)
            target_text.set(filename)

    target_button = ttk.Button(target, text="Choose FBX…", command=choose_target)
    target_button.pack(side="right", padx=(10, 0))
    ttk.Entry(target, textvariable=target_text, state="readonly").pack(fill="x")

    ttk.Label(
        legacy,
        text="Existing methods for comparison and older projects",
        style="Section.TLabel",
    ).pack(anchor="w")
    hint(
        legacy,
        "These use saved retarget setups. They do not use the UE5 target FBX above. Select them only when you want the older method; they can run alongside the new exporter.",
        740,
    )
    old_full = ttk.LabelFrame(legacy, text="Full take · saved setups", padding=10)
    old_full.pack(fill="x", pady=(4, 10))
    check(
        old_full,
        "MetaHuman adjusted · older tutorial",
        "run_mannequin_adjusted_retarget",
    )
    hint(old_full, "Output → exported/retargeted/metahuman_legacy/", 700)
    check(old_full, "Mannequin / MetaHuman · basic saved VSR", "run_mannequin_retarget")
    hint(old_full, "Output → exported/retargeted/metahuman_vsr/", 700)
    old_aligned = ttk.LabelFrame(legacy, text="Aligned take · saved setup", padding=10)
    old_aligned.pack(fill="x")
    check(old_aligned, "MetaHuman · existing mannequin VSR", "run_aligned_metahuman")
    hint(
        old_aligned,
        "Requires aLigner YAML. Output → aligned_exports/retargeted/metahuman/",
        700,
    )

    hint(
        utilities,
        "Optional operations on the selected folder. Choose them separately from exports.",
        740,
    )
    check(utilities, "Convert BVH rotations", "run_convert_bvh")
    hint(utilities, "Creates *_converted.bvh files from existing BVHs.", 700)
    check(utilities, "Rename face videos", "run_rename_face_videos")
    hint(utilities, "Renames face-video files in the selected takes.", 700)

    policy = ttk.LabelFrame(body, text="3. Existing export files", padding=10)
    policy.pack(fill="x", pady=(12, 8))
    ttk.Radiobutton(
        policy, text="Keep existing exports", variable=overwrite, value=False
    ).pack(side="left")
    ttk.Radiobutton(
        policy, text="Overwrite selected exports", variable=overwrite, value=True
    ).pack(side="left", padx=20)
    ttk.Label(
        body,
        text="Keep skips existing output groups; Vicon MetaHuman keeps each actor FBX. This choice applies to exports.",
        style="Hint.TLabel",
        wraplength=780,
    ).pack(anchor="w")

    legacy_keys = (
        "run_mannequin_retarget",
        "run_mannequin_adjusted_retarget",
        "run_aligned_metahuman",
    )

    def update_summary(*_args):
        count = sum(
            variable.get()
            for key, variable in variables.items()
            if key != "include_tracking_props"
        )
        legacy_count = sum(variables[key].get() for key in legacy_keys)
        text = f"{count} operation{'s' if count != 1 else ''} selected"
        if legacy_count:
            text += f" · {legacy_count} legacy"
        summary.set(text)
        tabs.tab(
            legacy,
            text=f"Legacy methods ({legacy_count})"
            if legacy_count
            else "Legacy methods",
        )
        target_button.configure(
            state="normal"
            if variables["run_metahuman_vicon"].get()
            or variables["run_aligned_metahuman_vicon"].get()
            else "disabled"
        )

    for variable in variables.values():
        variable.trace_add("write", update_summary)
    update_summary()

    def confirm():
        if selection.folder is None or not selection.folder.is_dir():
            messagebox.showinfo(
                "Choose a folder",
                "Choose a take folder or a batch parent folder first.",
                parent=root,
            )
            return
        if not any(
            variable.get()
            for key, variable in variables.items()
            if key != "include_tracking_props"
        ):
            messagebox.showinfo(
                "Choose an operation",
                "Select at least one export or utility to run.",
                parent=root,
            )
            return
        for key, variable in variables.items():
            setattr(selection, key, variable.get())
        selection.overwrite = overwrite.get()
        selection.prop_crop_policy = (
            "first" if prop_crop.get() == "First C3D" else "extremes"
        )
        root.destroy()

    footer = ttk.Frame(body)
    footer.pack(fill="x", pady=(12, 0))
    ttk.Label(footer, textvariable=summary).pack(side="left")
    ttk.Button(footer, text="Run selected operations", command=confirm).pack(
        side="right"
    )
    root.mainloop()
    return selection
