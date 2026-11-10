"""Overview of what each take has exported and what needs a new export.

The table only reads files. "Export selected…" runs main.py on the chosen takes in its own console
(Shogun's full output) and follows its progress file: the step running now and its time show in the
table, each take refreshes as soon as one of its steps ends, and a failed step stays marked until it
is exported again.
"""

import csv
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox, ttk

from exporter.export_status import (
    CURRENT,
    NEEDS_EXPORT,
    NOT_APPLICABLE,
    NOT_EXPORTED,
    STATE_TEXT,
    STEPS,
    UNVERIFIED,
    TakeStatus,
    take_status,
)
from ui import preferences
from ui.range_timeline import RangeTimeline
from utils.file_search import find_take_folders

MAIN_SCRIPT = Path(__file__).resolve().parent.parent / "main.py"
FILTERS = ("All takes", "Needs a new export", "Not fully exported", "3D ranges differ", "No aLigner export")
LEGEND = (
    " · ".join(f"{symbol} {sentence}" for symbol, sentence in STATE_TEXT.values() if symbol)
    + " · ⟳ exporting now. 3D range: the frames and rate the aLigner export gives its 3D files; ⚠ they "
    "differ. aLigner exported: when aLigner last wrote its export YAML; ⚠ the alignment was saved later "
    "without exporting, so export again from aLigner first."
)


def _date(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _state(state: str) -> str:
    """The state with its table symbol, for the details."""
    return f"{STATE_TEXT[state][0].split(' ')[0]} {state}".strip()


def open_file(path: str):
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opens the log in the user's default viewer
    else:
        subprocess.Popen(["xdg-open", path])


class StatusBrowser:
    def __init__(self, root: Tk, folder: Path | None):
        self.root = root
        self.folder = folder
        self.takes: list[TakeStatus] = []
        self.results: queue.Queue = queue.Queue()
        self.scan_id = 0
        self.pending = 0
        self.total: int | None = None
        # The running export: its process, takes, progress file, and the step running in each take.
        self.export: subprocess.Popen | None = None
        self.exporting: list[Path] = []
        self.progress: Path | None = None
        self.progress_offset = 0
        self.active: dict[Path, tuple[str, list[str], float]] = {}
        self.done: list[dict] = []
        self.detail_logs: dict[str, str] = {}
        root.title("Vicon Exporter · Export status")
        root.minsize(1100, 680)

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
        self.stop_button = ttk.Button(actions, text="Stop after this step", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.selection_text = StringVar(value="Select takes (Ctrl/Shift+click) to export them.")
        ttk.Label(actions, textvariable=self.selection_text).pack(side="left", padx=6)

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        table = ttk.Frame(panes)
        columns = ["aligner", "range"] + [step.key for step in STEPS]
        self.tree = ttk.Treeview(table, columns=columns, selectmode="extended")
        self.tree.heading("#0", text="Take")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.heading("aligner", text="aLigner exported")
        self.tree.column("aligner", width=130, stretch=False)
        self.tree.heading("range", text="3D range")
        self.tree.column("range", width=130, anchor="center", stretch=False)
        for step in STEPS:
            self.tree.heading(step.key, text=step.label)
            self.tree.column(step.key, width=95, anchor="center", stretch=False)
        self.tree.tag_configure("outdated", background="#fbe9c6")
        self.tree.tag_configure("missing", background="#f6d0d0")
        self.tree.tag_configure("ranges", background="#f2d7ee")
        self.tree.tag_configure("none", foreground="#888888")
        self.tree.tag_configure("queued", background="#e8f0fb")
        self.tree.tag_configure("active", background="#b9d3f5")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_detail())
        panes.add(table, weight=3)

        detail = ttk.Frame(panes)
        self.timeline = RangeTimeline(detail)
        self.timeline.pack(fill="x")
        tools = ttk.Frame(detail, padding=(0, 4))
        tools.pack(fill="x")
        self.log_button = ttk.Button(tools, text="Open Shogun log", command=self.open_log, state="disabled")
        self.log_button.pack(side="left")
        ttk.Label(tools, text="Select a failed step to open the log of its last run.",
                  foreground="#666666").pack(side="left", padx=6)
        self.detail = ttk.Treeview(detail, columns=("state", "when", "detail"), show="tree headings")
        self.detail.heading("#0", text="Step")
        self.detail.heading("state", text="State")
        self.detail.heading("when", text="Exported")
        self.detail.heading("detail", text="Details")
        self.detail.column("#0", width=160, stretch=False)
        self.detail.column("state", width=130, stretch=False)
        self.detail.column("when", width=150, stretch=False)
        self.detail.column("detail", width=560, stretch=True)
        self.detail.pack(fill="both", expand=True)
        self.detail.bind("<<TreeviewSelect>>", lambda _event: self._update_log_button())
        self.detail.bind("<Double-1>", lambda _event: self.open_log())
        panes.add(detail, weight=2)

        if folder:
            root.after(50, self.scan)

    # Scanning

    def choose(self):
        folder = filedialog.askdirectory(
            title="Select dataset or take folder", initialdir=preferences.dataset_dialog_start()
        )
        if folder:
            preferences.remember_dataset_folder(folder)
            self.folder = Path(folder)
            self.folder_text.set(folder)
            self.scan()

    def scan(self):
        """Rescan the whole folder."""
        if self.folder is None:
            return
        self.scan_id += 1
        self.takes = []
        self.total = None
        self.fill()
        self.summary.set("Looking for takes…")
        self._start(self.folder, None)

    def refresh(self, takes: list[Path]):
        """Read these takes again and update their rows in place."""
        if self.folder is not None and takes:
            self._start(self.folder, takes)

    def _start(self, folder: Path, only: list[Path] | None):
        self.pending += 1
        threading.Thread(target=self._scan, args=(self.scan_id, folder, only), daemon=True).start()
        if self.pending == 1:
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
        changed = selected_changed = False
        selected = set(self.tree.selection())
        while not self.results.empty():
            scan_id, kind, value = self.results.get()
            if kind == "done":
                self.pending -= 1
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
                selected_changed |= str(value.take_dir) in selected
        if changed or not self.pending:
            self.fill()
        if selected_changed:
            self.show_detail()
        if self.pending:
            if self.total is not None and self.export is None:
                self.summary.set(f"Scanning {len(self.takes)}/{self.total} takes…")
            self.root.after(150, self._collect)

    # Table

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
            return [take for take in self.takes if take.range_differs]
        if mode == FILTERS[4]:
            return [take for take in self.takes if take.aligner_yaml is None]
        return self.takes

    def _values(self, take: TakeStatus) -> list[str]:
        if take.aligner_yaml:
            aligner = _date(take.aligner_exported_at) + (" ⚠" if take.aligner_export_stale else "")
        else:
            aligner = "none"
        operation, running, started = self.active.get(take.take_dir, ("", [], 0.0))
        cells = []
        for step in STEPS:
            if step.key in running:
                cells.append(f"⟳ {_clock(time.monotonic() - started)}")
            elif step.key in take.steps:
                cells.append(STATE_TEXT[take.steps[step.key].state][0])
            else:
                cells.append("")
        return [aligner, take.range_text, *cells]

    def _tags(self, take: TakeStatus) -> tuple[str, ...]:
        if take.take_dir in self.active:
            return ("active",)
        if self.export is not None and take.take_dir in self.exporting:
            return ("queued",)
        if take.error:
            return ("missing",)
        if take.range_differs:
            return ("ranges",)
        if take.outdated:
            return ("outdated",)
        return () if take.aligner_yaml else ("none",)

    def fill(self):
        """Update the rows in place; rebuild only when the rows shown change order."""
        shown = self.visible()
        wanted = [str(take.take_dir) for take in shown]
        current = list(self.tree.get_children())
        if wanted[: len(current)] != current:
            selected = set(self.tree.selection())
            self.tree.delete(*current)
            current = []
        else:
            selected = None
        for take, iid in zip(shown, wanted, strict=True):
            values, tags = self._values(take), self._tags(take)
            if self.tree.exists(iid):
                self.tree.item(iid, values=values, tags=tags)
            else:
                self.tree.insert("", "end", iid=iid, text=self._label(take), values=values, tags=tags)
        if selected is not None:
            self.tree.selection_set([iid for iid in selected if self.tree.exists(iid)])
        if self.export is None:
            self.summary.set(self._overview())

    def _overview(self) -> str:
        needing = sum(bool(take.outdated) for take in self.takes)
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
        differ = sum(take.range_differs for take in self.takes)
        return (
            f"{len(self.takes)} takes · {aligned} with an aLigner export · {complete} exported and current · "
            f"{needing} need a new export · {differ} with 3D ranges that differ · "
            f"{unverified} exported before tracking, not verified"
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

    # Details

    def show_detail(self):
        self.detail.delete(*self.detail.get_children())
        self.detail_logs = {}
        chosen = self.selected_takes()
        self.selection_text.set(
            f"{len(chosen)} takes selected." if chosen else "Select takes (Ctrl/Shift+click) to export them."
        )
        self.timeline.show(chosen[0].mocap if len(chosen) == 1 else [])
        self._update_log_button()
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
            if take.mocap:
                text = (f"{len(take.ranges)} different ranges among {len(take.mocap)} 3D files: fix the alignment "
                        "in aLigner so they share one" if take.range_differs
                        else f"{len(take.mocap)} 3D files share frames {take.range_text}")
                state = "⚠ differ" if take.range_differs else "✓ shared"
                self.detail.insert("", "end", text="3D range", values=(state, "", text))
        else:
            self.detail.insert("", "end", text="aLigner export", values=("", "", "no aLigner export YAML in this take"))
        operation, running, started = self.active.get(take.take_dir, ("", [], 0.0))
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
            state = f"⟳ exporting {_clock(time.monotonic() - started)}" if step.key in running else _state(status.state)
            item = self.detail.insert(
                "", "end", text=step.label, open=True,
                values=(state, str(record.get("exported_at", ""))[:16].replace("T", " "), " · ".join(parts)),
            )
            if status.log:
                self.detail_logs[item] = status.log
            for change in status.changes:
                self.detail.insert(item, "end", text="", values=("", "", change))

    def _update_log_button(self):
        selected = self.detail.selection()
        self.log_button.configure(state="normal" if selected and selected[0] in self.detail_logs else "disabled")

    def open_log(self):
        selected = self.detail.selection()
        log = self.detail_logs.get(selected[0]) if selected else None
        if not log:
            return
        if not Path(log).is_file():
            messagebox.showinfo("Log not found", f"The log is no longer there:\n{log}", parent=self.root)
            return
        open_file(log)

    # Export

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

    def run_export(
        self, takes: list[TakeStatus], steps: list[str], overwrite: bool, crop: str
    ):
        self.progress = Path(tempfile.mkdtemp(prefix="vicon_exporter_")) / "progress.jsonl"
        self.progress_offset = 0
        self.active, self.done = {}, []
        arguments = [sys.executable, str(MAIN_SCRIPT), "--steps", ",".join(steps), "--prop-crop", crop,
                     "--progress", str(self.progress)]
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
        self.stop_button.configure(state="normal", text="Stop after this step")
        self.summary.set(f"Exporting {len(takes)} takes ({', '.join(steps)}); Shogun's output is in the console…")
        self.fill()
        self.root.after(1000, self._watch_export)

    def stop(self):
        """main.py skips the steps not started yet; the running one finishes so its files are complete."""
        if self.progress is not None:
            self.progress.with_suffix(".stop").touch()
            self.stop_button.configure(state="disabled", text="Stopping…")

    def _read_progress(self) -> list[dict]:
        try:
            with open(self.progress, "rb") as handle:
                handle.seek(self.progress_offset)
                data = handle.read()
        except OSError:
            return []
        complete = data[: data.rfind(b"\n") + 1]  # a line still being written waits for the next read
        self.progress_offset += len(complete)
        return [json.loads(line) for line in complete.decode("utf-8").splitlines() if line.strip()]

    def _watch_export(self):
        if self.export is None:
            return
        finished = self.export.poll() is not None
        ended = []
        for event in self._read_progress():
            take = Path(event["take"])
            if event["event"] == "start":
                self.active[take] = (event["operation"], event.get("steps") or [], time.monotonic())
            else:
                self.active.pop(take, None)
                self.done.append(event)
                ended.append(take)
        if finished:
            self._finish_export()
            return
        self.refresh(list(dict.fromkeys(ended)))
        self.fill()
        selected = set(self.tree.selection())
        if len(selected) == 1 and any(str(take) in selected for take in self.active):
            self.show_detail()  # its elapsed time
        self.summary.set(self._export_summary())
        self.root.after(1000, self._watch_export)

    def _counts(self) -> str:
        counts: dict[str, int] = {}
        for row in self.done:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return ", ".join(f"{count} {status}" for status, count in sorted(counts.items())) or "none yet"

    def _export_summary(self) -> str:
        now = [
            f"{self._label(TakeStatus(take))}: {operation} {_clock(time.monotonic() - started)}"
            for take, (operation, _steps, started) in self.active.items()
        ]
        return (f"Exporting {len(self.exporting)} takes · steps ended: {self._counts()} · "
                f"now: {'; '.join(now) or 'starting…'}")

    def _finish_export(self):
        self.export = None
        self.active = {}
        self.export_button.configure(state="normal")
        self.stop_button.configure(state="disabled", text="Stop after this step")
        failed = [row for row in self.done if row["status"] == "FAILED"]
        message = f"Export finished · steps: {self._counts()}."
        if failed:
            message += f" {len(failed)} failed: they are marked ✗ failed; select the take for the error and log."
        elif not self.done:
            message += " No step reported back: see the export console."
        shutil.rmtree(self.progress.parent, ignore_errors=True)
        self.progress = None
        self.refresh(self.exporting)
        self.fill()
        self.summary.set(message)
        self.root.after(8000, lambda: self.export is None and self.summary.set(self._overview()))

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["take", "aligner_exported_at", "aligner_saved_at", "range_3d", "ranges_differ",
                             *[step.key for step in STEPS]])
            for take in self.takes:
                writer.writerow([
                    self._label(take),
                    _date(take.aligner_exported_at),
                    _date(take.aligner_saved_at),
                    take.range_text,
                    take.range_differs,
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
        differ = sum(take.range_differs for take in takes)
        ttk.Label(body, text=f"{len(takes)} takes", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        for count, text in (
            (stale, "have an alignment saved after the last aLigner export; their aLigner YAML may hold "
                    "older values."),
            (differ, "have 3D files with different ranges in their aLigner export."),
        ):
            if count:
                ttk.Label(body, foreground="#a06000", wraplength=420,
                          text=f"⚠ {count} of them {text}").pack(anchor="w", pady=(4, 0))
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
                f"{needing} need a new export" if needing else "",
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
        # Read widget values before destroying the window that owns them.
        overwrite, crop = self.overwrite.get(), self.crop.get()
        self.window.destroy()
        self.run(self.takes, steps, overwrite, crop)


def open_status_browser(folder: Path | None = None):
    root = Tk()
    StatusBrowser(root, folder or preferences.last_dataset_folder())
    root.mainloop()
