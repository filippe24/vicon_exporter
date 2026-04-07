# gui_menu.py

from tkinter import Tk, Label, Button, Checkbutton, IntVar, filedialog
from pathlib import Path

class UserSelection:
    def __init__(self):
        self.folder = None
        self.run_export = False
        self.run_retarget = False
        self.run_convert_bvh = False


def open_menu():
    selection = UserSelection()

    root = Tk()
    root.title("Vicon Exporter")

    Label(root, text="Select operations to run:", font=("Arial", 12, "bold")).pack(pady=10)

    export_var = IntVar()
    retarget_var = IntVar()
    convert_var = IntVar()

    Checkbutton(root, text="Run Export", variable=export_var).pack(anchor="w")
    Checkbutton(root, text="Run Retarget", variable=retarget_var).pack(anchor="w")
    Checkbutton(root, text="Convert BVH Rotations", variable=convert_var).pack(anchor="w")

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
        selection.run_retarget = bool(retarget_var.get())
        selection.run_convert_bvh = bool(convert_var.get())
        root.destroy()

    Button(root, text="Run", command=confirm, bg="#4CAF50", fg="white").pack(pady=20)

    root.mainloop()
    return selection
