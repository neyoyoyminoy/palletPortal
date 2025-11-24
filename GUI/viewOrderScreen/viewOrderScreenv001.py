import sys, random, string
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout,
    QApplication, QHBoxLayout, QFrame
)


# ============================================================
#   GLITCH TITLE  (identical to Welcome + Shipment versions)
# ============================================================
class GlitchTitle(QWidget):
    def __init__(self, text="VIEW ORDERS", parent=None):
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

        # Base white text
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


# ============================================================
#                  VIEW ORDER SCREEN (THEMED)
# ============================================================
class ViewOrderScreen(QWidget):
    return_to_welcome = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.orders = []
        self._next_row = 1

        self.setStyleSheet("background-color:black;")

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)

        # ---------------- Glitch Title ----------------
        self.title = GlitchTitle("VIEW ORDERS")
        self.title.setMinimumHeight(80)
        root.addWidget(self.title)

        # ---------------- White Rounded Panel ----------------
        panel_wrapper = QWidget()
        panel_wrapper.setObjectName("ordersPanel")
        panel_wrapper.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel_wrapper)
        panel_layout.setContentsMargins(24, 24, 24, 24)
        root.addWidget(panel_wrapper)

        # Style the rounded white box
        self.setStyleSheet(
            """
            QWidget#ordersPanel {
                background-color:#ffffff;
                border-radius:40px;
            }
            QLabel {
                color: #000000;
            }
            """
        )

        # ---------------- Scroll Area ----------------
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border:0px; background:transparent;")
        panel_layout.addWidget(self.scroll_area)

        # Container inside scroll area
        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.scroll_area.setWidget(self.container)

        # ---------------- Grid Layout ----------------
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setAlignment(Qt.AlignTop)
        self.grid_layout.setHorizontalSpacing(20)
        self.grid_layout.setVerticalSpacing(10)

        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 14, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, col)

        # ---------------- Status Bubble ----------------
        self.status = QLabel("Press X to return to Welcome Screen")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Arial", 16))
        self.status.setObjectName("statusBubble")
        self.status.setAttribute(Qt.WA_StyledBackground, True)

        root.addWidget(self.status)

        # White rounded bubble
        self.setStyleSheet(
            self.styleSheet()
            + """
            QLabel#statusBubble {
                background-color:#ffffff;
                color:#000000;
                border-radius:30px;
                padding:12px 20px;
            }
            """
        )

    # ------------------------------------------------------------
    #                      Add Order Row
    # ------------------------------------------------------------
    def add_order(self, start_time, end_time, scanned_count, trailer_number):
        duration = end_time - start_time
        archway = "Archway 1"

        self.orders.append(
            {
                "start": start_time,
                "end": end_time,
                "duration": duration,
                "scanned_count": scanned_count,
                "archway": archway,
                "trailer": trailer_number,
            }
        )

        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
        duration_str = str(duration).split(".")[0]

        values = [
            trailer_number,
            archway,
            start_str,
            end_str,
            duration_str,
            str(scanned_count),
        ]

        for col, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setFont(QFont("Arial", 13))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, self._next_row, col)

        self._next_row += 1

    # ------------------------------------------------------------
    #                     Key Handling (X/C)
    # ------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_X, Qt.Key_C):
            import os

            for k in list(os.environ.keys()):
                if "QT_QPA_PLATFORM_PLUGIN_PATH" in k or "QT_PLUGIN_PATH" in k:
                    os.environ.pop(k, None)

            python = sys.executable
            os.execv(python, [python] + sys.argv)

    # ------------------------------------------------------------
    def clear_orders(self):
        for row in reversed(range(1, self._next_row)):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)

        self.orders.clear()
        self._next_row = 1
