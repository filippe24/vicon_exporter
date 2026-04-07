import numpy as np


class Node:
    def __init__(self, name, offset, is_root=False):
        self.name = name
        self.offset = np.array(offset, float)
        self.children = []
        self.is_root = is_root


def build_tree(root_h):
    def recurse(joint, is_root=False):
        node = Node(joint.Name, joint.RestPose.Position, is_root)
        for child in joint.Children:
            node.children.append(recurse(child, False))
        return node

    return recurse(root_h, True)


def print_tree(node, depth=0):
    print("  " * depth + f"{node.name} offset={node.offset}")
    for c in node.children:
        print_tree(c, depth + 1)
