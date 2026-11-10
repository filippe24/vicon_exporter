"""The 3D files of a take's aLigner export as bars on one time axis, like the aLigner browser's timeline.

Every 3D file should share the take's range and rate. Bars on the most common range are drawn in the
mocap colour; the others are red, with their frames written after the bar.
"""

from tkinter import Canvas, ttk

MOCAP = "#f5a623"  # the aLigner's mocap colour
DIFFERS = "#c45252"
SHARED_BAND = "#f3ead8"
TEXT, MUTED, AXIS = "#222222", "#777777", "#bbbbbb"
ROW, TOP, LABEL_WIDTH, RIGHT_TEXT = 18, 20, 170, 150


def _range(row: dict) -> tuple:
    return row["start_frame"], row["end_frame"], row["sample_rate"]


def _offset(row: dict, shared: tuple) -> str:
    """How the row's range differs from the shared one, e.g. "start +3, end +3 frames"."""
    start, end, rate = shared
    if row["sample_rate"] != rate:
        return f"{row['start_frame']}–{row['end_frame']} @ {row['sample_rate']:g} fps"
    parts = [f"{name} {delta:+d}" for name, delta in
             (("start", row["start_frame"] - start), ("end", row["end_frame"] - end)) if delta]
    return ", ".join(parts) + " frames"


class RangeTimeline(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.canvas = Canvas(self, height=0, background="white", highlightthickness=0)
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw())

    def show(self, rows: list[dict]):
        """`rows`: name, start_frame, end_frame, sample_rate of each 3D file."""
        self.rows = sorted(rows, key=lambda row: row["name"].lower())
        self.canvas.configure(height=TOP + ROW * len(self.rows) + 6 if self.rows else 0)
        self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        if not self.rows:
            return
        keys = [_range(row) for row in self.rows]
        shared = max(set(keys), key=keys.count)
        # Seconds, so files at different rates still line up.
        spans = [(row["start_frame"] / row["sample_rate"], row["end_frame"] / row["sample_rate"]) for row in self.rows]
        low, high = min(start for start, _ in spans), max(end for _, end in spans)
        width = max(canvas.winfo_width(), LABEL_WIDTH + RIGHT_TEXT + 100)
        left, right = LABEL_WIDTH, width - RIGHT_TEXT
        scale = (right - left) / max(high - low, 1e-6)

        def x(seconds):
            return left + (seconds - low) * scale

        bottom = TOP + ROW * len(self.rows)
        start, end, rate = shared
        canvas.create_rectangle(x(start / rate), TOP - 4, x(end / rate), bottom, fill=SHARED_BAND, width=0)
        canvas.create_text(x(start / rate), TOP - 6, anchor="sw", fill=MUTED, font=("Segoe UI", 8),
                           text=f"{start}–{end} @ {rate:g} fps")
        canvas.create_line(left, bottom, right, bottom, fill=AXIS)
        for index, (row, (begin, finish)) in enumerate(zip(self.rows, spans, strict=True)):
            y = TOP + index * ROW + ROW / 2
            differs = _range(row) != shared
            canvas.create_text(LABEL_WIDTH - 8, y, anchor="e", text=row["name"], font=("Segoe UI", 9),
                               fill=DIFFERS if differs else TEXT)
            canvas.create_rectangle(x(begin), y - 5, max(x(finish), x(begin) + 2), y + 5,
                                    fill=DIFFERS if differs else MOCAP, width=0)
            if differs:
                # A few frames are less than a pixel on a long take, so the offset is written out.
                canvas.create_text(x(finish) + 6, y, anchor="w", fill=DIFFERS, font=("Segoe UI", 8),
                                   text=_offset(row, shared))
