"""
shipScreenv004.py

updates:
- glitch title uses EXACT welcome-screen glitch class
- title font reduced slightly so it no longer clips left/right
- left scanned-message bubble has proper rounded corners
- "SCANNED BARCODES" subtitle centered above right panel
- progress percentage moved below bar for visibility
- layout centered & spacing tuned for 1024x600
- theme colors: black + white + cyan/magenta/red
- includes 4-key fullscreen exit combo (ctrl + c + v + enter)
"""

import sys, random, string
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QFont,
    QFontMetrics,
    QPainterPath,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QSizePolicy,
)


CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"


# ---------------------------------------------------------
# EXACT GLITCH CLASS FROM WELCOME SCREEN (font size reduced)
# ---------------------------------------------------------
class GlitchText(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", led_driver=None):
        super().__init__()
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.led = led_driver

        self.font = QFont("Arial", 56, QFont.Bold)   # reduced from 72 → 56
        self.setStyleSheet("background-color: black;")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

    def set_led_color(self, rgb):
        if not self.led:
            return

    def update_glitch(self):
        if random.random() < 0.35:
            self.glitch_strength = random.randint(3, 12)
            self.scramble()
        else:
            self.scrambled = self.text
            self.glitch_strength = 0
        self.update()

    def scramble(self):
        chars = list(self.text)
        for i in range(len(chars)):
            if random.random() < 0.25:
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        widget_rect = self.rect()
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)

        fm = QFontMetrics(self.font)
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()
        x = text_rect.x()
        y = baseline_y

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            s = self.glitch_strength

            # red left
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - s, y, self.scrambled)

            # cyan right
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + s, y, self.scrambled)

            # magenta jitter
            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)
                jitter_x = x + random.randint(-10, 10)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# ---------------------------------------------------------
# SHIP SCREEN LAYOUT
# ---------------------------------------------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()

        self._expected_codes = []
        self._found = set()
        self._barcode_items = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(10)

        # --- Title ---
        self.title = GlitchText("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(95)
        root.addWidget(self.title)

        # --- Middle row ---
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        # ========================
        # LEFT COLUMN
        # ========================
        left = QVBoxLayout()
        left.setSpacing(24)
        middle.addLayout(left, stretch=3)

        # bubble
        self.bubble = QWidget()
        self.bubble.setStyleSheet("""
            QWidget {
                background:white;
                border-radius:40px;
            }
        """)
        bubbleLayout = QVBoxLayout(self.bubble)
        bubbleLayout.setContentsMargins(32, 20, 32, 20)

        self.scan_msg = QLabel("")
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setFont(QFont("Arial", 24))
        bubbleLayout.addWidget(self.scan_msg)

        left.addWidget(self.bubble)

        # progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(26)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color:#222;
                border-radius:4px;
            }
            QProgressBar::chunk {
                background-color:#00ff7f;
                border-radius:4px;
            }
        """)
        left.addWidget(self.progress)

        # %-text below progress bar
        self.percent_lbl = QLabel("0%")
        self.percent_lbl.setAlignment(Qt.AlignCenter)
        self.percent_lbl.setFont(QFont("Arial", 20, QFont.Bold))
        self.percent_lbl.setStyleSheet("color:white;")
        left.addWidget(self.percent_lbl)

        left.addStretch(1)

        # logo bottom-left
        logo = QLabel()
        logo.setFixedSize(96, 96)
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            logo.setPixmap(pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        left.addWidget(logo, alignment=Qt.AlignLeft)

        # ========================
        # RIGHT COLUMN
        # ========================
        right = QVBoxLayout()
        right.setSpacing(12)
        middle.addLayout(right, stretch=4)

        # centered subtitle
        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Arial", 28, QFont.Bold))
        subtitle.setStyleSheet("color:#eaeaea;")
        right.addWidget(subtitle)

        panel = QWidget()
        panel.setStyleSheet("""
            QWidget {
                background:white;
                border-radius:40px;
            }
        """)
        pLayout = QVBoxLayout(panel)
        pLayout.setContentsMargins(24, 24, 24, 24)

        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        self.scanned_list.setStyleSheet("""
            QListWidget {
                background:white;
                border:0px;
                color:black;
            }
            QListWidget::item {
                padding:6px;
            }
        """)
        pLayout.addWidget(self.scanned_list)

        right.addWidget(panel)

    # ---------------------------------------------------------
    # Manifest handling
    # ---------------------------------------------------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.scan_msg.setText("")
        self.progress.setValue(0)
        self.percent_lbl.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(16)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    def on_barcode_matched(self, code, score=None, method=None):
        if code in self._found:
            return

        self._found.add(code)
        self.scan_msg.setText(f"{code} was scanned")

        item = self._barcode_items.get(code)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        total = len(self._expected_codes)
        if total > 0:
            pct = int(len(self._found) * 100 / total)
            self.progress.setValue(pct)
            self.percent_lbl.setText(f"{pct}%")

    # ---------------------------------------------------------
    # Exit combo
    # ---------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        if (mods & Qt.ControlModifier and
            Qt.Key_C in self._pressed and
            Qt.Key_V in self._pressed and
            k in (Qt.Key_Return, Qt.Key_Enter)):
            QApplication.quit()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


# ---------------------------------------------------------
# Demo runner
# ---------------------------------------------------------
class _Demo:
    def __init__(self, s: ShipScreen):
        demo = [
            "1234567891",
            "9876543210",
            "2085692649",
            "9340754051",
            "2799407451",
        ]
        s.set_manifest_codes(demo)
        self.left = list(demo)
        self.s = s

        self.t = QTimer()
        self.t.timeout.connect(self.do_fake)
        self.t.start(1700)

    def do_fake(self):
        if not self.left:
            self.t.stop()
            return
        code = self.left.pop(0)
        self.s.on_barcode_matched(code)


# ---------------------------------------------------------
# main
# ---------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()   # target hardware
    _Demo(w)
    sys.exit(app.exec_())
