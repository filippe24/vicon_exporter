from scipy.spatial.transform import Rotation


def quat_to_zyx(q):
    r = Rotation.from_quat([q.x, q.y, q.z, q.w])
    return r.as_euler("zyx", degrees=True)


def inspect_frame(root_h, frame_idx):
    print(f"\n=== Frame {frame_idx} ===")
    root_h.loadPose(frame_idx)

    for joint, depth, _parent in root_h.layout():
        pos = joint.PositionLocal
        rot = joint.RotationLocal
        euler = quat_to_zyx(rot)

        print("  " * depth + f"{joint.Name}:")
        print("  " * depth + f"  pos = {pos.x:.3f}, {pos.y:.3f}, {pos.z:.3f}")
        print("  " * depth + f"  euler ZYX = {euler}")
