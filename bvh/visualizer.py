import numpy as np
import pyqtgraph.opengl as gl
from PyQt5.QtWidgets import QApplication


def visualize_frame(root_h, frame_idx=0):
    root_h.loadPose(frame_idx)

    # Collect joint positions and edges
    positions = []
    edges = []
    index_map = {}

    for idx, (joint, depth, parent) in enumerate(root_h.layout()):
        index_map[joint] = idx
        positions.append(
            [joint.PositionWorld.x, joint.PositionWorld.y, joint.PositionWorld.z]
        )
        if parent is not None:
            edges.append((index_map[parent], idx))

    positions = np.array(positions)

    # Create window
    app = QApplication([])
    w = gl.GLViewWidget()
    w.setWindowTitle("BVH Skeleton Viewer")
    w.show()

    # Draw joints
    scatter = gl.GLScatterPlotItem(pos=positions, size=5, color=(1, 1, 1, 1))
    w.addItem(scatter)

    # Draw bones
    for i, j in edges:
        pts = np.array([positions[i], positions[j]])
        line = gl.GLLinePlotItem(pos=pts, color=(0, 1, 0, 1), width=2, antialias=True)
        w.addItem(line)

    app.exec_()
