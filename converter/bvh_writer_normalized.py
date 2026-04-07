from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation as R


@dataclass
class JointNode:
    name: str
    offset: np.ndarray
    children: list[JointNode] = field(default_factory=list)
    is_root: bool = False


def build_joint_tree_from_bvhio(root_joint) -> JointNode:
    """Convert bvhio hierarchy into a simple JointNode tree."""

    def recurse(joint, is_root=False):
        offset = np.array(joint.RestPose.Position, dtype=float)
        node = JointNode(joint.Name, offset, is_root=is_root)
        for child in joint.Children:
            node.children.append(recurse(child, is_root=False))
        return node

    return recurse(root_joint, is_root=True)


def iter_joint_nodes(root: JointNode) -> Iterable[JointNode]:
    """Preorder traversal."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in reversed(node.children):
            stack.append(child)


def quat_to_euler_zyx(q) -> np.ndarray:
    """Convert glm.quat (w,x,y,z) → Euler ZYX degrees."""
    r = R.from_quat([q.x, q.y, q.z, q.w])
    return r.as_euler("zyx", degrees=True)  # [rz, ry, rx]


def write_bvh(
    root: JointNode, frames: list[list[float]], frame_time: float, path: Path
):
    """Write normalized BVH for AI4Animation:
    - root: 6 channels (pos + rot ZYX)
    - others: 3 channels (rot ZYX)
    """

    def write_joint(f, node: JointNode, indent=0):
        ind = "  " * indent
        keyword = "ROOT" if node.is_root else "JOINT"
        f.write(f"{ind}{keyword} {node.name}\n")
        f.write(f"{ind}{{\n")
        f.write(
            f"{ind}  OFFSET {node.offset[0]:.6f} {node.offset[1]:.6f} {node.offset[2]:.6f}\n"
        )

        if node.is_root:
            f.write(
                f"{ind}  CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation\n"
            )
        else:
            f.write(f"{ind}  CHANNELS 3 Zrotation Yrotation Xrotation\n")

        for child in node.children:
            write_joint(f, child, indent + 1)

        f.write(f"{ind}}}\n")

    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        f.write("HIERARCHY\n")
        write_joint(f, root)

        f.write("MOTION\n")
        f.write(f"Frames: {len(frames)}\n")
        f.write(f"Frame Time: {frame_time:.6f}\n")

        for fr in frames:
            f.write(" ".join(f"{v:.6f}" for v in fr) + "\n")
