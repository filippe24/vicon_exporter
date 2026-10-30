"""Overview of what each take has exported and what needs a new export.

The table only reads files. "Export selected…" runs main.py on the chosen takes
in its own console, then refreshes their status.
"""

import csv
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox, ttk

from exporter.export_status import (
    CURRENT,
    MISSING_OUTPUTS,
    NO_ALIGNMENT,
    NOT_APPLICABLE,
    NOT_EXPORTED,
    OUTDATED,
    STEPS,
    UNVERIFIED,
    TakeStatus,
    take_status,
)
from utils.file_search import find_take_folders

MAIN_SCRIPT = Path(__file__).resolve().parent.parent / "main.py"
SYMBOLS = {
    CURRENT: "✓",
    OUTDATED: "⚠ outdated",
    MISSING_OUTPUTS: "✗ files missing",
    UNVERIFIED: "?",
    NOT_EXPORTED: "–",
    NOT_APPLICABLE: "",
    NO_ALIGNMENT: "",
}
FILTERS = ("All takes", "Needs a new export", "Not fully exported", "No aLigner export")
LEGEND = (
    "✓ matches the current aLigner export · ⚠ the aLigner values changed: export again with "
    "Overwrite · ✗ recorded files missing · ? exported before status tracking, not verified · "
    "– not exported. aLigner exported: when aLigner last wrote its export YAML; ⚠ there means the "
    "alignment was saved later without exporting, so export again from aLigner first."
)
NEEDS_EXPORT = (OUTDATED, MISSING_OUTPUTS)


def _date(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


class StatusBrowser:
    def __init__(self, root: Tk, folder: Path | None):
        self.root = root
        self.folder = folder
        self.takes: list[TakeStatus] = []
        self.results: queue.Queue = queue.Queue()
        self.scan_id = 0
        self.total: int | None = None
        self.export: subprocess.Popen | None = None
        self.exporting: list[Path] = []
        root.title("Vicon Exporter · Export status")
        root.minsize(1100, 640)

        top = ttk.Frame(root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        self.folder_text = StringVar(value=str(folder) if folder else "Choose a dataset or take folder")
        ttk.Button(top, text="Choose folder…", command=self.choose).pack(side="left")
        ttk.Button(top, text="Rescan", command=self.scan).pack(side="left", padx=6)
        ttk.Label(top, textvariable=self.folder_text).pack(side="left", padx=6)
        ttk.Button(top, text="Save CSV…", command=self.save_csv).pack(side="right")
        self.filter = ttk.Combobox(top, values=FILTERS, state="readonly", width=22)
        self.filter.current(0)
        self.filter.bind("<<ComboboxSelected>>", lambda _event: self.fill())
        self.filter.pack(side="right", padx=6)

        self.summary = StringVar()
        ttk.Label(root, textvariable=self.summary, padding=(10, 0)).pack(fill="x")
        ttk.Label(root, text=LEGEND, foreground="#666666", wraplength=1080, padding=(10, 2)).pack(fill="x")

        actions = ttk.Frame(root, padding=(10, 4, 10, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Select all shown", command=self.select_all).pack(side="left")
        self.export_button = ttk.Button(actions, text="Export selected…", command=self.export_selected)
        self.export_button.pack(side="left", padx=6)
        self.selection_text = StringVar(value="Select takes (Ctrl/Shift+click) to export them.")
        ttk.Label(actions, textvariable=self.selection_text).pack(side="left", padx=6)

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        table = ttk.Frame(panes)
        columns = ["aligner"] + [step.key for step in STEPS]
        self.tree = ttk.Treeview(table, columns=columns, selectmode="extended")
        self.tree.heading("#0", text="Take")
        self.tree.column("#0", width=280, stretch=True)
        self.tree.heading("aligner", text="aLigner exported")
        self.tree.column("aligner", width=130, stretch=False)
        for step in STEPS:
            self.tree.heading(step.key, text=step.label)
            self.tree.column(step.key, width=100, anchor="center", stretch=False)
        self.tree.tag_configure("outdated", background="#fbe9c6")
        self.tree.tag_configure("missing", background="#f6d0d0")
        self.tree.tag_configure("none", foreground="#888888")
        self.tree.tag_configure("running", background="#d6e6fb")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_detail())
        panes.add(table, weight=3)

        detail = ttk.Frame(panes)
        self.detail = ttk.Treeview(detail, columns=("state", "when", "detail"), show="tree headings")
        self.detail.heading("#0", text="Step")
        self.detail.heading("state", text="State")
        self.detail.heading("when", text="Exported")
        self.detail.heading("detail", text="Details")
        self.detail.column("#0", width=160, stretch=False)
        self.detail.column("state", width=120, stretch=False)
        self.detail.column("when", width=150, stretch=False)
        self.detail.column("detail", width=560, stretch=True)
        self.detail.pack(fill="both", expand=True)
        panes.add(detail, weight=2)

        if folder:
            root.after(50, self.scan)

    def choose(self):
        folder = filedialog.askdirectory(title="Select dataset or take folder")
        if folder:
            self.folder = Path(folder)
            self.folder_text.set(folder)
            self.scan()

    def scan(self, only: list[Path] | None = None):
        """Rescan everything, or refresh only the given takes in place."""
        if self.folder is None:
            return
        self.scan_id += 1
        if only is None:
            self.takes = []
            self.total = None
            self.fill()
            self.summary.set("Looking for takes…")
        threading.Thread(target=self._scan, args=(self.scan_id, self.folder, only), daemon=True).start()
        self.root.after(100, self._collect)

    def _scan(self, scan_id: int, folder: Path, only: list[Path] | None):
        takes = find_take_folders(folder) if only is None else only
        if only is None:
            self.results.put((scan_id, "count", len(takes)))
        for take in takes:
            try:
                self.results.put((scan_id, "take", take_status(take)))
            except Exception as error:  # one unreadable take must not stop the scan
                self.results.put((scan_id, "take", TakeStatus(take, error=str(error))))
        self.results.put((scan_id, "done", None))

    def _collect(self):
        done = False
        changed = False
        while not self.results.empty():
            scan_id, kind, value = self.results.get()
            if scan_id != self.scan_id:
                continue
            if kind == "count":
                self.total = value
            elif kind == "take":
                index = next((i for i, take in enumerate(self.takes) if take.take_dir == value.take_dir), None)
                if index is None:
                    self.takes.append(value)
                else:
                    self.takes[index] = value
                changed = True
            else:
                done = True
        if changed or done:
            self.fill()
        if not done:
            if self.total is not None:
                self.summary.set(f"Scanning {len(self.takes)}/{self.total} takes…")
            self.root.after(150, self._collect)

    def visible(self) -> list[TakeStatus]:
        mode = self.filter.get()
        if mode == FILTERS[1]:
            return [take for take in self.takes if take.outdated]
        if mode == FILTERS[2]:
            return [
                take for take in self.takes
                if take.aligner_yaml and any(step.state in (NOT_EXPORTED, *NEEDS_EXPORT)
                                             for step in take.steps.values())
            ]
        if mode == FILTERS[3]:
            return [take for take in self.takes if take.aligner_yaml is None]
        return self.takes

    def fill(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        running = set(self.exporting) if self.export is not None else set()
        for take in self.visible():
            if take.aligner_yaml:
                aligner = _date(take.aligner_exported_at) + (" ⚠" if take.aligner_export_stale else "")
            else:
                aligner = "none"
            values = [aligner] + [
                SYMBOLS[take.steps[step.key].state] if step.key in take.steps else "" for step in STEPS
            ]
            tags = (
                ("running",) if take.take_dir in running
                else ("missing",) if take.error
                else ("outdated",) if take.outdated
                else () if take.aligner_yaml else ("none",)
            )
            self.tree.insert("", "end", iid=str(take.take_dir), text=self._label(take), values=values, tags=tags)
        self.tree.selection_set([iid for iid in selected if self.tree.exists(iid)])
        if self.export is not None:
            return
        outdated = sum(bool(take.outdated) for take in self.takes)
        aligned = sum(take.aligner_yaml is not None for take in self.takes)
        complete = sum(
            bool(take.aligner_yaml and take.exported)
            and all(take.steps[key].state == CURRENT for key in take.exported)
            for take in self.takes
        )
        unverified = sum(
            not take.outdated and any(step.state == UNVERIFIED for step in take.steps.values())
            for take in self.takes
        )
        self.summary.set(
            f"{len(self.takes)} takes · {aligned} with an aLigner export · {complete} exported and current · "
            f"{outdated} need a new export · {unverified} exported before tracking, not verified"
        )

    def _label(self, take: TakeStatus) -> str:
        try:
            return take.take_dir.relative_to(self.folder).as_posix() or take.take_dir.name
        except (TypeError, ValueError):
            return str(take.take_dir)

    def selected_takes(self) -> list[TakeStatus]:
        chosen = set(self.tree.selection())
        return [take for take in self.takes if str(take.take_dir) in chosen]

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def show_detail(self):
        self.detail.delete(*self.detail.get_children())
        chosen = self.selected_takes()
        self.selection_text.set(
            f"{len(chosen)} takes selected." if chosen else "Select takes (Ctrl/Shift+click) to export them."
        )
        if len(chosen) != 1:
            return
        take = chosen[0]
        if take.error:
            self.detail.insert("", "end", text="Error", values=("", "", take.error))
        if take.aligner_yaml:
            source = f"{take.aligner_yaml.relative_to(take.take_dir).as_posix()} ({take.aligner_format or 'no format version'})"
            self.detail.insert("", "end", text="aLigner export", values=("", _date(take.aligner_exported_at), source))
            saved = "alignment saved after the last aLigner export: export again from aLigner first" \
                if take.aligner_export_stale else "alignment state"
            if take.aligner_saved_at:
                self.detail.insert("", "end", text="aLigner saved", values=("", _date(take.aligner_saved_at), saved))
        else:
            self.detail.insert("", "end", text="aLigner export", values=("", "", "no aLigner export YAML in this take"))
        for step in STEPS:
            status = take.steps.get(step.key)
            if status is None or status.state == NOT_APPLICABLE:
                continue
            record = status.record or {}
            parts = [status.note] if status.note else []
            if status.outputs:
                parts.append(f"{len(status.outputs)} files")
            if record.get("crop_policy"):
                parts.append(f"crop: {record['crop_policy']}")
            item = self.detail.insert(
                "", "end", text=step.label, open=True,
                values=(status.state, str(record.get("exported_at", ""))[:16].replace("T", " "), " · ".join(parts)),
            )
            for change in status.changes:
                self.detail.insert(item, "end", text="", values=("", "", change))

    def export_selected(self):
        if self.export is not None:
            messagebox.showinfo("Export running", "Wait for the running export to finish.", parent=self.root)
            return
        takes = [take for take in self.selected_takes() if take.aligner_yaml]
        if not takes:
            messagebox.showinfo(
                "Choose takes", "Select takes with an aLigner export first.", parent=self.root
            )
            return
        ExportDialog(self.root, takes, self.run_export)

    def run_export(self, takes: list[TakeStatus], steps: list[str], overwrite: bool, crop: str):
        arguments = [sys.executable, str(MAIN_SCRIPT), "--steps", ",".join(steps), "--prop-crop", crop]
        if overwrite:
            arguments.append("--overwrite")
        for take in takes:
            arguments += ["--take", str(take.take_dir)]
        if sys.platform == "win32":
            # Own console showing Shogun's output; it stays open until a key is pressed.
            # /s strips only the outer quotes, so quoted paths with spaces survive.
            command = f'cmd /s /c "{subprocess.list2cmdline(arguments)} & pause"'
            self.export = subprocess.Popen(
                command, cwd=MAIN_SCRIPT.parent, creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            self.export = subprocess.Popen(arguments, cwd=MAIN_SCRIPT.parent)
        self.exporting = [take.take_dir for take in takes]
        self.export_button.configure(state="disabled")
        self.summary.set(
            f"Exporting {len(takes)} takes ({', '.join(steps)}) in a separate console. "
            "Their status refreshes when it closes."
        )
        self.fill()
        self.root.after(2000, self._watch_export)

    def _watch_export(self):
        if self.export is None:
            return
        if self.export.poll() is None:
            self.root.after(2000, self._watch_export)
            return
        self.export = None
        self.export_button.configure(state="normal")
        self.scan(only=self.exporting)

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["take", "aligner_exported_at", "aligner_saved_at",
                             *[step.key for step in STEPS]])
            for take in self.takes:
                writer.writerow([
                    self._label(take),
                    _date(take.aligner_exported_at),
                    _date(take.aligner_saved_at),
                    *[take.steps[step.key].state if step.key in take.steps else "" for step in STEPS],
                ])


class ExportDialog:
    """Choose steps for the selected takes; steps needing a new export are preselected."""

    def __init__(self, parent: Tk, takes: list[TakeStatus], run):
        self.takes = takes
        self.run = run
        self.window = Toplevel(parent)
        self.window.title("Export selected takes")
        self.window.transient(parent)
        self.window.grab_set()
        body = ttk.Frame(self.window, padding=14)
        body.pack(fill="both", expand=True)
        stale = sum(take.aligner_export_stale for take in takes)
        ttk.Label(body, text=f"{len(takes)} takes", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        if stale:
            ttk.Label(
                body, foreground="#a06000", wraplength=420,
                text=f"⚠ {stale} of them have an alignment saved after the last aLigner export; "
                     "their aLigner YAML may hold older values.",
            ).pack(anchor="w", pady=(4, 0))
        steps = ttk.LabelFrame(body, text="Aligned steps", padding=10)
        steps.pack(fill="x", pady=10)
        self.choices: dict[str, BooleanVar] = {}
        for step in STEPS:
            states = [take.steps[step.key].state for take in takes if step.key in take.steps]
            needing = sum(state in NEEDS_EXPORT for state in states)
            missing = sum(state == NOT_EXPORTED for state in states)
            if all(state == NOT_APPLICABLE for state in states):
                continue
            variable = BooleanVar(value=needing > 0)
            self.choices[step.key] = variable
            counts = ", ".join(part for part in (
                f"{needing} outdated" if needing else "",
                f"{missing} not exported" if missing else "",
            ) if part)
            ttk.Checkbutton(
                steps, text=step.label + (f"  ({counts})" if counts else ""), variable=variable
            ).pack(anchor="w")
        self.overwrite = BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="Overwrite existing outputs (needed to refresh outdated ones)", variable=self.overwrite
        ).pack(anchor="w")
        crop = ttk.Frame(body)
        crop.pack(fill="x", pady=(8, 0))
        ttk.Label(crop, text="Prop crop range").pack(side="left")
        self.crop = ttk.Combobox(crop, state="readonly", values=("first", "extremes"), width=12)
        self.crop.current(0)
        self.crop.pack(side="left", padx=6)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Run export", command=self.confirm).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="right", padx=6)

    def confirm(self):
        steps = [key for key, variable in self.choices.items() if variable.get()]
        if not steps:
            messagebox.showinfo("Choose steps", "Select at least one step.", parent=self.window)
            return
        self.window.destroy()
        self.run(self.takes, steps, self.overwrite.get(), self.crop.get())


def open_status_browser(folder: Path | None = None):
    root = Tk()
    StatusBrowser(root, folder)
    root.mainloop()
