"""
main.py — JS AudioRouter
Dark-themed control panel: device list w/ enable toggles + volume
sliders, VB-Cable status, snapshot/rollback buttons.
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QCheckBox, QSlider, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

from core.device_manager import list_output_devices, find_vb_cable, is_vb_cable_installed
from core.engine import RouterEngine
from core import profile_manager

DARK_STYLE = """
QWidget { background-color: #1e1e1e; color: #f0f0f0; font-family: Segoe UI; }
QPushButton { background-color: #2d2d2d; border: 1px solid #444; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background-color: #3a3a3a; }
QSlider::groove:horizontal { background: #333; height: 4px; }
QSlider::handle:horizontal { background: #5aa9e6; width: 12px; margin: -6px 0; border-radius: 6px; }
QLabel#status_ok { color: #6ee787; }
QLabel#status_bad { color: #e76e6e; }
"""


class DeviceRow(QWidget):
    def __init__(self, device, engine):
        super().__init__()
        self.device = device
        self.engine = engine
        layout = QHBoxLayout(self)

        self.checkbox = QCheckBox(f"{device['name']}  [{device['type']}]")
        self.checkbox.setChecked(False)
        self.checkbox.stateChanged.connect(self.toggle)
        layout.addWidget(self.checkbox, 3)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(80)
        self.slider.valueChanged.connect(self.set_volume)
        layout.addWidget(self.slider, 2)

    def toggle(self, state):
        if state:
            self.engine.add_branch(self.device["id"], self.device["name"])
        else:
            self.engine.remove_branch(self.device["id"])

    def set_volume(self, value):
        self.engine.set_gain(self.device["id"], value / 100.0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JS AudioRouter")
        self.resize(480, 480)
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        self.engine = None
        ci, co = find_vb_cable()
        if is_vb_cable_installed():
            self.status_label.setObjectName("status_ok")
            self.status_label.setText("✔ VB-Audio Cable detected")
            self.engine = RouterEngine(cable_output_id=co)
            self.engine.start()
        else:
            self.status_label.setObjectName("status_bad")
            self.status_label.setText("✘ VB-Audio Cable NOT found — install it first")

        layout.addWidget(QLabel("Output devices:"))
        for d in list_output_devices():
            if d["is_vb_cable"]:
                continue  # don't let user route back into the cable itself
            row = DeviceRow(d, self.engine) if self.engine else DeviceRow(d, self._dummy_engine())
            layout.addWidget(row)

        btn_row = QHBoxLayout()
        snap_btn = QPushButton("Snapshot current settings")
        snap_btn.clicked.connect(self.do_snapshot)
        rollback_btn = QPushButton("Rollback to saved snapshot")
        rollback_btn.clicked.connect(self.do_rollback)
        btn_row.addWidget(snap_btn)
        btn_row.addWidget(rollback_btn)
        layout.addLayout(btn_row)

    def _dummy_engine(self):
        class Dummy:
            def add_branch(self, *a, **k): pass
            def remove_branch(self, *a, **k): pass
            def set_gain(self, *a, **k): pass
        return Dummy()

    def do_snapshot(self):
        path = profile_manager.snapshot()
        QMessageBox.information(self, "Snapshot saved", f"Saved to {path}")

    def do_rollback(self):
        try:
            restored, missing = profile_manager.rollback()
            msg = f"Restored {len(restored)} devices."
            if missing:
                msg += f"\nCould not restore: {', '.join(missing)}"
            QMessageBox.information(self, "Rollback complete", msg)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "No snapshot found", str(e))

    def closeEvent(self, event):
        if self.engine:
            self.engine.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
