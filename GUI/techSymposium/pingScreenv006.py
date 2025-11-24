"""
pingScreenv006.py

standalone "ping" screen with a radar-style pizza slice:
- static wedge pointing up
- soft circular grid
- pulsing fill inside the wedge once per second
- color changes with distance:
    >= 30 in  -> red
    13–30 in  -> orange
    < 13 in   -> green + "cameras starting up..." hint later if you want

this standalone version simulates distance values so you can test layout/animation.
later, the main gui can call a method like set_distance(dist_in) to drive it from
dualPingWorkerv001.

includes 4-button exit combo: hold ctrl + c + v, then press enter/return.
"""

import sys
import math
import random
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel


class PingRadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 400)
        self.distance_in = 120.0  # simulated distance in inches
        self._pulse_phase = 0.0   # for the inner ripple animation

        # animation timer (~60 fps)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def set_distance(self, dist_in):
        self.distance_in = max(0.0, float(dist_in))
        self.update()

    # simple internal sawtooth distance for demo
    def _tick(self):
        self._pulse_phase += 0.06
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi

        # slow oscillation just for standalone testing
        self.distance_in = 10 + 120 * (0.5 + 0.5 * math.sin(self._pulse_phase / 2.0))
        self.update()

    # choose color from distance
    def current_color(self):
        d = self.distance_in
        if d < 13.0:
            return QColor(0, 255, 128)   # green
        elif d < 30.0:
            return QColor(255, 165, 0)   # orange
        else:
            return QColor(255, 64, 64)   # red

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        p.fillRect(self.rect(), QColor(0, 0, 0))

        cx = w // 2
        base_y = h * 0.80  # bottom of wedge
        radius = min(w * 0.35, h * 0.6)

        # ----- draw soft circular grid -----
        grid_color_main = QColor(0, 255, 255, 80)
        grid_color_alt = QColor(255, 0, 255, 60)

        p.setPen(QPen(grid_color_main, 1))
        for r_factor in (0.3, 0.5, 0.7, 0.9):
            r = radius * r_factor
            p.drawEllipse(int(cx - r), int(base_y - r), int(2 * r), int(2 * r))

        p.setPen(QPen(grid_color_alt, 1))
        # vertical grid lines
        for xf in (-0.4, -0.2, 0, 0.2, 0.4):
            x = cx + xf * radius * 1.3
            p.drawLine(int(x), int(base_y - radius), int(x), int(base_y))

        # ----- compute wedge geometry -----
        half_angle_deg = 32
        half_angle = math.radians(half_angle_deg)

        tip = (cx, base_y)
        left = (cx - radius * math.sin(half_angle),
                base_y - radius * math.cos(half_angle))
        right = (cx + radius * math.sin(half_angle),
                 base_y - radius * math.cos(half_angle))

        # outer wedge outline
        p.setPen(QPen(self.current_color(), 3))
        p.drawLine(int(tip[0]), int(tip[1]), int(left[0]), int(left[1]))
        p.drawLine(int(tip[0]), int(tip[1]), int(right[0]), int(right[1]))
        p.drawLine(int(left[0]), int(left[1]), int(right[0]), int(right[1]))

        # ----- pulsing fill inside wedge -----
        color = self.current_color()
        fill_alpha_base = 40
        fill_alpha_variation = 60
        pulse = 0.5 + 0.5 * math.sin(self._pulse_phase * 2.0)
        alpha = int(fill_alpha_base + fill_alpha_variation * pulse)

        # fill as series of horizontal bands within wedge
        steps = 32
        for i in range(steps):
            t0 = i / float(steps)
            t1 = (i + 1) / float(steps)

            # interpolate between tip and top edge
            y0 = base_y - t0 * radius
            y1 = base_y - t1 * radius
            if y1 < base_y - radius:
                y1 = base_y - radius

            # compute horizontal span from wedge edges at mid height
            ym = (y0 + y1) / 2.0
            frac = (base_y - ym) / radius  # 0 at tip, 1 at top
            half_span = math.tan(half_angle) * frac * radius

            x0 = cx - half_span
            x1 = cx + half_span

            band_color = QColor(color.red(), color.green(), color.blue(), alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(band_color)
            p.drawRect(int(x0), int(y1), int(x1 - x0), int(y0 - y1))

        p.end()


class PingScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ping screen – pallet portal")
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)

        self._pressed = set()  # for exit combo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # radar widget
        self.radar = PingRadarWidget()
        layout.addWidget(self.radar, stretch=3)

        # status text
        self.status_label = QLabel("Move closer to begin scanning")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #ffffff;")
        self.status_label.setFont(QFont("Arial", 26))
        layout.addWidget(self.status_label)

        # distance text
        self.distance_label = QLabel("Distance: -- in")
        self.distance_label.setAlignment(Qt.AlignCenter)
        self.distance_label.setStyleSheet("color: #cccccc;")
        self.distance_label.setFont(QFont("Arial", 18))
        layout.addWidget(self.distance_label)

        # timer to update labels based on radar distance
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._update_labels)
        self.ui_timer.start(80)

    def _update_labels(self):
        d = self.radar.distance_in
        self.distance_label.setText(f"Distance: {d:0.2f} in")
        if d < 13.0:
            self.status_label.setText("Cameras starting up...")
        else:
            self.status_label.setText("Move closer to begin scanning")

    # ---- 4-button exit combo ----
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            QApplication.quit()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.showFullScreen()
    sys.exit(app.exec_())
