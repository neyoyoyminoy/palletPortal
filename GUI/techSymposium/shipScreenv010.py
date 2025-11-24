"""
shipScreenv010.py

standalone shipment screen:
- centered glitch title "SHIPMENT IN PROGRESS"
- left: rounded white bubble "<code> was scanned"
- left middle: pill-style animated progress bar + percentage label
- right: "SCANNED BARCODES" + rounded white panel with list
- black background with white text + cyan accent

later, the main gui can call:
    set_manifest_codes([...])
    on_barcode_matched(code, score, method)

includes 4-button exit combo: hold ctrl + c + v, then press enter/return.
"""

import sys
import random
import string

from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"


# -------------------- glitch title (copy of welcome style) --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0

        self.font = QFont("Arial", 40, QFont.Bold)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

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

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            shift = self.glitch_strength

            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)
                jitter_x = x + random.randint(-10, 10)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# -------------------- pill progress bar --------------------
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

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        # wide pill, 40 px tall
        return self.parent().width() // 3 if self.parent() else 400, 40

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

