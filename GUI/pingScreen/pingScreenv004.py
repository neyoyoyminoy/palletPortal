"""
this is pingScreenv004.py

updates:
- slice is fixed pointing upward (no rotation)
- ripple/wave animation inside the slice
- subtle glitch lines in the background using the main gui color palette
- green/orange/red slice color for distance thresholds
- based on the working dualpingworker from the pallet portal gui
- includes the 4-button exit combo (ctrl + c + v + enter/return)
"""

import sys  #for argv + exit
import math  #for trig + ripple math
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint  #qt core
from PyQt5.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QFont,
    QPolygon,
    QRegion,
)  #drawing + shapes
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel  #widgets


#-------------------- tiny helpers --------------------
def cy_point(x, y):
    return QPoint(int(x), int(y))  #force ints for qpainter

def polyRegion(poly):
    return QRegion(poly)  #clip region from polygon

def clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))  #simple clamp helper


#======================================================
#-------------------- radar widget --------------------
#======================================================
class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.distance_in = None  #latest distance reading
        self.ripple_phase = 0.0  #phase for inner wave animation
        self.glitch_phase = 0.0  #phase for background glitch lines

        self._timer = QTimer(self)  #animation timer
        self._timer.timeout.connect(self._tick)  #drive phases
        self._timer.start(30)  #~33 fps

    def set_distance(self, d):
        self.distance_in = d  #store latest value
        self.update()  #request repaint

    def _tick(self):
        self.ripple_phase = (self.ripple_phase + 0.15) % (2 * math.pi)  #wave motion
        self.glitch_phase = (self.glitch_phase + 0.08) % (2 * math.pi)  #background motion
        self.update()

    def _distance_color(self):
        d = self.distance_in
        if d is None:
            return QColor(160, 160, 160)  #neutral when no reading
        if d > 30.0:
            return QColor(255, 0, 0)  #red when really far
        if d > 13.0:
            return QColor(255, 160, 0)  #orange mid range
        return QColor(0, 255, 0)  #green when in range

    def _glitch_palette(self):
        #main gui palette (white, cyan, magenta, red)
        return [
            QColor(255, 255, 255, 80),
            QColor(0, 255, 255, 80),
            QColor(255, 0, 255, 80),
            QColor(255, 0, 0, 80),
        ]

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        try:
            w = self.width()
            h = self.height()

            #black background
            p.fillRect(self.rect(), QColor(0, 0, 0))

            cx = w // 2  #center x
            cy = int(h * 0.75)  #drop center a bit low
            radius = int(min(w, h) * 0.55)  #overall radius

            #---------- subtle glitch background ----------
            palette = self._glitch_palette()
            #horizontal glitch lines
            for i in range(6):
                y_frac = 0.2 + 0.1 * i
                y = int(h * y_frac)
                jitter = int(20 * math.sin(self.glitch_phase + i * 0.9))
                col = palette[i % len(palette)]
                p.setPen(QPen(col, 2))
                p.drawLine(0 + jitter, y, w + jitter, y)

            #vertical glitch lines
            for i in range(4):
                x_frac = 0.25 + 0.15 * i
                x = int(w * x_frac)
                jitter = int(15 * math.cos(self.glitch_phase + i * 1.1))
                col = palette[(i + 1) % len(palette)]
                p.setPen(QPen(col, 2))
                p.drawLine(x + jitter, int(h * 0.3), x + jitter, h)

            #---------- build the fixed pizza slice ----------
            start_angle = -90 - 30  #left edge of slice
            end_angle = -90 + 30  #right edge of slice

            poly = QPolygon()
            poly.append(cy_point(cx, cy))  #slice vertex at center

            for deg in range(start_angle, end_angle + 1):
                rads = math.radians(deg)
                x = cx + radius * math.cos(rads)
                y = cy + radius * math.sin(rads)
                poly.append(cy_point(x, y))

            base_color = self._distance_color()  #distance-based color

            #---------- inner ripple/wave inside slice ----------
            p.setClipRegion(polyRegion(poly))  #clip to slice

            for yOffset in range(0, radius, 6):
                wave = 40 * math.sin(self.ripple_phase + yOffset * 0.12)  #wave shape
                rc = clamp(base_color.red() + wave, 0, 255)
                gc = clamp(base_color.green() + wave, 0, 255)
                bc = clamp(base_color.blue() + wave, 0, 255)
                ripple_color = QColor(rc, gc, bc)

                p.setPen(QPen(ripple_color, 4))

                x1 = int(cx - wave * 0.3)
                x2 = int(cx + wave * 0.3)
                yy = int(cy - yOffset)

                p.drawLine(x1, yy, x2, yy)  #wave stripe across slice

            p.setClipping(False)  #stop clipping

            #---------- slice outline ----------
            p.setPen(QPen(base_color, 4))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(poly)

            #center dot
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.drawEllipse(cx - 6, cy - 6, 12, 12)

        finally:
            p.end()  #always end painter


#======================================================
#-------------------- dual ping worker ----------------
#======================================================
class DualPingWorker(QThread):
    ready = pyqtSignal(float, str)  #avg_distance_in, "either"
    log = pyqtSignal(str)  #text log
    distanceUpdated = pyqtSignal(float)  #continuous distance updates

    def __init__(self):
        super().__init__()
        self._stop = False  #stop flag

    def stop(self):
        self._stop = True  #thread exit request

    def run(self):
        try:
            import Jetson.GPIO as GPIO  #import gpio on jetson
        except Exception as e:
            self.log.emit(f"ping error: Jetson.GPIO not available: {e}")
            return

        import time as _time  #local alias for timing

        SENSOR1_PIN = 15  #mb1040 #1
        SENSOR2_PIN = 32  #mb1040 #2
        HARD_MIN_IN = 6.0
        MAX_IN = 254.0
        TRIGGER_IN = 13.0  #threshold for starting csi

        def measure_pulse(pin, timeout=0.05):
            #single pwm pulse measurement
            if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
                return None
            start_ns = _time.monotonic_ns()
            if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
                return None
            end_ns = _time.monotonic_ns()
            return (end_ns - start_ns) / 1000.0  #us

        def read_distance(pin, label):
            width_us = measure_pulse(pin)
            if width_us is None:
                self.log.emit(f"{label} → no pulse detected")
                return None
            distance_in = width_us / 147.0
            if not (HARD_MIN_IN <= distance_in <= MAX_IN):
                self.log.emit(f"{label} → out of range ({distance_in:.2f} in)")
                return None
            distance_cm = distance_in * 2.54
            self.log.emit(f"{label} → {distance_in:.2f} in ({distance_cm:.2f} cm)")
            return distance_in

        try:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(SENSOR1_PIN, GPIO.IN)
            GPIO.setup(SENSOR2_PIN, GPIO.IN)

            self.log.emit("ping worker active (instantaneous dual mb1040)...")

            while not self._stop:
                d1 = read_distance(SENSOR1_PIN, "sensor 1")
                _time.sleep(0.1)  #small gap for crosstalk protection
                d2 = read_distance(SENSOR2_PIN, "sensor 2")

                active_dist = None

                if d1 is not None and d2 is not None:
                    avg = (d1 + d2) / 2.0
                    diff = d1 - d2
                    self.log.emit(f"→ fused avg: {avg:.2f} in | offset: {diff:.2f} in")
                    active_dist = avg
                elif d1 is not None or d2 is not None:
                    active_dist = d1 if d1 is not None else d2
                    self.log.emit(f"→ single sensor active: {active_dist:.2f} in")
                else:
                    self.log.emit("→ both sensors out of range")

                if active_dist is not None:
                    self.distanceUpdated.emit(active_dist)  #live distance feed
                    if active_dist <= TRIGGER_IN:
                        self.log.emit("distance < 13 in — ready to scan")
                        self.ready.emit(active_dist, "either")
                        break

                _time.sleep(0.25)

        except Exception as e:
            self.log.emit(f"ping error: {e}")
        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.log.emit("ping gpio cleaned up")


#======================================================
#-------------------- ping screen ---------------------
#======================================================
class PingScreen(QWidget):
    readyToShip = pyqtSignal(float)  #emits when we are under 13 in

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")  #match other screens
        self.setFocusPolicy(Qt.StrongFocus)  #needed for key combo

        self.worker = None  #dual ping worker
        self._pressed = set()  #tracks key press state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        self.radar = RadarWidget(self)  #custom radar view
        layout.addWidget(self.radar, stretch=1)

        self.status = QLabel("move closer to begin scanning")  #main msg
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:white;")
        self.status.setFont(QFont("Beausite Classic", 26))
        layout.addWidget(self.status)

        self.dist_label = QLabel("")  #distance debug label
        self.dist_label.setAlignment(Qt.AlignCenter)
        self.dist_label.setStyleSheet("color:#aaaaaa;")
        self.dist_label.setFont(QFont("Beausite Classic", 16))
        layout.addWidget(self.dist_label)

    #---------- ping worker wiring ----------
    def start_ping(self):
        if self.worker and self.worker.isRunning():
            return  #already running
        try:
            self.worker = DualPingWorker()
            self.worker.distanceUpdated.connect(self._on_distance)
            self.worker.ready.connect(self._on_ready)
            #optional: hook logs if you want to see them in terminal
            #self.worker.log.connect(lambda msg: print(msg))
            self.worker.start()
        except Exception as e:
            self.status.setText(f"ping error: {e}")
            self.worker = None

    def stop_ping(self):
        if not self.worker:
            return
        try:
            if self.worker.isRunning():
                self.worker.stop()
                self.worker.wait(800)
        except Exception:
            pass
        finally:
            self.worker = None

    def _on_distance(self, d_in):
        self.dist_label.setText(f"distance: {d_in:.2f} in")
        self.radar.set_distance(d_in)

        if d_in > 30.0:
            self.status.setText("move closer to begin scanning")
        elif d_in > 13.0:
            self.status.setText("almost there, keep moving forward")
        else:
            self.status.setText("cameras starting up...")

    def _on_ready(self, d_in, label):
        self.status.setText("cameras starting up...")
        self.stop_ping()
        self.readyToShip.emit(d_in)  #mainwindow can switch to ship screen here

    #---------- qt lifecycle ----------
    def showEvent(self, e):
        super().showEvent(e)
        self.start_ping()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_ping()

    #---------- 4-button exit combo ----------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        #hold ctrl + c + v then press enter/return
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


#======================================================
#-------------------- standalone entry ----------------
#======================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.showFullScreen()  #designed for the 1024x600 display
    sys.exit(app.exec_())
