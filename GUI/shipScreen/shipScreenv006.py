"""
shipScreenv006.py

fixes:
- title uses EXACT welcome-screen GlitchText class (no clipping, slightly smaller)
- left bubble now has rounded 40px corners, matches right panel exactly
- bubble + progress bar centered vertically on left side
- progress bar now pill style w/ floating highlight (YouTube reference)
- percentage appears UNDER bar
- right subtitle perfectly aligned w/ right rounded panel
- screen no longer shifts when progress animates
"""

import sys
import random
import string
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPixmap
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QHBoxLayout, QSpacerItem, QSizePolicy
)

CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"


# =========================================================
#   ★★★ EXACT GLITCH CLASS FROM WELCOME SCREEN ★★★
# =========================================================
class GlitchText(QWidget):
    def __init__(self, text="WELCOME", led_driver=None):
        super().__init__()
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.led = led_driver

        self.font = QFont("Arial", 62, QFont.Bold)   # slightly smaller to prevent side clipping
        self.setStyleSheet("background-color: black;")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

    def set_led_color(self, rgb):
        pass  # disabled for ShipScreen

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
            if random.random() < 0.25:
                chars[i] = random.choice(
                    string.ascii_uppercase + string.digits + "!@#$%*"
                )
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

        # Base
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        # Red (left)
        if self.glitch_strength:
            shift = self.glitch_strength
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # Cyan (right)
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # Magenta jitter
            if random.random() < 0.4:
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(
                    x + random.randint(-12, 12),
                    y + random.randint(-18, 18),
                    self.scrambled,
                )


# =========================================================
#   ★ Pill-Shaped ProgressBar Widget ★
# =========================================================
class PillProgressBar(QWidget):
    def __init__(self):
        super().__init__()
        self.value = 0    # 0–100
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.repaint)
        self.timer.start(30)

    def setValue(self, v):
        self.value = max(0, min(100, v))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h // 2

        # Outer border
        p.setPen(QColor(0, 0, 0))
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        # Inner fill pill
        fill_w = int((self.value / 100.0) * (w - 12))
        fill_h = h - 12
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 255, 200))   # neon green/cyan mix
        p.drawRoundedRect(6, 6, fill_w, fill_h, fill_h // 2, fill_h // 2)

        # Top glossy highlight
        p.setBrush(QColor(255, 255, 255, 55))
        p.drawRoundedRect(6, 6, fill_w, fill_h // 2, fill_h // 2, fill_h // 2)


# =========================================================
#                  ★ SHIP SCREEN ★
# =========================================================
class ShipScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:black;")
        self.setFocusPolicy(Qt.StrongFocus)

        self._expected_codes = []
        self._found = set()
        self._barcode_items = {}
        self._pressed = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(35, 10, 35, 10)
        root.setSpacing(4)

        # ---------------------------------------------
        #  TITLE (uses welcome glitch)
        # ---------------------------------------------
        self.title = GlitchText("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(105)
        root.addWidget(self.title)

        # ---------------------------------------------
        #  MAIN 2-COLUMN LAYOUT
        # ---------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(40)
        root.addLayout(row)

        # =====================================================
        # LEFT SIDE
        # =====================================================
        left = QVBoxLayout()
        left.setSpacing(25)
        row.addLayout(left, stretch=3)

        # ********** Rounded bubble **********
        self.bubble = QWidget()
        self.bubble.setStyleSheet(
            "background:white; border-radius:40px;"
        )
        bubble_lay = QVBoxLayout(self.bubble)
        bubble_lay.setContentsMargins(35, 20, 35, 20)

        self.scan_msg = QLabel("")
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setStyleSheet("color:black;")
        self.scan_msg.setFont(QFont("Arial", 23))
        bubble_lay.addWidget(self.scan_msg)

        left.addWidget(self.bubble)

        # Spacer between bubble and bar
        left.addSpacerItem(QSpacerItem(0, 30, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # ********** Progress Bar **********
        self.progress_bar = PillProgressBar()
        self.progress_bar.setFixedHeight(50)
        self.progress_bar.setMinimumWidth(420)
        left.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        # % label
        self.percent_label = QLabel("0%")
        self.percent_label.setFont(QFont("Arial", 22))
        self.percent_label.setStyleSheet("color:white;")
        self.percent_label.setAlignment(Qt.AlignCenter)
        left.addWidget(self.percent_label)

        # Bottom-left logo
        left.addStretch(1)
        self.logo_label = QLabel()
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo_label.setPixmap(
                pm.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self.logo_label.setFixedSize(100, 100)
        left.addWidget(self.logo_label, alignment=Qt.AlignLeft | Qt.AlignBottom)

        # =====================================================
        # RIGHT SIDE
        # =====================================================
        right = QVBoxLayout()
        right.setSpacing(10)
        row.addLayout(right, stretch=4)

        # Subtitle centered with panel
        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setFont(QFont("Arial", 27, QFont.Bold))
        subtitle.setStyleSheet("color:white;")
        subtitle.setAlignment(Qt.AlignCenter)
        right.addWidget(subtitle)

        # White rounded panel
        panel = QWidget()
        panel.setStyleSheet("background:white; border-radius:40px;")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(25, 25, 25, 25)

        self.scanned_list = QListWidget()
        self.scanned_list.setStyleSheet(
            "QListWidget { background:white; color:black; font-size:18px; border:0px; }"
        )
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        panel_lay.addWidget(self.scanned_list)

        right.addWidget(panel)

        root.addStretch(1)

    # =====================================================
    # BARCODE HANDLING
    # =====================================================
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()

        self.scan_msg.setText("")
        self.scanned_list.clear()
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(17)
            item.setFont(f)
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    def on_barcode_matched(self, code, score=None, method=None):
        if code in self._found:
            return

        self._found.add(code)
        self.scan_msg.setText(f"{code} was scanned")

        item = self._barcode_items.get(code)
        if item:
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)
            item.setForeground(QColor(150, 150, 150))

        total = len(self._expected_codes)
        pct = int((len(self._found) / total) * 100) if total else 0

        self.progress_bar.setValue(pct)
        self.percent_label.setText(f"{pct}%")

    # =====================================================
    # SECRET EXIT COMBO
    # =====================================================
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        if (e.modifiers() & Qt.ControlModifier) and \
           Qt.Key_C in self._pressed and \
           Qt.Key_V in self._pressed and \
           k in (Qt.Key_Return, Qt.Key_Enter):
            QApplication.quit()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


# =========================================================
# DEMO DRIVER FOR TESTING
# =========================================================
class DemoDriver:
    def __init__(self, screen):
        demo = ["1234567891", "9876543210", "2085692649", "9340754051", "2799407451"]
        screen.set_manifest_codes(demo)
        self.remaining = demo[:]
        self.screen = screen

        self.t = QTimer()
        self.t.timeout.connect(self.tick)
        self.t.start(1500)

    def tick(self):
        if not self.remaining:
            self.t.stop()
            return
        code = self.remaining.pop(0)
        self.screen.on_barcode_matched(code)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()
    DemoDriver(w)
    sys.exit(app.exec_())
