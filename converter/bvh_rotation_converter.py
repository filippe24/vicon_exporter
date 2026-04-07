from __future__ import annotations

from scipy.spatial.transform import Rotation as R  # noqa: N817

from .bvh_parser import BVH

AXIS_MAP = {
    "Xrotation": "x",
    "Yrotation": "y",
    "Zrotation": "z",
}

TARGET_ORDER = "zyx"  # Zrotation → Yrotation → Xrotation


def parse_channels(channels: list[str]) -> str:
    """Extract Euler order from a CHANNELS list."""
    return "".join(AXIS_MAP[ch] for ch in channels if "rotation" in ch)


def convert_euler(euler_deg, src_order: str):
    """Convert Euler angles from src_order → TARGET_ORDER."""
    r = R.from_euler(src_order, euler_deg, degrees=True)
    return r.as_euler(TARGET_ORDER, degrees=True).tolist()


def convert_bvh(bvh: BVH) -> BVH:
    """
    Convert BVH rotations to:
      - uniform 6 channels per joint
      - rotation order Z,Y,X
      - root keeps translation, children get 0 0 0
    """
    new_frames = []

    for frame in bvh.frames:
        cursor = 0
        new_frame: list[float] = []

        for joint in bvh.joints:
            ch = joint.channels
            pos_ch = [c for c in ch if "position" in c]
            rot_ch = [c for c in ch if "rotation" in c]

            pos_vals = frame[cursor : cursor + len(pos_ch)]
            cursor += len(pos_ch)

            rot_vals = frame[cursor : cursor + len(rot_ch)]
            cursor += len(rot_ch)

            if rot_ch:
                src_order = parse_channels(rot_ch)
                new_rot = convert_euler(rot_vals, src_order)
            else:
                new_rot = [0.0, 0.0, 0.0]

            if joint.is_root:
                new_frame.extend(pos_vals)
            else:
                new_frame.extend([0.0, 0.0, 0.0])

            new_frame.extend(new_rot)

        new_frames.append(new_frame)

    bvh.frames = new_frames

    for joint in bvh.joints:
        joint.channels = [
            "Xposition",
            "Yposition",
            "Zposition",
            "Zrotation",
            "Yrotation",
            "Xrotation",
        ]

    return bvh
