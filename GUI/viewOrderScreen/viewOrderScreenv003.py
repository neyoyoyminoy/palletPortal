"""
viewOrderScreenv002.py
stand-alone tester for the redesigned view order screen
theme: black background, glitch title, white rounded table panel
"""

import sys, random, string
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QScrollArea,
    QHBoxLayout, QGridLayout
)

# -------------------- glitch title (same as welcome/ship) --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="VIEW ORDERS", parent=None):
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.font = QFont("Arial", 48, QFont.Bold)

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
            if random.random() < 0.12:
                chars[i] = random.choice(string.ascii_uppercase + string.digits)
        self.scrambled = "".join(chars)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        rect = p.boundingRect(self.rect(), Qt.AlignCenter, self.scrambled)
        fm = self.fontMetrics()
        baseline = rect.y() + rect.height() - fm.descent()

        x = rect.x()
        y = baseline

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            shift = self.glitch_strength

            p.setPen(QColor(255, 0, 0, 180))      # red left
            p.drawText(x - shift, y, self.scrambled)

            p.setPen(QColor(0, 255, 255, 180))    # cyan right
            p.drawText(x + shift, y, self.scrambled)

            if random.random() < 0.35:           # magenta jitter
                jitter_x = x + random.randint(-10, 10)
                jitter_y = y + random.randint(-15, 15)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# -------------------- ViewOrderScreen --------------------
class ViewOrderScreen(QWidget):
    return_to_welcome = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)

        # glitch title
        self.title = GlitchTitle("VIEW ORDERS")
        self.title.setMinimumHeight(100)
        layout.addWidget(self.title)

        # scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.scroll_area, stretch=1)

        # white rounded panel
        self.container = QWidget()
        self.container.setObjectName("panel")
        self.container.setStyleSheet("""
            QWidget#panel {
                background-color: white;
                border-radius: 40px;
            }
        """)

        self.scroll_area.setWidget(self.container)

        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(40, 30, 40, 30)
        self.grid.setHorizontalSpacing(40)
        self.grid.setVerticalSpacing(10)
        self.grid.setAlignment(Qt.AlignTop)

        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 16, QFont.Bold))
            lbl.setStyleSheet("color: black;")
            self.grid.addWidget(lbl, 0, col)

        self._next_row = 1
        self.orders = []

        # exit text
        self.exit_label = QLabel("Press X to exit")
        self.exit_label.setAlignment(Qt.AlignCenter)
        self.exit_label.setFont(QFont("Arial", 18))
        self.exit_label.setStyleSheet("color: white;")
        layout.addWidget(self.exit_label)

    def add_order(self, trailer, start, end, scanned):
        duration = end - start
        arch = "Archway 1"

        fields = [
            trailer,
            arch,
            start.strftime("%H:%M:%S"),
            end.strftime("%H:%M:%S"),
            str(duration).split(".")[0],
            str(scanned)
        ]

        for col, val in enumerate(fields):
            lbl = QLabel(val)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 15))
            lbl.setStyleSheet("color: black;")
            self.grid.addWidget(lbl, self._next_row, col)

        self._next_row += 1

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_X, Qt.Key_C):
            QApplication.quit()


# -------------------- standalone test driver --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewOrderScreen()
    w.showFullScreen()

    # add some dummy rows
    now = datetime.now()
    for i in range(5):
        start = now - timedelta(minutes=5 - i)
        end = start + timedelta(minutes=random.randint(1, 5))
        w.add_order(f"T-{101+i}", start, end, random.randint(1, 6))

    sys.exit(app.exec_())
