"""
ping.py
Pallet Portal – Ping Distance Screen

Features:
- Black background
- Upward-facing "pizza slice" scan zone
- Smooth radar-style pulse animation (fills the slice)
- Soft circular grid (Option B style)
- Color zones:
      >30 in  = red
  13–30 in  = orange
      <13 in = green  → "Cameras starting up..."
- Emits readyForShip(distance, "either") when < 13 inches
- 4-button exit combo: ctrl + c + v + enter/return
"""

import sys
import math
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QFont,
    QPen,
)
from PyQt5.QtWidgets import QWidget, QApplication


class PingScreen(QWidget):

    # ✔ signal added (required by palletPortal.py)
    readyForShip = pyqtSignal(float, str)   # (distance, "either")

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Ping Distance")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background-color:black;")

        # distance coming from DualPingWorker → set_distance()
        self.distance_in = None

        # pulse animation
        self.pulse = 0.0
        self.pulse_speed = 0.035

        self._pressed = set()  # for exit combo

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)  # ~60fps

    # --------------------------
    # External update from worker
    # --------------------------
    def set_distance(self, dist_in):
        self.distance_in = dist_in
        self.update()

        # ✔ Emit ready signal when <13 inches
        if dist_in is not None and dist_in < 13:
            self.readyForShip.emit(dist_in, "either")

    # --------------------------
    # Animation tick
    # --------------------------
    def _tick(self):
        self.pulse += self.pulse_speed
        if self.pulse > 1.0:
            self.pulse = 0.0
        self.update()

    # --------------------------
    # Drawing
    # --------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        center_x = w // 2
        base_y = int(h * 0.78)
        radius = int(h * 0.70)

        # circular grid
        self._draw_soft_grid(p, center_x, base_y, radius)

        # radar pulse
        self._draw_pulse_slice(p, center_x, base_y, radius)

        # distance text
        self._draw_distance_text(p, w, h)

        p.end()

    # ===========================================================
    #   Soft Circular Grid
    # ===========================================================
    def _draw_soft_grid(self, p, cx, cy, r):
        p.setPen(QPen(QColor(50, 50, 50, 120), 2))

        ring_count = 4
        for i in range(1, ring_count + 1):
            rr = (r / ring_count) * i
            p.drawEllipse(cx - rr, cy - rr, 2 * rr, 2 * rr)

    # ===========================================================
    #   Pulse “pizza slice”
    # ===========================================================
    def _draw_pulse_slice(self, p, cx, cy, r):
        spread = math.radians(50)    # slice width
        start_ang = -spread
        end_ang = spread

        rr = r * self.pulse          # pulse radius

        # color zones
        if self.distance_in is None:
            col = QColor(0, 255, 255, 160)     # idle cyan
        elif self.distance_in < 13:
            col = QColor(0, 255, 0, 170)       # green
        elif self.distance_in < 30:
            col = QColor(255, 165, 0, 170)     # orange
        else:
            col = QColor(255, 0, 0, 170)       # red

        p.setBrush(col)
        p.setPen(Qt.NoPen)

        # build wedge path
        from PyQt5.QtGui import QPainterPath
        pp = QPainterPath()
        pp.moveTo(cx, cy)

        steps = 40
        for i in range(steps + 1):
            t = start_ang + (i / steps) * (end_ang - start_ang)
            x = cx + rr * math.sin(t)
            y = cy - rr * math.cos(t)
            pp.lineTo(x, y)

        pp.closeSubpath()
        p.drawPath(pp)

    # ===========================================================
    #   Status / distance text
    # ===========================================================
    def _draw_distance_text(self, p, w, h):
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 32, QFont.Bold))

        if self.distance_in is None:
            txt = "Waiting for sensor..."
        else:
            d = self.distance_in
            if d < 13:
                txt = "Cameras starting up..."
            else:
                txt = f"Move closer (Distance: {d:.1f} in)"

        p.drawText(0, int(h * 0.15), w, 50, Qt.AlignCenter, txt)

    # --------------------------
    # Key handling
    # --------------------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # exit combo: ctrl + c + v + enter
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


# =====================================================
# Standalone test
# =====================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.resize(1024, 600)
    w.showFullScreen()

    # test animation
    import random
    from PyQt5.QtCore import QTimer

    def update_fake():
        w.set_distance(random.uniform(8, 35))

    timer = QTimer()
    timer.timeout.connect(update_fake)
    timer.start(400)

    sys.exit(app.exec_())
