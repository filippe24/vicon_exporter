from pathlib import Path


def write_bvh(root, frames, frame_time, path):
    path = Path(path)

    def write_joint(f, node, indent=0):
        ind = "  " * indent
        kw = "ROOT" if node.is_root else "JOINT"
        f.write(f"{ind}{kw} {node.name}\n")
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

        for c in node.children:
            write_joint(f, c, indent + 1)

        f.write(f"{ind}}}\n")

    with path.open("w") as f:
        f.write("HIERARCHY\n")
        write_joint(f, root)

        f.write("MOTION\n")
        f.write(f"Frames: {len(frames)}\n")
        f.write(f"Frame Time: {frame_time:.6f}\n")

        for fr in frames:
            f.write(" ".join(f"{v:.6f}" for v in fr) + "\n")
