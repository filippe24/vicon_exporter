"""Read-only overview of what each take has exported and what needs a new export."""

import csv
import queue
import threading
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, ttk

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
    "– not exported. Nothing here changes files."
)


class StatusBrowser:
    def __init__(self, root: Tk, folder: Path | None):
        self.root = root
        self.folder = folder
        self.takes: list[TakeStatus] = []
        self.results: queue.Queue = queue.Queue()
        self.scan_id = 0
        self.total: int | None = None
        root.title("Vicon Exporter · Export status")
        root.minsize(1000, 640)

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
        ttk.Label(root, text=LEGEND, foreground="#666666", wraplength=980, padding=(10, 2)).pack(fill="x")

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        table = ttk.Frame(panes)
        columns = ["aligner"] + [step.key for step in STEPS]
        self.tree = ttk.Treeview(table, columns=columns, selectmode="browse")
        self.tree.heading("#0", text="Take")
        self.tree.column("#0", width=280, stretch=True)
        self.tree.heading("aligner", text="aLigner export")
        self.tree.column("aligner", width=110, stretch=False)
        for step in STEPS:
            self.tree.heading(step.key, text=step.label)
            self.tree.column(step.key, width=105, anchor="center", stretch=False)
        self.tree.tag_configure("outdated", background="#fbe9c6")
        self.tree.tag_configure("missing", background="#f6d0d0")
        self.tree.tag_configure("none", foreground="#888888")
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

    def scan(self):
        if self.folder is None:
            return
        self.scan_id += 1
        self.takes = []
        self.total = None
        self.fill()
        self.summary.set("Looking for takes…")
        threading.Thread(target=self._scan, args=(self.scan_id, self.folder), daemon=True).start()
        self.root.after(100, self._collect)

    def _scan(self, scan_id: int, folder: Path):
        takes = find_take_folders(folder)
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
                self.takes.append(value)
                changed = True
            else:
                done = True
        if changed:
            self.fill()
        if done:
            self.fill()
        else:
            self.summary.set(f"Scanning {len(self.takes)}/{self.total if self.total is not None else '?'} takes…")
            self.root.after(150, self._collect)

    def visible(self) -> list[TakeStatus]:
        mode = self.filter.get()
        if mode == FILTERS[1]:
            return [take for take in self.takes if take.outdated]
        if mode == FILTERS[2]:
            return [
                take for take in self.takes
                if take.aligner_yaml and any(step.state in (NOT_EXPORTED, OUTDATED, MISSING_OUTPUTS)
                                             for step in take.steps.values())
            ]
        if mode == FILTERS[3]:
            return [take for take in self.takes if take.aligner_yaml is None]
        return self.takes

    def fill(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for index, take in enumerate(self.visible()):
            values = ["✓ " + (take.aligner_format or "found") if take.aligner_yaml else "none"]
            values += [SYMBOLS[take.steps[step.key].state] if step.key in take.steps else "" for step in STEPS]
            tags = ("missing",) if take.error else ("outdated",) if take.outdated else () if take.aligner_yaml else ("none",)
            self.tree.insert("", "end", iid=str(index), text=self._label(take), values=values, tags=tags)
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
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

    def show_detail(self):
        self.detail.delete(*self.detail.get_children())
        selection = self.tree.selection()
        if not selection:
            return
        take = self.visible()[int(selection[0])]
        if take.error:
            self.detail.insert("", "end", text="Error", values=("", "", take.error))
        source = (
            f"{take.aligner_yaml.relative_to(take.take_dir).as_posix()} ({take.aligner_format or 'no format version'})"
            if take.aligner_yaml else "no aLigner export YAML in this take"
        )
        self.detail.insert("", "end", text="aLigner export", values=("", "", source))
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
                values=(status.state, record.get("exported_at", ""), " · ".join(parts)),
            )
            for change in status.changes:
                self.detail.insert(item, "end", text="", values=("", "", change))

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["take", "aligner_export", *[step.key for step in STEPS]])
            for take in self.takes:
                writer.writerow([
                    self._label(take),
                    take.aligner_yaml.name if take.aligner_yaml else "",
                    *[take.steps[step.key].state if step.key in take.steps else "" for step in STEPS],
                ])


def open_status_browser(folder: Path | None = None):
    root = Tk()
    StatusBrowser(root, folder)
    root.mainloop()
