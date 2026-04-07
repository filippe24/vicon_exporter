from __future__ import annotations

from pathlib import Path


class Joint:
    def __init__(
        self,
        name: str,
        offset: list[float] | None = None,
        channels: list[str] | None = None,
        is_root: bool = False,
    ):
        self.name = name
        self.offset: list[float] = offset or [0.0, 0.0, 0.0]
        self.channels: list[str] = channels or []
        self.children: list[Joint] = []
        self.end_site: list[float] | None = None
        self.is_root = is_root


class BVH:
    def __init__(self):
        self.root: Joint | None = None
        self.joints: list[Joint] = []
        self.frames: list[list[float]] = []
        self.frame_time: float = 0.0


def load_bvh(path: Path | str) -> BVH:
    """Parse a BVH file, preserving hierarchy, offsets, channels and frames."""
    bvh = BVH()
    lines = Path(path).read_text().splitlines()

    stack: list[Joint] = []
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if line.startswith("ROOT") or line.startswith("JOINT"):
            name = line.split()[1]
            joint = Joint(name, is_root=line.startswith("ROOT"))

            if stack:
                stack[-1].children.append(joint)
            else:
                bvh.root = joint

            stack.append(joint)
            bvh.joints.append(joint)

        elif line.startswith("OFFSET"):
            parts = line.split()
            offset = list(map(float, parts[1:4]))
            if stack:
                stack[-1].offset = offset

        elif line.startswith("CHANNELS"):
            parts = line.split()
            count = int(parts[1])
            channels = parts[2 : 2 + count]
            if stack:
                stack[-1].channels = channels

        elif line.startswith("End Site"):
            # next two lines: "{", "OFFSET x y z"
            i += 2
            offset_line = lines[i].strip()
            offset = list(map(float, offset_line.split()[1:4]))
            if stack:
                stack[-1].end_site = offset
        elif line == "}":
            # Only pop if we are inside a joint block
            if (
                stack
                and (i + 1 < len(lines))
                and (
                    "OFFSET" in lines[i - 1]
                    or "CHANNELS" in lines[i - 1]
                    or "End Site" in lines[i - 1]
                )
            ):
                stack.pop()

        elif line.startswith("Frame Time:"):
            bvh.frame_time = float(line.split(":")[1])

        elif line and line[0].isdigit():
            values = list(map(float, line.split()))
            bvh.frames.append(values)

        i += 1

    return bvh


def _write_joint(f, joint: Joint, indent: int = 0) -> None:
    ind = "  " * indent
    keyword = "ROOT" if joint.is_root else "JOINT"
    f.write(f"{ind}{keyword} {joint.name}\n")
    f.write(f"{ind}{{\n")
    f.write(
        f"{ind}  OFFSET {joint.offset[0]:.6f} {joint.offset[1]:.6f} {joint.offset[2]:.6f}\n"
    )
    f.write(f"{ind}  CHANNELS {len(joint.channels)} {' '.join(joint.channels)}\n")

    for child in joint.children:
        _write_joint(f, child, indent + 1)

    if joint.end_site is not None:
        f.write(f"{ind}  End Site\n")
        f.write(f"{ind}  {{\n")
        f.write(
            f"{ind}    OFFSET {joint.end_site[0]:.6f} {joint.end_site[1]:.6f} {joint.end_site[2]:.6f}\n"
        )
        f.write(f"{ind}  }}\n")

    f.write(f"{ind}}}\n")


def save_bvh(bvh: BVH, path: Path | str) -> None:
    """Write a BVH with preserved hierarchy and updated channels/frames."""
    if bvh.root is None:
        raise ValueError("BVH has no root joint.")

    with Path(path).open("w", encoding="utf-8") as f:
        f.write("HIERARCHY\n")
        _write_joint(f, bvh.root)

        f.write("MOTION\n")
        f.write(f"Frames: {len(bvh.frames)}\n")
        f.write(f"Frame Time: {bvh.frame_time:.6f}\n")

        for fr in bvh.frames:
            f.write(" ".join(f"{v:.6f}" for v in fr) + "\n")
