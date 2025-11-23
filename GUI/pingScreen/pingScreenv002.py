"""
this is pingScreenv2.py

updates from v1:
- slice no longer rotates
- slice always points upward (fixed orientation)
- added ripple/wave animation inside the slice
- radar background updated to match glitch theme (white/cyan/red/magenta accents)
- green/orange/red still represent distance thresholds
- kept the four-button exit combo (ctrl + c + v + enter/return)

the ripple effect animates vertically inside the slice to mimic energy waves
coming from the sensors, and blends with the distance color
"""

import sys
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygon
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
import math


# ============================================================
# -------------------- RadarWidget ----------------------------
# ============================================================

class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.distance_in = None  #latest distance
        self.ripple_phase = 0    #for ripple animation

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 FPS

    def _tick(self):
        self.ripple_phase = (self.ripple_phase + 0.15) % (2 * math.pi)
        self.update()

    # ----------- distance color -----------
    def _distance_color(self):
        d = self.distance_in
        if d is None:
            return QColor(150, 150, 150)

        if d > 30:
            return QColor(255, 0, 0)        # red
        if d > 13:
            return QColor(255, 160, 0)      # orange
        return QColor(0, 255, 0)            # green

    # ----------- theme colors -----------
    def _theme_grid_colors(self):
        # glitch color theme (white, cyan, magenta, red)
        return [
            QColor(255, 255, 255, 60),
            QColor(0, 255, 255, 60),
            QColor(255, 0, 255, 60),
            QColor(255, 0, 0, 60),
        ]

    def set_distance(self, d):
        self.distance_in = d
        self.update()

    # ============================================================
    # -------------------- PAINT ---------------------------------
    # ============================================================

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # background
        p.fillRect(self.rect(), QColor(0, 0, 0))

        # center of radar
        cx = w // 2
        cy = int(h * 0.75)

        # radius of slice
        radius = int(min(w, h) * 0.55)

        # slice is a 60-degree wedge pointing straight UP
        start_angle = -90 - 30   # left boundary
        end_angle   = -90 + 30   # right boundary

        # build polygon for slice
        poly = QPolygon()
        poly.append(cy_point(cx, cy))  # center

        for deg in range(start_angle, end_angle + 1):
            rad = math.radians(deg)
            x = cx + radius * math.cos(rad)
            y = cy + radius * math.sin(rad)
            poly.append(cy_point(x, y))

        # draw faint glitch grid arcs
        grid_colors = self._theme_grid_colors()
        for i, col in enumerate(grid_colors):
            p.setPen(QPen(col, 2))
            r = int(radius * (0.25 + 0.15 * i))
            p.drawArc(cx - r, cy - r, 2 * r, 2 * r, 180 * 16, 180 * 16)

        # determine slice base color
        base_color = self._distance_color()

        # DRAW RIPPLE INSIDE THE SLICE
        p.setClipRegion(polyRegion(poly))

        for yOffset in range(0, radius, 6):
            ripple = 40 * math.sin(self.ripple_phase + yOffset * 0.1)
            ripple_color = QColor(
                clamp(base_color.red()   + ripple, 0, 255),
                clamp(base_color.green() + ripple, 0, 255),
                clamp(base_color.blue()  + ripple, 0, 255),
            )
            p.setPen(QPen(ripple_color, 4))
            p.drawLine(
                cx - ripple * 0.2,
                cy - yOffset,
                cx + ripple * 0.2,
                cy - yOffset,
            )

        p.setClipping(False)

        # Slice outline
        p.setPen(QPen(base_color, 4))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(poly)

        # center dot
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - 6, cy - 6, 12, 12)

        p.end()


# helpers
def cy_point(x, y):
    from PyQt5.QtCore import QPoint
    return QPoint(int(x), int(y))

def polyRegion(poly):
    from PyQt5.QtGui import QRegion
    return QRegion(poly)

def clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


# ============================================================
# -------------------- DualPingWorker -------------------------
# ============================================================

class DualPingWorker(QThread):
    ready = pyqtSignal(float, str)
    log = pyqtSignal(str)
    distanceUpdated = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import Jetson.GPIO as GPIO
        except Exception as e:
            self.log.emit(f"gpio unavailable: {e}")
            return

        import time as _time

        SENSOR1_PIN = 15
        SENSOR2_PIN = 32
        HARD_MIN_IN = 6
        MAX_IN = 254
        TRIGGER_IN = 13

        def measure(pin):
            if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=50) is None:
                return None
            start = _time.monotonic_ns()
            if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=50) is None:
                return None
            end = _time.monotonic_ns()
            return (end - start) / 1000.0

        def read(pin):
            width = measure(pin)
            if width is None:
                return None
            d = width / 147.0
            if not (HARD_MIN_IN <= d <= MAX_IN):
                return None
            return d

        try:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(SENSOR1_PIN, GPIO.IN)
            GPIO.setup(SENSOR2_PIN, GPIO.IN)

            while not self._stop:
                d1 = read(SENSOR1_PIN)
                _time.sleep(0.1)
                d2 = read(SENSOR2_PIN)

                dist = None

                if d1 and d2:
                    dist = (d1 + d2) / 2
                elif d1 or d2:
                    dist = d1 if d1 else d2

                if dist:
                    self.distanceUpdated.emit(dist)
                    if dist <= TRIGGER_IN:
                        self.ready.emit(dist, "either")
                        break

                _time.sleep(0.15)

        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass


# ============================================================
# -------------------- PingScreen -----------------------------
# ============================================================

class PingScreen(QWidget):
    readyToShip = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:black;")
        self.setFocusPolicy(Qt.StrongFocus)

        self.worker = None
        self._pressed = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        self.radar = RadarWidget()
        layout.addWidget(self.radar, stretch=1)

        self.status = QLabel("move closer to begin scanning")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:white;")
        self.status.setFont(QFont("Beausite Classic", 26))
        layout.addWidget(self.status)

        self.dist_label = QLabel("")
        self.dist_label.setAlignment(Qt.AlignCenter)
        self.dist_label.setStyleSheet("color:#aaaaaa;")
        self.dist_label.setFont(QFont("Beausite Classic", 16))
        layout.addWidget(self.dist_label)

    # worker wiring
    def start_ping(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = DualPingWorker()
        self.worker.distanceUpdated.connect(self._on_dist)
        self.worker.ready.connect(self._on_ready)
        self.worker.start()

    def stop_ping(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(800)
            self.worker = None

    def _on_dist(self, d):
        self.dist_label.setText(f"distance: {d:.2f} in")
        self.radar.set_distance(d)
        if d > 30:
            self.status.setText("move closer to begin scanning")
        elif d > 13:
            self.status.setText("almost there, keep moving forward")
        else:
            self.status.setText("cameras starting up...")

    def _on_ready(self, d, _):
        self.status.setText("cameras starting up...")
        self.stop_ping()
        self.readyToShip.emit(d)

    def showEvent(self, e):
        super().showEvent(e)
        self.start_ping()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_ping()

    # exit combo
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        if (mods & Qt.ControlModifier) and Qt.Key_C in self._pressed and Qt.Key_V in self._pressed \
           and k in (Qt.Key_Return, Qt.Key_Enter):
            QApplication.quit()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


# standalone test
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.showFullScreen()
    sys.exit(app.exec_())
