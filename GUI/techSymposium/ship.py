"""
ship.py
Pallet Portal – Ship Screen (clean, modular version)

This screen:
- Displays glitch title “SHIPMENT IN PROGRESS”
- Left column:
      • "<code> was scanned" bubble
      • pill progress bar
      • percent label
      • cyan logo
- Right column:
      • white rounded panel
      • scanned barcode list
- Handles:
      set_manifest_codes(...)
      on_barcode_matched(...)
- No barcode worker inside (palletPortal.py manages workers)
- 4-key exit combo (Ctrl + C + V + Enter/Return)
"""

import sys
import random
import string
from PyQt5.QtCore import Qt, QTimer, QRect, QSize
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


# ============================================================
# GlitchTitle Widget
# ============================================================
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0

        self.font = QFont("Arial", 36, QFont.Bold)
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

        rect = p.boundingRect(self.rect(), Qt.AlignCenter, self.scrambled)
        fm = self.fontMetrics()
        baseline = rect.y() + rect.height() - fm.descent()
        x, y = rect.x(), baseline

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            shift = self.glitch_strength

            # red offset
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan offset
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter
            if random.random() < 0.4:
                jx = x + random.randint(-10, 10)
                jy = y + random.randint(-20, 20)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jx, jy, self.scrambled)

        p.end()


# ============================================================
# UI bubbles and panels
# ============================================================
class ScanBubble(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.radius = 40

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 18, 40, 18)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 20))
        self.label.setStyleSheet("color:black;")
        layout.addWidget(self.label)

    def setText(self, t):
        self.label.setText(t)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        p.setBrush(QColor(255, 255, 255))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, self.radius, self.radius)

        p.end()
        super().paintEvent(e)


class RoundedPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.radius = 40

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        p.setBrush(QColor(255, 255, 255))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, self.radius, self.radius)

        p.end()
        super().paintEvent(e)


# ============================================================
# Pill ProgressBar
# ============================================================
class PillProgressBar(QWidget):
    def __init__(self):
        super().__init__()
        self._value = 0
        self._visual = 0.0

        self.anim = QTimer(self)
        self.anim.timeout.connect(self._step)
        self.anim.start(30)

    def setValue(self, v):
        self._value = max(0, min(100, int(v)))

    def _step(self):
        target = self._value / 100.0
        self._visual += (target - self._visual) * 0.12
        if abs(self._visual - target) < 0.003:
            self._visual = target
        self.update()

    def sizeHint(self):
        return QSize(360, 40)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin = 6
        outer = QRect(margin, margin, w - margin*2, h - margin*2)
        radius = outer.height() / 2

        # shadow
        sh = outer.translated(0, 3)
        p.setBrush(QColor(0, 0, 0, 120))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(sh, radius, radius)

        # track border
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(outer, radius, radius)

        # inner cyan track
        inner = outer.adjusted(4, 4, -4, -4)
        p.setBrush(QColor(210, 255, 250))
        p.drawRoundedRect(inner, inner.height()/2, inner.height()/2)

        # fill
        fill_w = int(inner.width() * max(0, min(1, self._visual)))
        if fill_w > 0:
            fill_rect = QRect(inner.left(), inner.top(), fill_w, inner.height())
            p.setBrush(QColor(0, 255, 180))
            p.drawRoundedRect(fill_rect, inner.height()/2, inner.height()/2)

        p.end()


# ============================================================
# ShipScreen
# ============================================================
class ShipScreen(QWidget):
    def __init__(self):
        super().__init__()

        self.setStyleSheet("background-color:black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()

        self._expected = []
        self._found = set()
        self._items = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(10)

        # title
        self.title = GlitchTitle("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(80)
        root.addWidget(self.title)

        root.addSpacing(30)

        # layout row
        row = QHBoxLayout()
        row.setSpacing(40)
        root.addLayout(row, stretch=1)

        # RIGHT column first
        right = QVBoxLayout()
        right.setSpacing(12)
        row.addLayout(right, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Arial", 26, QFont.Bold))
        subtitle.setStyleSheet("color:#eaeaea;")
        right.addWidget(subtitle)

        self.panel = RoundedPanel()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setStyleSheet("""
            QListWidget {
                background:white;
                border:0px;
                color:black;
            }
            QListWidget::item { padding:4px; }
        """)
        panel_layout.addWidget(self.list)
        right.addWidget(self.panel)

        # LEFT column
        left = QVBoxLayout()
        left.setSpacing(24)
        row.insertLayout(0, left, stretch=3)

        left.addSpacing(52)

        self.bubble = ScanBubble()
        left.addWidget(self.bubble)

        left.addSpacing(60)

        self.progress = PillProgressBar()
        self.progress.setFixedHeight(40)
        left.addWidget(self.progress)

        self.percent = QLabel("0%")
        self.percent.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.percent.setFont(QFont("Arial", 18))
        self.percent.setStyleSheet("color:white;")
        left.addWidget(self.percent)

        left.addStretch(1)

        self.logo = QLabel()
        self.logo.setFixedSize(96, 96)
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo.setPixmap(pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        left.addWidget(self.logo, alignment=Qt.AlignLeft | Qt.AlignBottom)

        root.addStretch(0)

    # ============================================================
    # Manifest Wiring
    # ============================================================
    def set_manifest_codes(self, codes):
        self._expected = list(codes or [])
        self._found.clear()
        self._items.clear()
        self.list.clear()
        self.bubble.setText("")
        self.progress.setValue(0)
        self.percent.setText("0%")

        for c in self._expected:
            item = QListWidgetItem(c)
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.list.addItem(item)
            self._items[c] = item

    # ============================================================
    # Barcode Match
    # ============================================================
    def on_barcode_matched(self, code):
        if code in self._found:
            return

        self._found.add(code)
        self.bubble.setText(f"{code} was scanned")

        item = self._items.get(code)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        total = len(self._expected)
        if total > 0:
            pct = int(round(len(self._found) * 100.0 / total))
            self.progress.setValue(pct)
            self.percent.setText(f"{pct}%")

    # ============================================================
    # Exit Combo
    # ============================================================
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


# ============================================================
# Standalone Test
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()

    # Fake data updates for demo
    import random
    t = QTimer()
    fake_codes = ["ABC123", "DEF456", "GHI789"]
    idx = {"i": 0}

    def fake_scan():
        if idx["i"] < len(fake_codes):
            w.on_barcode_matched(fake_codes[idx["i"]])
            idx["i"] += 1

    t.timeout.connect(fake_scan)
    t.start(1500)

    sys.exit(app.exec_())
