import sys, random, string
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QScrollArea,
    QGridLayout
)


# ============================================================
#   GLITCH TITLE  (same as shipment & welcome screens)
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

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        # glitch overlays
        if self.glitch_strength > 0:
            shift = self.glitch_strength

            # red
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter
            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)
                jitter_x = x + random.randint(-10, 10)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# ============================================================
#                   VIEW ORDER SCREEN (standalone)
# ============================================================
class ViewOrderScreen(QWidget):
    def __init__(self):
        super().__init__()

        self.orders = []
        self._next_row = 1

        self.setStyleSheet("background-color:black;")

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)

        # glitch title
        self.title = GlitchTitle("VIEW ORDERS")
        self.title.setMinimumHeight(80)
        root.addWidget(self.title)

        # ---------------- Rounded white panel ----------------
        panel = QWidget()
        panel.setObjectName("ordersPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)
        root.addWidget(panel)

        self.setStyleSheet(
            """
            QWidget#ordersPanel {
                background-color:#ffffff;
                border-radius:40px;
            }
            QLabel {
                color:#000000;
            }
            """
        )

        # scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border:0px; background:transparent;")
        panel_layout.addWidget(self.scroll_area)

        # container inside scroll
        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.scroll_area.setWidget(self.container)

        # grid layout (header + rows)
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(10)

        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 14, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, 0, col)

        # status bubble
        self.status = QLabel("Press X to exit")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Arial", 18))
        self.status.setObjectName("statusBubble")
        self.status.setAttribute(Qt.WA_StyledBackground, True)

        root.addWidget(self.status)

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

    # -----------------------------------------------------
    #               Add a row to the table
    # -----------------------------------------------------
    def add_order(self, start, end, scanned_count, trailer_number):
        duration = end - start
        archway = "Archway 1"

        start_str = start.strftime("%H:%M:%S")
        end_str = end.strftime("%H:%M:%S")
        duration_str = str(duration).split(".")[0]

        values = [
            trailer_number,
            archway,
            start_str,
            end_str,
            duration_str,
            str(scanned_count)
        ]

        for col, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setFont(QFont("Arial", 13))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, self._next_row, col)

        self._next_row += 1

    # exit with X or C
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_X, Qt.Key_C):
            QApplication.quit()


# ============================================================
#                      DEMO DRIVER
# ============================================================
class DemoDriver:
    def __init__(self, screen: ViewOrderScreen):
        self.screen = screen
        self.timer = QTimer()
        self.timer.timeout.connect(self._fake_order)
        self.timer.start(2000)

        self.count = 1

    def _fake_order(self):
        if self.count > 5:
            self.timer.stop()
            return

        now = datetime.now()
        start = now - timedelta(minutes=random.randint(1, 9))
        end = now
        scanned = random.randint(1, 12)
        trailer = f"T-{100 + self.count}"

        self.screen.add_order(start, end, scanned, trailer)

        self.count += 1


# ============================================================
#                 STANDALONE ENTRY POINT
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewOrderScreen()
    w.showFullScreen()
    demo = DemoDriver(w)
    sys.exit(app.exec_())
