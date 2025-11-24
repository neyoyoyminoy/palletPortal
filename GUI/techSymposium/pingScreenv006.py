"""
pingScreenv006.py

single-direction ping screen with radar-style pizza slice
- colors: red (>30 in), orange (13–30 in), green (<=13 in)
- text:
    "Move closer to begin scanning" when >13 in
    "Cameras starting up..." when <=13 in
- black background, theme accent lines
- exposes set_distance(inches) so gui or worker can feed real data
- standalone demo uses random distances
- includes 4-button exit combo (ctrl + c + v + enter/return)
"""

import sys  #for argv + exit
import random  #for demo distances
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel


class PingScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("ping screen")  #window title
        self.setStyleSheet("background-color:black;")  #black bg
        self.setFocusPolicy(Qt.StrongFocus)  #capture key events
        self._pressed = set()  #track keys for exit combo

        #current distance in inches (None means unknown)
        self._distance_in = None

        #ui layout: just labels; radar is drawn in paintEvent
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(10)

        #status text
        self.status_label = QLabel("Move closer to begin scanning")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:#ffffff;")
        self.status_label.setFont(QFont("Arial", 26, QFont.Bold))
        root.addWidget(self.status_label)

        #distance text
        self.distance_label = QLabel("Distance: --.-- in")
        self.distance_label.setAlignment(Qt.AlignCenter)
        self.distance_label.setStyleSheet("color:#cccccc;")
        self.distance_label.setFont(QFont("Arial", 18))
        root.addWidget(self.distance_label)

        root.addStretch(1)

        #little hint at bottom
        hint = QLabel("hold Ctrl + C + V then press Enter to exit demo")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#666666;")
        hint.setFont(QFont("Arial", 10))
        root.addWidget(hint)

        #simple animation timer for pulse inside the slice
        self._pulse_phase = 0.0
        self._pulse_dir = 1.0

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_pulse)
        self.anim_timer.start(40)  #about 25 fps

    #--------------- external api ---------------
    def set_distance(self, dist_in):
        """update the current measured distance in inches"""
        self._distance_in = dist_in
        if dist_in is None:
            self.status_label.setText("Move closer to begin scanning")
            self.distance_label.setText("Distance: --.-- in")
        else:
            self.distance_label.setText(f"Distance: {dist_in:0.2f} in")
            if dist_in <= 13.0:
                self.status_label.setText("Cameras starting up...")
            else:
                self.status_label.setText("Move closer to begin scanning")
        self.update()  #redraw radar

    #--------------- animation ---------------
    def _tick_pulse(self):
        #simple sawtooth motion to make the bands move
        self._pulse_phase += 0.04 * self._pulse_dir
        if self._pulse_phase > 1.0:
            self._pulse_phase = 1.0
            self._pulse_dir = -1.0
        elif self._pulse_phase < 0.0:
            self._pulse_phase = 0.0
            self._pulse_dir = 1.0
        self.update()

    #--------------- drawing ---------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        #background is already black by stylesheet, but clear anyway
        p.fillRect(self.rect(), QColor(0, 0, 0))

        #radar area: upper middle portion of the screen
        slice_width = int(w * 0.7)
        slice_height = int(h * 0.42)
        cx = w // 2
        bottom_y = int(h * 0.55)

        left_x = cx - slice_width // 2
        right_x = cx + slice_width // 2
        top_y = bottom_y - slice_height

        #choose base color from distance
        dist = self._distance_in
        if dist is None:
            base = QColor(0, 255, 255)  #cyan when unknown
        elif dist <= 13.0:
            base = QColor(0, 255, 0)  #green close
        elif dist <= 30.0:
            base = QColor(255, 165, 0)  #orange medium
        else:
            base = QColor(255, 0, 0)  #red far

        #draw soft circular grid (concentric arcs)
        grid_pen = QPen(QColor(0, 255, 255, 80))
        grid_pen.setWidth(2)
        p.setPen(grid_pen)
        for frac in (0.35, 0.55, 0.75, 0.95):
            r = int(slice_height * frac)
            rect = (cx - r, bottom_y - 2 * r, 2 * r, 2 * r)
            p.drawArc(*rect, 0 * 16, 180 * 16)  #top half only

        #vertical center guideline
        p.setPen(QPen(QColor(0, 255, 255, 60), 1))
        p.drawLine(cx, bottom_y, cx, top_y)

        #pizza slice outline in base color
        p.setPen(QPen(base, 4))
        p.drawLine(cx, bottom_y, left_x, top_y + int(slice_height * 0.15))
        p.drawLine(cx, bottom_y, right_x, top_y + int(slice_height * 0.15))
        p.drawArc(left_x, top_y, slice_width, slice_height, 0 * 16, 180 * 16)

        #radial pulse fill (bands inside the slice)
        #bands move up/down using _pulse_phase
        max_bands = 14
        for i in range(max_bands):
            t = (i + self._pulse_phase * max_bands) / max_bands
            if t < 0.0 or t > 1.0:
                continue

            y = bottom_y - int(t * slice_height)
            #fade alpha with t
            alpha = int(40 + 120 * (1.0 - t))
            band_color = QColor(base.red(), base.green(), base.blue(), alpha)
            p.setPen(QPen(band_color, 3))

            #find horizontal span along the arc between the slice edges
            frac = t
            span = int((slice_width // 2) * (1.0 - 0.1 * (1.0 - frac)))
            p.drawLine(cx - span, y, cx + span, y)

        #sensor dot at bottom
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(cx - 6, bottom_y - 6, 12, 12)

        p.end()

    #--------------- exit combo ---------------
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


# ----------------------------------------------------------------------
# standalone demo
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PingScreen()
    w.showFullScreen()

    #demo: random distances every 0.8 s
    def _rand_update():
        dist = random.uniform(8.0, 40.0)
        w.set_distance(dist)

    t = QTimer()
    t.timeout.connect(_rand_update)
    t.start(800)

    sys.exit(app.exec_())
