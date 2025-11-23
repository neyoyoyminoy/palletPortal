"""
this is pingScreenv001.py

this separates the ping stage into its own screen with a radar-style animation
it uses the dual mb1040 worker to read distance and shows:
- red when distance > 30 in
- orange when 13–30 in
- green when < 13 in

when distance < 13 in it says "cameras starting up..." and fires readyToShip
exit combo: hold ctrl + c + v then press enter/return

based on the existing DualPingWorker + ShipScreen layout from the pallet portal gui
"""

import sys  #for argv + exit
import os  #may be handy later when wiring into main gui
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal  #qt core stuff
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont  #drawing tools
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel  #widgets


# -------------------- radar widget --------------------
class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.distance_in = None  #latest distance in inches
        self.sweep_angle = 0  #current sweep angle in degrees
        self._timer = QTimer(self)  #timer for sweep
        self._timer.timeout.connect(self._tick)  #advance sweep on timer
        self._timer.start(30)  #about 33 fps

    def set_distance(self, dist_in):
        self.distance_in = dist_in  #store latest distance
        self.update()  #trigger repaint

    def _tick(self):
        self.sweep_angle = (self.sweep_angle + 5) % 360  #spin in one direction
        self.update()  #repaint with new angle

    def _color_for_distance(self):
        d = self.distance_in
        if d is None:
            return QColor(80, 80, 80)  #no data yet
        if d > 30.0:
            return QColor(255, 0, 0)  #red for far
        if d > 13.0:
            return QColor(255, 160, 0)  #orange mid
        return QColor(0, 200, 0)  #green for in range

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        #background
        p.fillRect(self.rect(), QColor(0, 0, 0))

        #center + radius for radar
        radius = int(min(w, h) * 0.4)
        cx = w // 2
        cy = h // 2 + int(radius * 0.25)  #bump down a bit

        #draw radar arcs in subtle grey
        p.setPen(QPen(QColor(60, 60, 60), 2))
        for r in (radius, int(radius * 0.66), int(radius * 0.33)):
            p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)

        #draw baseline line
        p.drawLine(cx, cy, cx, cy - radius)

        #compute wedge rect
        rect = self.rect()
        rect_size = 2 * radius
        rect_x = cx - radius
        rect_y = cy - radius

        #color based on distance
        color = self._color_for_distance()
        brush = QBrush(color)
        p.setBrush(brush)
        p.setPen(Qt.NoPen)

        #pizza slice sweep (40 degree span)
        start_deg = self.sweep_angle - 20
        span_deg = 40
        start16 = int(start_deg * 16)
        span16 = int(span_deg * 16)

        p.drawPie(rect_x, rect_y, rect_size, rect_size, start16, span16)

        #small center dot
        p.setBrush(QBrush(QColor(200, 200, 200)))
        p.drawEllipse(cx - 4, cy - 4, 8, 8)

        p.end()


# -------------------- DualPingWorker --------------------
class DualPingWorker(QThread):
    ready = pyqtSignal(float, str)  #avg_distance_in, "either"
    log = pyqtSignal(str)
    distanceUpdated = pyqtSignal(float)  #continuous distance updates

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import Jetson.GPIO as GPIO
        except Exception as e:
            self.log.emit(f"ping error: Jetson.GPIO not available: {e}")
            return

        import time as _time

        SENSOR1_PIN = 15
        SENSOR2_PIN = 32
        HARD_MIN_IN = 6.0
        MAX_IN = 254.0
        TRIGGER_IN = 13.0

        def measure_pulse(pin, timeout=0.05):
            if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
                return None
            start_ns = _time.monotonic_ns()
            if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
                return None
            end_ns = _time.monotonic_ns()
            return (end_ns - start_ns) / 1000.0

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

            self.log.emit("ping worker active (instantaneous mode)...")
            while not self._stop:
                d1 = read_distance(SENSOR1_PIN, "sensor 1")
                _time.sleep(0.1)
                d2 = read_distance(SENSOR2_PIN, "sensor 2")

                active_dist = None

                if d1 is not None and d2 is not None:
                    avg = (d1 + d2) / 2.0
                    diff = d1 - d2
                    self.log.emit(f"→ fused avg: {avg:.2f} in | offset: {diff:.2f} in")
                    active_dist = avg
                elif d1 is not None or d2 is not None:
                    active_dist = d1 if d1 is not None else d2
                    self.log.emit(f"→ single sensor: {active_dist:.2f} in")
                else:
                    self.log.emit("→ both sensors out of range")

                if active_dist is not None:
                    self.distanceUpdated.emit(active_dist)
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


# -------------------- PingScreen --------------------
class PingScreen(QWidget):
    readyToShip = pyqtSignal(float)  #fires when we hit <13 in

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("ping screen")  #hidden in kiosk but handy for dev
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)

        self._pressed = set()  #for 4-button exit combo
        self.worker = None  #dual ping thread

        #layout: radar + status text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        self.radar = RadarWidget()  #custom radar widget
        layout.addWidget(self.radar, stretch=1)

        self.status = QLabel("move closer to begin scanning")  #main message
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color: white;")
        self.status.setFont(QFont("Beausite Classic", 24))
        layout.addWidget(self.status)

        self.distance_label = QLabel("")  #optional debug distance
        self.distance_label.setAlignment(Qt.AlignCenter)
        self.distance_label.setStyleSheet("color: #aaaaaa;")
        self.distance_label.setFont(QFont("Beausite Classic", 16))
        layout.addWidget(self.distance_label)

    # ----- ping worker handling -----
    def start_ping(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            self.worker = DualPingWorker()
            self.worker.log.connect(self._on_log)  #can extend later
            self.worker.distanceUpdated.connect(self._on_distance)
            self.worker.ready.connect(self._on_ready)
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

    def _on_log(self, msg):
        #placeholder for future debug box
        #print(msg)  #uncomment if you want terminal logs
        pass

    def _on_distance(self, dist_in):
        #update radar + text based on latest distance
        self.radar.set_distance(dist_in)
        self.distance_label.setText(f"distance: {dist_in:.2f} in")

        if dist_in > 30.0:
            self.status.setText("move closer to begin scanning")
        elif dist_in > 13.0:
            self.status.setText("almost there, keep moving forward")
        else:
            #this will get overridden when ready fires, but keep it in sync
            self.status.setText("cameras starting up...")

    def _on_ready(self, dist_in, label):
        #triggered once when we hit <= 13 in
        self.status.setText("cameras starting up...")
        try:
            self.stop_ping()
        except Exception:
            pass
        self.readyToShip.emit(dist_in)  #main window can swap to ship screen here

    # ----- lifecycle -----
    def showEvent(self, e):
        super().showEvent(e)
        self.start_ping()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_ping()

    def closeEvent(self, e):
        try:
            self.stop_ping()
        except Exception:
            pass
        super().closeEvent(e)

    # ----- 4-button exit combo -----
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        #secret exit combo: hold ctrl + c + v, then press enter/return
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
        try:
            self._pressed.remove(e.key())
        except KeyError:
            pass
        super().keyReleaseEvent(e)


# -------------------- standalone entry (for testing on jetson) --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.showFullScreen()  #matches your other test screens
    sys.exit(app.exec_())
