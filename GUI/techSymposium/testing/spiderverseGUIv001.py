"""
spiderverseGUIv001.py
Single-file backup Pallet Portal GUI with embedded screens.

Screens:
  - WelcomeScreen: glitch "WELCOME" + insert-flashdrive prompt, idle -> WaitScreen
  - WaitScreen: bouncing logo screensaver, any key (ctrl/c/v/enter) returns to Welcome
  - PingScreen: radar-style wedge asking user to move closer (demo animation)
  - ShipScreen: shipment in progress, glitch title, scanned bubble, pill progress bar
  - ViewOrderScreen: table of completed orders, black bg + white rounded panel

Notes:
  - This version is mostly a visual/demo backup and does NOT talk to real cameras,
    barcode readers, or ping sensors. Those can be wired later by replacing the
    demo timers with your real workers.
  - Global quit combo everywhere: hold Control + C + V and press Enter/Return.
  - Designed for 1024x600 but scales to other resolutions.
"""

import sys
import random
import string
import math
from datetime import datetime

from PyQt5.QtCore import (
    Qt,
    QTimer,
    QRect,
    pyqtSignal,
    QSize,
    QPointF,
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QGridLayout,
    QStackedWidget,
)

# ------------------------------------------------------------------
#  Paths to logo assets (update if your paths differ)
# ------------------------------------------------------------------
CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"
WHITE_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentWhiteLogo.png"
RED_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentRedLogo.png"
MAGENTA_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentMagentaLogo.png"


# ==================================================================
#  BaseScreen — common key handling (Ctrl + C + V + Enter to quit)
# ==================================================================
class BaseScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed = set()
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # global exit combo: hold ctrl + c + v, press enter/return
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


# ==================================================================
#  GlitchTitle (similar to welcome glitch text)
# ==================================================================
class GlitchTitle(BaseScreen):
    def __init__(self, text="WELCOME", font_size=48, parent=None):
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0

        self.font = QFont("Arial", font_size, QFont.Bold)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)  # ~16 fps

    def update_glitch(self):
        if random.random() < 0.35:
            self.glitch_strength = random.randint(3, 10)
            self.scramble()
        else:
            self.scrambled = self.text
            self.glitch_strength = 0
        self.update()

    def scramble(self):
        chars = list(self.text)
        for i in range(len(chars)):
            if random.random() < 0.15:
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        widget_rect = self.rect()
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)

        fm = self.fontMetrics()
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()
        x = text_rect.x()
        y = baseline_y

        # base white layer
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            shift = self.glitch_strength

            # red left
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan right
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter
            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)
                jitter_x = x + random.randint(-10, 10)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# ==================================================================
#  WelcomeScreen
# ==================================================================
class WelcomeScreen(BaseScreen):
    start_requested = pyqtSignal()
    user_activity = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:black;")

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(40)

        # logo row
        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        root.addLayout(top_row)

        logo_label = QLabel()
        logo_label.setFixedSize(96, 96)
        pm = QPixmap(WHITE_LOGO_PATH)
        if not pm.isNull():
            logo_label.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        top_row.addWidget(logo_label, alignment=Qt.AlignLeft | Qt.AlignTop)
        top_row.addStretch(1)

        # glitch "WELCOME"
        self.title = GlitchTitle("WELCOME", font_size=64)
        self.title.setMinimumHeight(140)
        root.addWidget(self.title)

        root.addStretch(1)

        # white pill "Insert flashdrive to begin..."
        bubble = QWidget()
        bubble.setObjectName("welcomeBubble")
        bubble.setAttribute(Qt.WA_StyledBackground, True)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(40, 18, 40, 18)

        msg = QLabel("Insert flashdrive to begin...")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color:#000000;")
        msg.setFont(QFont("Arial", 24))
        bubble_layout.addWidget(msg)

        root.addWidget(bubble, alignment=Qt.AlignHCenter)
        root.addStretch(2)

        extra = """
            QWidget { background-color:black; }
            QWidget#welcomeBubble { background-color:#ffffff; border-radius:40px; }
        """
        self.setStyleSheet(extra)

    def keyPressEvent(self, e):
        self.user_activity.emit()
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_V):
            self.start_requested.emit()
        super().keyPressEvent(e)


# ==================================================================
#  WaitScreen — bouncing logo
# ==================================================================
class WaitScreen(BaseScreen):
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:black;")

        self.logos = []
        for path in (WHITE_LOGO_PATH, CYAN_LOGO_PATH, RED_LOGO_PATH, MAGENTA_LOGO_PATH):
            pm = QPixmap(path)
            if not pm.isNull():
                self.logos.append(
                    pm.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        if not self.logos:
            self.logos.append(QPixmap(180, 180))

        self.color_index = 0
        self.current_logo = self.logos[self.color_index]

        self.x = 50
        self.y = 50
        self.dx = 2.0
        self.dy = 1.6
        self.margin = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(16)

    def switch_color(self):
        self.color_index = (self.color_index + 1) % len(self.logos)
        self.current_logo = self.logos[self.color_index]

    def update_frame(self):
        w = self.width()
        h = self.height()
        lw = self.current_logo.width()
        lh = self.current_logo.height()

        self.x += self.dx
        self.y += self.dy
        hit_edge = False

        if self.x <= self.margin:
            self.x = self.margin
            self.dx *= -1
            hit_edge = True
        elif self.x + lw >= w - self.margin:
            self.x = w - self.margin - lw
            self.dx *= -1
            hit_edge = True

        if self.y <= self.margin:
            self.y = self.margin
            self.dy *= -1
            hit_edge = True
        elif self.y + lh >= h - self.margin:
            self.y = h - self.margin - lh
            self.dy *= -1
            hit_edge = True

        if hit_edge:
            self.switch_color()

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        p.drawPixmap(int(self.x), int(self.y), self.current_logo)
        p.end()

    def keyPressEvent(self, e):
        if e.key() in (
            Qt.Key_Control,
            Qt.Key_C,
            Qt.Key_V,
            Qt.Key_Return,
            Qt.Key_Enter,
        ):
            self.exit_requested.emit()
        super().keyPressEvent(e)


# ==================================================================
#  PingScreen — radar wedge demo
# ==================================================================
class PingScreen(BaseScreen):
    ping_ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:black;")

        self.distance_in = 120.0
        self.phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_demo)
        self.timer.start(50)

    def _update_demo(self):
        self.phase += 0.12
        self.distance_in = max(8.0, self.distance_in - 0.4)

        if self.distance_in <= 13.0:
            self.ping_ready.emit()
            self.timer.stop()

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.black)

        w = self.width()
        h = self.height()

        cx = w // 2
        cy = int(h * 0.45)
        radius = int(min(w, h) * 0.25)

        # circular grid
        for i, col in enumerate(
            (
                QColor(0, 255, 255, 40),
                QColor(255, 0, 255, 40),
                QColor(255, 0, 0, 40),
            )
        ):
            r = radius * (0.4 + 0.2 * i)
            p.setPen(col)
            p.drawArc(
                QRect(cx - int(r), cy - int(r), int(2 * r), int(2 * r)),
                0,
                180 * 16,
            )

        # wedge
        p.setPen(QColor(255, 0, 0))
        top_y = cy - radius
        left_x = cx - int(radius * 0.7)
        right_x = cx + int(radius * 0.7)
        p.drawPolygon(
            QPointF(cx, cy + radius * 0.7),
            QPointF(left_x, top_y),
            QPointF(right_x, top_y),
        )

        # pulse bars
        p.setPen(QColor(255, 0, 0))
        steps = 24
        for i in range(steps):
            t = i / steps
            y = top_y + t * (cy + radius * 0.7 - top_y)
            amp = 18 * (0.5 + 0.5 * (1.0 + math.sin(self.phase + t * 6.0)))
            p.drawLine(cx - amp, int(y), cx + amp, int(y))

        # text
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 26))
        msg = "move closer to begin scanning"
        if self.distance_in <= 13.0:
            msg = "cameras starting up..."

        p.drawText(QRect(0, int(h * 0.65), w, 40), Qt.AlignCenter, msg)

        p.setFont(QFont("Arial", 18))
        p.drawText(
            QRect(0, int(h * 0.72), w, 40),
            Qt.AlignCenter,
            f"Distance: {self.distance_in:.2f} in",
        )

        p.end()


# ==================================================================
#  PillProgressBar
# ==================================================================
class PillProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._visual = 0.0

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step_anim)
        self._anim_timer.start(30)

    def setValue(self, v):
        v = max(0, min(100, int(v)))
        self._value = v

    def _step_anim(self):
        target = self._value / 100.0
        if abs(self._visual - target) < 0.005:
            self._visual = target
        else:
            self._visual += (target - self._visual) * 0.12
        self.update()

    def sizeHint(self):
        return QSize(420, 40)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 4 or h <= 4:
            p.end()
            return

        margin = 6
        outer = QRect(margin, margin, w - 2 * margin, h - 2 * margin)
        if outer.width() <= 0 or outer.height() <= 0:
            p.end()
            return

        radius = outer.height() / 2

        # shadow
        shadow = outer.translated(0, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawRoundedRect(shadow, radius, radius)

        # outer pill
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QColor(0, 0, 0))
        p.drawRoundedRect(outer, radius, radius)

        # inner track
        track_margin = 4
        track = outer.adjusted(track_margin, track_margin, -track_margin, -track_margin)
        track_radius = track.height() / 2
        p.setBrush(QColor(210, 255, 250))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(track, track_radius, track_radius)

        # fill
        frac = max(0.0, min(1.0, float(self._visual)))
        fill_width = int(track.width() * frac)
        if fill_width > 0:
            fill = QRect(track.left(), track.top(), fill_width, track.height())
            p.setBrush(QColor(0, 255, 180))
            p.drawRoundedRect(fill, track_radius, track_radius)

        p.end()


# ==================================================================
#  ShipScreen
# ==================================================================
class ShipScreen(BaseScreen):
    scan_complete = pyqtSignal(int, datetime, datetime)  # scanned_count, start, end

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:black;")

        self._expected_codes = []
        self._found = set()
        self._barcode_items = {}
        self._demo_timer = None
        self._start_time = None

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(10)

        self.title = GlitchTitle("SHIPMENT IN PROGRESS", font_size=44)
        self.title.setMinimumHeight(90)
        root.addWidget(self.title)

        root.addSpacing(20)

        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        # left column
        left_col = QVBoxLayout()
        left_col.setSpacing(24)
        middle.addLayout(left_col, stretch=3)

        left_col.addSpacing(40)

        self.bubble = QWidget()
        self.bubble.setObjectName("scanBubble")
        self.bubble.setAttribute(Qt.WA_StyledBackground, True)
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(40, 18, 40, 18)

        self.scan_msg = QLabel("")
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setStyleSheet("color:#000000;")
        self.scan_msg.setFont(QFont("Arial", 20))
        bubble_layout.addWidget(self.scan_msg)
        left_col.addWidget(self.bubble)

        left_col.addSpacing(40)

        self.progress = PillProgressBar()
        self.progress.setFixedHeight(40)
        left_col.addWidget(self.progress)

        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.percent_label.setStyleSheet("color:#ffffff;")
        self.percent_label.setFont(QFont("Arial", 18))
        left_col.addWidget(self.percent_label)

        left_col.addStretch(1)

        logo_label = QLabel()
        logo_label.setFixedSize(96, 96)
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            logo_label.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        left_col.addWidget(logo_label, alignment=Qt.AlignLeft | Qt.AlignBottom)

        # right column
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        middle.addLayout(right_col, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#eaeaea;")
        subtitle.setFont(QFont("Arial", 26, QFont.Bold))
        right_col.addWidget(subtitle)

        panel = QWidget()
        panel.setObjectName("scanPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)

        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        self.scanned_list.setStyleSheet(
            """
            QListWidget { background-color:#ffffff; border:0px; color:#000000; }
            QListWidget::item { padding:4px; }
            """
        )
        panel_layout.addWidget(self.scanned_list)
        right_col.addWidget(panel)

        extra_style = """
            QWidget { background-color:black; }
            QWidget#scanBubble { background-color:#ffffff; border-radius:40px; }
            QWidget#scanPanel { background-color:#ffffff; border-radius:40px; }
        """
        self.setStyleSheet(extra_style)

    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.scan_msg.setText("")
        self.progress.setValue(0)
        self.percent_label.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    def on_barcode_matched(self, val):
        if val in self._found:
            return
        self._found.add(val)

        self.scan_msg.setText(f"{val} was scanned")

        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        total = len(self._expected_codes)
        if total > 0:
            pct = int(round(len(self._found) * 100.0 / total))
            self.progress.setValue(pct)
            self.percent_label.setText(f"{pct}%")

    def start_demo(self):
        demo_codes = [
            "1234567891",
            "9876543210",
            "2085692649",
            "9340754051",
            "2799407451",
        ]
        self.set_manifest_codes(demo_codes)
        self._remaining = list(demo_codes)
        self._start_time = datetime.now()

        if self._demo_timer is not None:
            self._demo_timer.stop()

        self._demo_timer = QTimer(self)
        self._demo_timer.timeout.connect(self._fake_scan)
        self._demo_timer.start(1700)

    def _fake_scan(self):
        if not self._remaining:
            if self._demo_timer:
                self._demo_timer.stop()
            end = datetime.now()
            self.scan_complete.emit(len(self._found), self._start_time, end)
            return

        code = self._remaining.pop(0)
        self.on_barcode_matched(code)


# ==================================================================
#  ViewOrderScreen
# ==================================================================
class ViewOrderScreen(BaseScreen):
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:black;")

        self.orders = []
        self._next_row = 1

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)

        self.title = GlitchTitle("VIEW ORDERS", font_size=42)
        self.title.setMinimumHeight(90)
        root.addWidget(self.title)

        panel = QWidget()
        panel.setObjectName("ordersPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(32, 24, 32, 24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel_layout.addWidget(scroll)

        self.container = QWidget()
        scroll.setWidget(self.container)

        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid.setHorizontalSpacing(40)
        self.grid.setVerticalSpacing(8)

        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 12, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#ffffff;")
            self.grid.addWidget(lbl, 0, col)

        root.addWidget(panel, stretch=1)

        self.status = QLabel("Press X to return to Welcome Screen")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:#ffffff;")
        self.status.setFont(QFont("Arial", 12, QFont.Bold))
        root.addWidget(self.status)

        extra = """
            QWidget#ordersPanel { background-color:#101010; border-radius:40px; }
        """
        self.setStyleSheet(self.styleSheet() + extra)

    def add_order(self, trailer, archway, start_time, end_time, scanned_count):
        duration = end_time - start_time
        self.orders.append(
            dict(
                trailer=trailer,
                archway=archway,
                start=start_time,
                end=end_time,
                duration=duration,
                scanned=scanned_count,
            )
        )

        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
        duration_str = str(duration).split(".")[0]

        values = [trailer, archway, start_str, end_str, duration_str, str(scanned_count)]
        for col, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setFont(QFont("Arial", 11))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#ffffff;")
            self.grid.addWidget(lbl, self._next_row, col)

        self._next_row += 1

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_X, Qt.Key_C):
            self.exit_requested.emit()
        super().keyPressEvent(e)


# ==================================================================
#  MainWindow
# ==================================================================
class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()

        self.welcome = WelcomeScreen()
        self.wait = WaitScreen()
        self.ping = PingScreen()
        self.ship = ShipScreen()
        self.view = ViewOrderScreen()

        self.addWidget(self.welcome)  # 0
        self.addWidget(self.wait)     # 1
        self.addWidget(self.ping)     # 2
        self.addWidget(self.ship)     # 3
        self.addWidget(self.view)     # 4

        self.setCurrentWidget(self.welcome)

        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._show_wait)
        self._restart_idle()

        self.welcome.start_requested.connect(self._start_flow)
        self.welcome.user_activity.connect(self._restart_idle)

        self.wait.exit_requested.connect(self._return_from_wait)
        self.ping.ping_ready.connect(self._start_ship)
        self.ship.scan_complete.connect(self._finish_ship)
        self.view.exit_requested.connect(self._back_to_welcome)

        self._trailer_counter = 101

    def _restart_idle(self):
        if self.currentWidget() is self.welcome:
            self.idle_timer.start(30_000)  # 30 seconds
        else:
            self.idle_timer.stop()

    def _show_wait(self):
        self.setCurrentWidget(self.wait)

    def _return_from_wait(self):
        self.setCurrentWidget(self.welcome)
        self._restart_idle()

    def _start_flow(self):
        self.setCurrentWidget(self.ping)
        self.idle_timer.stop()

    def _start_ship(self):
        self.setCurrentWidget(self.ship)
        self.ship.start_demo()

    def _finish_ship(self, scanned_count, start_time, end_time):
        trailer = f"T-{self._trailer_counter}"
        self._trailer_counter += 1
        archway = "Archway 1"
        self.view.add_order(trailer, archway, start_time, end_time, scanned_count)
        self.setCurrentWidget(self.view)

    def _back_to_welcome(self):
        self.setCurrentWidget(self.welcome)
        self._restart_idle()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.showFullScreen()
    sys.exit(app.exec_())
