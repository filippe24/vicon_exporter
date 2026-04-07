from __future__ import annotations

from pathlib import Path

import bvhio

from converter.bvh_writer_normalized import (
    build_joint_tree_from_bvhio,
    iter_joint_nodes,
    quat_to_euler_zyx,
    write_bvh,
)


def convert_vicon_bvh_to_target(path_in: Path | str, path_out: Path | str):
    path_in = Path(path_in)
    path_out = Path(path_out)

    # 1) Load BVH using bvhio
    container = bvhio.readAsBvh(str(path_in))
    root_h = bvhio.convertBvhToHierarchy(container.Root)

    # 2) Build simple tree for writing
    root_node = build_joint_tree_from_bvhio(root_h)

    # 3) Determine joint order (preorder)
    joint_nodes = list(iter_joint_nodes(root_node))
    name_to_joint = {j.Name: j for j, _, _ in root_h.layout()}
    joints_in_order = [name_to_joint[node.name] for node in joint_nodes]

    # 4) Extract animation
    frames = []
    frame_count = container.FrameCount
    frame_time = container.FrameTime

    for frame_idx in range(frame_count):
        root_h.loadPose(frame_idx)
        values = []

        for i, joint in enumerate(joints_in_order):
            if i == 0:
                # Root: translation + rotation
                pos = joint.PositionLocal
                q = joint.RotationLocal
                euler = quat_to_euler_zyx(q)
                values.extend([pos.x, pos.y, pos.z])
                values.extend(euler.tolist())
            else:
                # Children: rotation only
                q = joint.RotationLocal
                euler = quat_to_euler_zyx(q)
                values.extend(euler.tolist())

        frames.append(values)

    # 5) Write normalized BVH
    write_bvh(root_node, frames, frame_time, path_out)
