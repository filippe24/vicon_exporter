from bvh.build_hierarchy import build_tree
from bvh.extract_transforms import quat_to_zyx
from bvh.loader import load_bvh
from bvh.writer import write_bvh


def convert(path_in, path_out):
    container, root_h = load_bvh(path_in)

    # Build clean hierarchy
    root_node = build_tree(root_h)

    # Preorder joint list
    joints = [j for j, _, _ in root_h.layout()]

    frames = []
    for frame_idx in range(container.FrameCount):
        root_h.loadPose(frame_idx)
        values = []

        for i, joint in enumerate(joints):
            if i == 0:
                pos = joint.PositionLocal
                q = joint.RotationLocal
                e = quat_to_zyx(q)
                values.extend([pos.x, pos.y, pos.z])
                values.extend(e.tolist())
            else:
                q = joint.RotationLocal
                e = quat_to_zyx(q)
                values.extend(e.tolist())

        frames.append(values)

    write_bvh(root_node, frames, container.FrameTime, path_out)
