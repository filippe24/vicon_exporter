import bvhio


def load_bvh(path):
    print("**loading bvh")
    container = bvhio.readAsBvh(path)
    print("  ▫️frames:", container.FrameCount)
    print("  ▫️frame Time:", container.FrameTime)
    print("  ▫️frequency:", (1 / container.FrameTime))

    print("\n**convert to hierarchy.")
    root_h = bvhio.convertBvhToHierarchy(container.Root)

    print("\n** joint list.")
    root_h.printTree()
    for joint, _index, depth in root_h.layout():  # noqa: B007
        print(f"{joint.PositionWorld} {joint.UpWorld} {joint.Name}")
    # for joint, depth, _parent in root_h.layout():
    #     print("  " * depth + f"- {joint.Name}  offset={joint.RestPose.Position}")

    return container, root_h
