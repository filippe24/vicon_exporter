# gui_menu.py

from pathlib import Path
from tkinter import Button, Checkbutton, IntVar, Label, Tk, filedialog


class UserSelection:
    def __init__(self):
        self.folder: Path | None = None
        self.run_export: bool = False
        self.run_mannequin_retarget: bool = False
        self.run_mannequin_adjusted_retarget: bool = False
        self.run_geeno_retarget: bool = False
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
    mannequin_var = IntVar()
    mannequin_adjusted_var = IntVar()
    geeno_var = IntVar()
    convert_var = IntVar()
    rename_var = IntVar()

    Checkbutton(root, text="Run Export", variable=export_var).pack(anchor="w")
    Checkbutton(root, text="Run Mannequin Retarget", variable=mannequin_var).pack(
        anchor="w"
    )
    Checkbutton(
        root, text="Run Mannequin Adjusted Retarget", variable=mannequin_adjusted_var
    ).pack(anchor="w")
    Checkbutton(root, text="Run Geeno Retarget", variable=geeno_var).pack(anchor="w")
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
        selection.run_mannequin_retarget = bool(mannequin_var.get())
        selection.run_mannequin_adjusted_retarget = bool(mannequin_adjusted_var.get())
        selection.run_geeno_retarget = bool(geeno_var.get())
        selection.run_convert_bvh = bool(convert_var.get())
        selection.run_rename_face_videos = bool(rename_var.get())
        root.destroy()

    Button(root, text="Run", command=confirm, bg="#4CAF50", fg="white").pack(pady=20)

    root.mainloop()
    return selection
