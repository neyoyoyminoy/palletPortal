"""
order.py
Pallet Portal – View Orders screen (glitch theme)

Features:
- Black background
- Glitch title: "VIEW ORDERS"
- White rounded panel containing a scrollable table:
    Trailer | Archway | Start | End | Duration | Scanned
- Bottom hint: "Press X to return to Welcome Screen"
- Emits return_to_welcome on X/C key press
- add_order(...) accepts both:
    add_order(trailer, start, end, scanned)
    add_order(start_time=..., end_time=..., scanned_count=..., trailer_number=...)
"""

import sys
import random
import string
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QScrollArea,
    QGridLayout,
)


# ============================================================
# GlitchTitle Widget
# ============================================================
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

            # red left
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan right
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter
            if random.random() < 0.35:
                jitter_x = x + random.randint(-10, 10)
                jitter_y = y + random.randint(-15, 15)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# ============================================================
# ViewOrderScreen
# ============================================================
class ViewOrderScreen(QWidget):
    return_to_welcome = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setStyleSheet("background-color:black;")
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
        self.scroll_area.setStyleSheet("background:transparent; border:none;")
        layout.addWidget(self.scroll_area, stretch=1)

        # white rounded panel
        self.container = QWidget()
        self.container.setObjectName("panel")
        self.container.setStyleSheet("""
            QWidget#panel {
                background-color:white;
                border-radius:40px;
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
            lbl.setStyleSheet("color:black;")
            self.grid.addWidget(lbl, 0, col)

        self._next_row = 1
        self.orders = []

        # status / hint
        self.exit_label = QLabel("Press X to return to Welcome Screen")
        self.exit_label.setAlignment(Qt.AlignCenter)
        self.exit_label.setFont(QFont("Arial", 18))
        self.exit_label.setStyleSheet("color:white;")
        layout.addWidget(self.exit_label)

    # --------------------------------------------------------
    # add_order: supports both old and new calling styles
    # --------------------------------------------------------
    def add_order(self, trailer=None, start=None, end=None, scanned=None, **kwargs):
        """
        Accepts either:
          add_order(trailer, start, end, scanned)
        or:
          add_order(start_time=..., end_time=..., scanned_count=..., trailer_number=...)
        """

        # map old named args if passed
        if trailer is None and "trailer_number" in kwargs:
            trailer = kwargs.get("trailer_number")
        if start is None and "start_time" in kwargs:
            start = kwargs.get("start_time")
        if end is None and "end_time" in kwargs:
            end = kwargs.get("end_time")
        if scanned is None and "scanned_count" in kwargs:
            scanned = kwargs.get("scanned_count")

        # basic defaults for safety if something missing
        trailer = trailer if trailer is not None else "Unknown"
        start = start if isinstance(start, datetime) else datetime.now()
        end = end if isinstance(end, datetime) else (start + timedelta(minutes=5))
        scanned = scanned if scanned is not None else 0

        duration = end - start
        arch = "Archway 1"

        self.orders.append(
            {
                "trailer": trailer,
                "archway": arch,
                "start": start,
                "end": end,
                "duration": duration,
                "scanned": scanned,
            }
        )

        fields = [
            trailer,
            arch,
            start.strftime("%H:%M:%S"),
            end.strftime("%H:%M:%S"),
            str(duration).split(".")[0],
            str(scanned),
        ]

        row = self._next_row
        for col, val in enumerate(fields):
            lbl = QLabel(val)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 15))
            lbl.setStyleSheet("color:black;")
            self.grid.addWidget(lbl, row, col)

        self._next_row += 1

    def clear_orders(self):
        for row in range(1, self._next_row):
            for col in range(self.grid.columnCount()):
                item = self.grid.itemAtPosition(row, col)
                if item and item.widget():
                    item.widget().setParent(None)
        self.orders.clear()
        self._next_row = 1

    # --------------------------------------------------------
    # Key handling
    # --------------------------------------------------------
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_X, Qt.Key_C):
            self.return_to_welcome.emit()
            e.accept()
            return
        super().keyPressEvent(e)


# ============================================================
# Standalone test
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewOrderScreen()
    w.showFullScreen()

    # demo rows
    now = datetime.now()
    w.add_order("TRLR-001", now, now + timedelta(minutes=7, seconds=13), 10)
    w.add_order("TRLR-002", now + timedelta(minutes=10), now + timedelta(minutes=21), 8)

    sys.exit(app.exec_())
